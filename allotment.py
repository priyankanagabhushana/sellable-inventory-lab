"""Spot allotment on a programme grid: the manual rule, written down.

On linear TV the scarce thing is airtime in a break. Viewers are not used up:
two spots in the same break both reach that break's audience. So the rule
places spots into breaks with free seconds and counts each campaign's
target-group audience against its goal, on the conservative P20 forecast.

Breaks, audiences and campaign requests here are synthetic. Only the
programme grid underneath may be real.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd
from contracts import allocation_errors, programme_errors, require_valid

BREAK_SECONDS = 180
P20_FACTOR = 0.78
W25_49_SHARE = 0.28
NO_BREAK_GENRES = {"Einkauf"}

CHANNEL_BASE = {"3+": 90_000, "4+": 38_000, "5+": 32_000, "6+": 22_000}
DAYPART_WEIGHT = {"morning": 0.15, "day": 0.30, "access": 0.60, "prime": 1.00, "late": 0.35}
GENRE_WEIGHT = {
    "Film": 1.10,
    "Krimi Drama": 1.00,
    "Krimi": 1.00,
    "Drama Serie": 0.95,
    "Drama": 0.95,
    "Reality": 1.00,
    "Unterhaltung": 0.95,
    "Sitcom": 0.80,
    "Dokumentation": 0.75,
    "Musik": 0.50,
    "Erwachsene": 0.40,
    "Kinder": 0.40,
}
PRESOLD_SHARE = {
    ("3+", "prime"): 0.83,
    ("3+", "access"): 0.67,
    ("4+", "prime"): 0.67,
    ("5+", "prime"): 0.50,
    ("6+", "prime"): 0.50,
}
DEFAULT_PRESOLD_SHARE = 0.33
TARGET_SHARE = {"All adults": 1.0, "Women 25–49": W25_49_SHARE}
LIST_SEP = " | "


def daypart(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "day"
    if 18 <= hour < 20:
        return "access"
    if 20 <= hour < 23:
        return "prime"
    return "late"


def split_list(cell: str) -> list[str]:
    return [part.strip() for part in str(cell).split("|") if part.strip()]


def build_breaks(schedule: pd.DataFrame) -> pd.DataFrame:
    """One row per commercial break, with a synthetic P50/P20 adult audience."""
    require_valid(programme_errors(schedule))
    rows = []
    for programme in schedule.itertuples(index=False):
        if programme.genre in NO_BREAK_GENRES or programme.duration_min < 20:
            continue
        count = max(1, round(programme.duration_min / 30))
        for index in range(count):
            offset = programme.duration_min * (index + 1) / (count + 1)
            at = programme.start + pd.Timedelta(minutes=round(offset))
            part = daypart(at.hour)
            seed = zlib.crc32(f"{programme.channel}|{at.isoformat()}".encode())
            noise = np.random.default_rng(seed).normal(1.0, 0.08)
            p50 = (
                CHANNEL_BASE.get(programme.channel, 20_000)
                * DAYPART_WEIGHT[part]
                * GENRE_WEIGHT.get(programme.genre, 0.8)
                * max(noise, 0.6)
            )
            presold_share = PRESOLD_SHARE.get((programme.channel, part), DEFAULT_PRESOLD_SHARE)
            presold = int(round(BREAK_SECONDS * presold_share / 10) * 10)
            rows.append(
                {
                    "break_id": f"{programme.programme_id}-B{index + 1:02d}",
                    "break_position": index,
                    "slot_key": f"{programme.channel}-{programme.start.dayofweek}-{programme.start:%H%M}-{index}",
                    "programme_id": programme.programme_id,
                    "channel": programme.channel,
                    "air_time": at,
                    "day": at.strftime("%a %d %b"),
                    "daypart": part,
                    "programme": programme.title,
                    "genre": programme.genre,
                    "capacity_sec": BREAK_SECONDS,
                    "presold_sec": presold,
                    "adults_p50": int(round(p50, -2)),
                    "adults_p20": int(round(p50 * P20_FACTOR, -2)),
                }
            )
    breaks = pd.DataFrame(rows)
    if breaks.empty:
        return breaks
    if breaks.break_id.duplicated().any():
        raise ValueError("Duplicate break IDs")
    return breaks.sort_values(["air_time", "channel"]).reset_index(drop=True)


def campaign_requests(week_start: pd.Timestamp) -> pd.DataFrame:
    """Synthetic requests shaped like a planner's sheet: lists inside cells."""
    day = week_start.normalize()
    specs = [
        ("C01", "Alpine Bank", "firm", -21, "3+ | 4+", "prime", "Women 25–49", 30, 180_000, 14),
        ("C02", "Lake Insurance", "firm", -18, "3+", "prime | access", "All adults", 30, 900_000, 14),
        ("C03", "City Retail", "option", -16, "3+ | 5+", "prime", "All adults", 20, 700_000, 12),
        ("C04", "North Telecom", "firm", -9, "3+ | 4+ | 5+", "prime", "All adults", 30, 1_100_000, 18),
        ("C05", "Summit Foods", "option", -20, "3+", "prime", "Women 25–49", 30, 160_000, 10),
        ("C06", "Glacier Water", "firm", -6, "4+ | 5+ | 6+", "access | prime", "All adults", 20, 400_000, 16),
        ("C07", "Metro Cars", "option", -4, "3+ | 4+ | 5+ | 6+", "late | prime", "All adults", 30, 500_000, 16),
        ("C08", "Tal Pharmacy", "firm", -2, "3+", "day | access", "Women 25–49", 20, 60_000, 12),
    ]
    rows = [
        {
            "request_id": rid,
            "advertiser": name,
            "status": status,
            "booked_on": (day + pd.Timedelta(days=offset)).date().isoformat(),
            "eligible_channels": channels,
            "dayparts": parts,
            "target_group": target,
            "spot_sec": spot,
            "goal_impressions": goal,
            "max_spots": spots,
        }
        for rid, name, status, offset, channels, parts, target, spot, goal, spots in specs
    ]
    return pd.DataFrame(rows)


def grain_check(requests: pd.DataFrame) -> dict:
    """What happens to totals if the channel list is exploded into rows."""
    exploded = requests.assign(channel=requests["eligible_channels"].map(split_list)).explode("channel")
    return {
        "request_rows": len(requests),
        "exploded_rows": len(exploded),
        "true_goal": int(requests["goal_impressions"].sum()),
        "exploded_goal": int(exploded["goal_impressions"].sum()),
        "exploded": exploded,
    }


def order_requests(requests: pd.DataFrame, policy: str) -> pd.DataFrame:
    frame = requests.copy()
    if policy == "firm_first":
        frame["_rank"] = frame["status"].map({"firm": 0, "option": 1}).fillna(2)
        return frame.sort_values(["_rank", "booked_on", "request_id"]).drop(columns="_rank")
    return frame.sort_values(["booked_on", "request_id"])


def allot(
    breaks: pd.DataFrame,
    requests: pd.DataFrame,
    policy: str = "firm_first",
    plan_on: str = "p20",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Place spots break by break. Returns placements, campaign summary, break fill.

    Rules, in the order a planner applies them:
    1. Serve requests in policy order (firm before option, or first come).
    2. Only listed channels and dayparts are eligible.
    3. Listed channel order is preference; inside a channel, larger audience first.
    4. At most one spot per campaign per break, and never past break capacity.
    5. Stop when the planned target audience reaches the goal, or spots run out.
    """
    require_valid(allocation_errors(breaks, requests))
    if policy not in {"firm_first", "first_come"} or plan_on not in {"p20", "p50"}:
        raise ValueError("Unknown allocation policy or planning forecast")
    audience_col = "adults_p20" if plan_on == "p20" else "adults_p50"
    free = dict(zip(breaks["break_id"], breaks["capacity_sec"] - breaks["presold_sec"]))
    placements = []
    summary = []
    for request in order_requests(requests, policy).itertuples(index=False):
        share = TARGET_SHARE[request.target_group]
        channels = split_list(request.eligible_channels)
        parts = split_list(request.dayparts)
        pool = breaks[breaks["channel"].isin(channels) & breaks["daypart"].isin(parts)].copy()
        pool["_pref"] = pool["channel"].map({name: rank for rank, name in enumerate(channels)})
        pool = pool.sort_values(["_pref", audience_col, "air_time", "break_id"], ascending=[True, False, True, True])

        planned = {"p20": 0.0, "p50": 0.0}
        spots = 0
        for slot in pool.itertuples(index=False):
            if planned[plan_on] >= request.goal_impressions or spots >= request.max_spots:
                break
            if free[slot.break_id] < request.spot_sec:
                continue
            free[slot.break_id] -= request.spot_sec
            spots += 1
            p20 = int(slot.adults_p20 * share)
            p50 = int(slot.adults_p50 * share)
            planned["p20"] += p20
            planned["p50"] += p50
            placement = {
                    "request_id": request.request_id,
                    "advertiser": request.advertiser,
                    "status": request.status,
                    "break_id": slot.break_id,
                    "channel": slot.channel,
                    "air_time": slot.air_time,
                    "daypart": slot.daypart,
                    "programme": slot.programme,
                    "spot_sec": request.spot_sec,
                    "target_p20": int(p20),
                    "target_p50": int(p50),
                }
            for field in ["model_name", "forecast_issue_time", "training_cutoff", "calibration_start", "calibration_end", "source_state"]:
                if hasattr(slot, field):
                    placement[field] = getattr(slot, field)
            placements.append(placement)
        goal = request.goal_impressions
        if planned["p20"] >= goal:
            verdict = "covered at P20"
        elif planned["p50"] >= goal:
            verdict = "covered only at P50"
        else:
            verdict = "short"
        summary.append(
            {
                "request_id": request.request_id,
                "advertiser": request.advertiser,
                "status": request.status,
                "target_group": request.target_group,
                "goal": goal,
                "spots": spots,
                "planned_p20": int(planned["p20"]),
                "planned_p50": int(planned["p50"]),
                "gap_p20": int(planned["p20"] - goal),
                "verdict": verdict,
            }
        )

    fill = breaks[
        [
            "break_id",
            "programme_id",
            "channel",
            "air_time",
            "daypart",
            "programme",
            "capacity_sec",
            "presold_sec",
        ]
    ].copy()
    fill["used_sec"] = fill["capacity_sec"] - fill["break_id"].map(free)
    fill["allotted_sec"] = fill["used_sec"] - fill["presold_sec"]
    fill["fill_pct"] = fill["used_sec"] / fill["capacity_sec"]
    metadata = [field for field in ["model_name", "forecast_issue_time", "training_cutoff", "calibration_start", "calibration_end", "source_state"] if field in breaks]
    placement_frame = pd.DataFrame(placements, columns=["request_id", "advertiser", "status", "break_id", "channel", "air_time", "daypart", "programme", "spot_sec", "target_p20", "target_p50"] + metadata)
    summary_frame = pd.DataFrame(summary, columns=["request_id", "advertiser", "status", "target_group", "goal", "spots", "planned_p20", "planned_p50", "gap_p20", "verdict"])
    require_valid(allocation_errors(breaks, requests, placement_frame))
    return placement_frame, summary_frame, fill


def policy_difference(breaks: pd.DataFrame, requests: pd.DataFrame, plan_on: str = "p20") -> pd.DataFrame:
    """Same week, two protection rules. Which requests win or lose spots?"""
    _, firm, _ = allot(breaks, requests, "firm_first", plan_on)
    _, fifo, _ = allot(breaks, requests, "first_come", plan_on)
    merged = firm.merge(fifo, on=["request_id", "advertiser", "status"], suffixes=("_firm_first", "_first_come"))
    merged["spots_change"] = merged["spots_firm_first"] - merged["spots_first_come"]
    return merged[
        [
            "request_id",
            "advertiser",
            "status",
            "spots_first_come",
            "spots_firm_first",
            "spots_change",
            "verdict_first_come",
            "verdict_firm_first",
        ]
    ]


def allocation_trace(breaks, requests, request_id, policy="firm_first", plan_on="p20"):
    """Explain eligible candidates at the moment this campaign is processed."""
    ordered = order_requests(requests, policy).reset_index(drop=True)
    position = int(ordered.index[ordered.request_id == request_id][0])
    request = ordered.iloc[position]
    _, _, prior_fill = allot(breaks, ordered.iloc[:position], policy, plan_on)
    prior = prior_fill.set_index("break_id")
    channels, parts = split_list(request.eligible_channels), split_list(request.dayparts)
    column = "adults_p20" if plan_on == "p20" else "adults_p50"
    pool = breaks[breaks.channel.isin(channels) & breaks.daypart.isin(parts)].copy()
    pool["_pref"] = pool.channel.map({name: rank for rank, name in enumerate(channels)})
    pool = pool.sort_values(["_pref", column, "air_time", "break_id"], ascending=[True, False, True, True])
    total, spots, rows = 0, 0, []
    for rank, slot in enumerate(pool.itertuples(), start=1):
        free = int(prior.loc[slot.break_id, "capacity_sec"] - prior.loc[slot.break_id, "used_sec"])
        audience = int(getattr(slot, column) * TARGET_SHARE[request.target_group])
        if total >= request.goal_impressions:
            reason = "Goal already reached in earlier candidates"
        elif spots >= request.max_spots:
            reason = "Campaign spot limit already reached"
        elif free < request.spot_sec:
            reason = "Not enough seconds when this campaign was considered"
        else:
            reason = "Selected: eligible and enough seconds"
            spots += 1
            total += audience
        rows.append(dict(break_id=slot.break_id, rank=rank, free_seconds_at_decision=free, planned_impressions=audience, reason=reason))
    return pd.DataFrame(rows, columns=["break_id", "rank", "free_seconds_at_decision", "planned_impressions", "reason"])
