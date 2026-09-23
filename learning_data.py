"""Stable data contracts, normalized tables, and data-quality checks."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from io import StringIO

import pandas as pd

from allotment import allot, build_breaks, campaign_requests, split_list
from schedule_source import stable_demo_schedule
from contracts import allocation_errors, programme_errors


@dataclass(frozen=True)
class Programme:
    programme_id: str
    channel: str
    title: str
    genre: str
    start: pd.Timestamp
    stop: pd.Timestamp
    source: str


@dataclass(frozen=True)
class Break:
    break_id: str
    programme_id: str
    channel: str
    air_time: pd.Timestamp
    capacity_sec: int
    presold_sec: int


@dataclass(frozen=True)
class Campaign:
    request_id: str
    status: str
    target_group: str
    goal_impressions: int
    spot_sec: int


@dataclass(frozen=True)
class Placement:
    request_id: str
    break_id: str
    spot_sec: int
    target_p20: int
    target_p50: int


@dataclass(frozen=True)
class ForecastResult:
    break_id: str
    model_name: str
    training_cutoff: pd.Timestamp
    forecast_issue_time: pd.Timestamp
    calibration_start: pd.Timestamp
    calibration_end: pd.Timestamp
    raw_prediction: float
    p20: float
    p50: float
    p80: float


def stable_case(artifacts=None, model_name="xgboost", policy="firm_first", plan_on="p20") -> dict[str, pd.DataFrame]:
    """Return one deterministic, offline demonstration case."""
    programmes = stable_demo_schedule()
    breaks = build_breaks(programmes)
    from forecast_workbench import evaluate_models, forecast_breaks
    artifacts = evaluate_models() if artifacts is None else artifacts
    breaks, features = forecast_breaks(breaks, artifacts, model_name)
    requests = campaign_requests(programmes["start"].min())
    placements, summary, fill = allot(breaks, requests, policy, plan_on)
    return {
        "programmes": programmes,
        "breaks": breaks,
        "requests": requests,
        "placements": placements,
        "summary": summary,
        "fill": fill,
        "features": features,
    }


def normalized_campaign_tables(requests: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Turn list-valued request cells into safe relationship tables."""
    campaigns = requests.drop(columns=["eligible_channels", "dayparts"]).copy()
    channel_rows: list[dict[str, object]] = []
    daypart_rows: list[dict[str, object]] = []
    for row in requests.itertuples(index=False):
        for rank, channel in enumerate(split_list(row.eligible_channels), start=1):
            channel_rows.append(
                {"request_id": row.request_id, "channel": channel, "preference_rank": rank}
            )
        for part in split_list(row.dayparts):
            daypart_rows.append({"request_id": row.request_id, "daypart": part})
    return {
        "campaigns": campaigns,
        "campaign_channels": pd.DataFrame(channel_rows),
        "campaign_dayparts": pd.DataFrame(daypart_rows),
    }


def data_quality_report(
    programmes: pd.DataFrame,
    breaks: pd.DataFrame,
    requests: pd.DataFrame,
    placements: pd.DataFrame,
) -> pd.DataFrame:
    """Use the same executable contracts that gate real calculation paths."""
    errors = programme_errors(programmes) + allocation_errors(breaks, requests, placements)
    if errors:
        return pd.DataFrame([dict(check=error, status="FAIL", why_it_matters="Correct this before continuing.") for error in dict.fromkeys(errors)])
    if "programme_id" in breaks and "programme_id" in programmes:
        if not breaks.programme_id.isin(programmes.programme_id).all():
            errors.append("Breaks: unknown programme reference")
        elif not programmes.programme_id.duplicated().any():
            lookup = programmes.set_index("programme_id")
            for row in breaks.itertuples():
                p = lookup.loc[row.programme_id]
                if row.channel != p.channel or not p.start <= row.air_time < p.stop:
                    errors.append("Breaks: channel or time does not match programme")
                    break
    if errors:
        return pd.DataFrame([dict(check=error, status="FAIL", why_it_matters="Correct this before continuing.") for error in dict.fromkeys(errors)])
    return pd.DataFrame([dict(check=check, status="PASS", why_it_matters=why) for check, why in [
        ("Required values and unique keys", "Every record is complete and has one identity."),
        ("Programme times and break references", "Programmes do not overlap; breaks belong to their programmes."),
        ("Durations and forecast values", "Durations are positive; forecast values are ordered."),
        ("Campaign eligibility and spot limits", "Every placement follows the campaign rules."),
        ("Total used seconds", "Existing bookings plus new spots fit in each break."),
        ("Placement identities and audience", "No duplicate spot or unknown reference; delivery matches the forecast."),
    ]])


SQL_EXAMPLES = {
    "Remaining seconds by break": """
SELECT
  b.break_id,
  b.channel,
  b.air_time,
  b.capacity_sec,
  b.presold_sec + COALESCE(SUM(p.spot_sec), 0) AS used_sec,
  b.capacity_sec - b.presold_sec - COALESCE(SUM(p.spot_sec), 0) AS remaining_sec
FROM breaks b
LEFT JOIN placements p ON p.break_id = b.break_id
GROUP BY b.break_id, b.channel, b.air_time, b.capacity_sec, b.presold_sec
ORDER BY b.air_time
LIMIT 12;
""".strip(),
    "Find an overbooked break": """
SELECT
  b.break_id,
  b.capacity_sec,
  b.presold_sec + COALESCE(SUM(p.spot_sec), 0) AS used_sec
FROM breaks b
LEFT JOIN placements p ON p.break_id = b.break_id
GROUP BY b.break_id, b.capacity_sec, b.presold_sec
HAVING used_sec > b.capacity_sec;
""".strip(),
    "Campaign delivery counted once": """
WITH delivered AS (
  SELECT
    request_id,
    SUM(target_p20) AS delivered_p20,
    SUM(target_p50) AS delivered_p50
  FROM placements
  GROUP BY request_id
)
SELECT
  c.request_id,
  c.advertiser,
  c.goal_impressions,
  COALESCE(d.delivered_p20, 0) AS delivered_p20,
  COALESCE(d.delivered_p50, 0) AS delivered_p50
FROM campaigns c
LEFT JOIN delivered d ON d.request_id = c.request_id
ORDER BY c.request_id;
""".strip(),
    "Eligible campaign-break matches": """
SELECT
  c.request_id,
  cc.channel,
  cd.daypart,
  COUNT(DISTINCT b.break_id) AS eligible_breaks
FROM campaigns c
JOIN campaign_channels cc ON cc.request_id = c.request_id
JOIN campaign_dayparts cd ON cd.request_id = c.request_id
JOIN breaks b ON b.channel = cc.channel AND b.daypart = cd.daypart
GROUP BY c.request_id, cc.channel, cd.daypart
ORDER BY c.request_id, cc.preference_rank, cd.daypart;
""".strip(),
}


def run_sql_example(case: dict[str, pd.DataFrame], query: str) -> pd.DataFrame:
    """Run a read-only teaching query against an in-memory normalized model."""
    normalized = normalized_campaign_tables(case["requests"])
    programmes = case["programmes"].copy()
    breaks = case["breaks"].copy()
    placements = case["placements"].copy()
    for frame in (programmes, breaks, placements):
        for column in frame.columns:
            if pd.api.types.is_datetime64_any_dtype(frame[column]):
                frame[column] = frame[column].astype(str)
    with closing(sqlite3.connect(":memory:")) as connection:
        programmes.to_sql("programmes", connection, index=False)
        breaks.to_sql("breaks", connection, index=False)
        placements.to_sql("placements", connection, index=False)
        for name, frame in normalized.items():
            frame.to_sql(name, connection, index=False)
        return pd.read_sql_query(query, connection)


def relationship_diagram() -> str:
    return """
campaigns (one row per goal)
    │ request_id
    ├──────────────► campaign_channels (one row per allowed channel)
    ├──────────────► campaign_dayparts (one row per allowed daypart)
    │
    └──────────────► placements ◄────────────── breaks
                       request_id                 break_id
""".strip()


def contract_markdown() -> str:
    rows = [
        ("Programme", "programme_id", "One scheduled programme"),
        ("Break", "break_id", "One commercial break inside a programme"),
        ("Campaign", "request_id", "One goal and one set of business rules"),
        ("Placement", "request_id + break_id", "One campaign spot in one break"),
        ("ForecastResult", "break_id + model_name + training_cutoff", "One versioned forecast"),
    ]
    buffer = StringIO()
    buffer.write("| Contract | Key | One row means |\n|---|---|---|\n")
    for name, key, grain in rows:
        buffer.write(f"| `{name}` | `{key}` | {grain} |\n")
    return buffer.getvalue()
