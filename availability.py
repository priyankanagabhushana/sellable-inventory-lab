"""Availability: naive subtraction vs overlapping target pools."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Brief:
    channel: str
    region: str
    daypart: str
    segment_id: str
    start_date: str
    end_date: str
    daily_impressions: int
    include_options: bool = True


def _share(segments: pd.DataFrame, child: str, ancestor: str) -> float:
    if child == ancestor:
        return 1.0
    row = segments.loc[segments["segment_id"] == child]
    if row.empty:
        return 0.0
    parent = row.iloc[0]["parent_id"]
    share = float(row.iloc[0]["share_of_parent"])
    if parent == ancestor:
        return share
    if parent is None or (isinstance(parent, float) and pd.isna(parent)):
        return 0.0
    return share * _share(segments, str(parent), ancestor)


def booking_hit(segments: pd.DataFrame, brief_seg: str, booking_seg: str) -> float:
    """How much of a booking's impressions land in the brief's pool.

    If the booking is the same or narrower, all of it contends.
    If the booking is broader, only the nested share contends.
    """
    if brief_seg == booking_seg:
        return 1.0
    if _share(segments, booking_seg, brief_seg) > 0:
        return 1.0
    nested = _share(segments, brief_seg, booking_seg)
    return nested if nested > 0 else 0.0


def cell_frame(supply: pd.DataFrame, brief: Brief) -> pd.DataFrame:
    mask = (
        (supply["channel"] == brief.channel)
        & (supply["region"] == brief.region)
        & (supply["daypart"] == brief.daypart)
        & (supply["date"] >= brief.start_date)
        & (supply["date"] <= brief.end_date)
    )
    return supply.loc[mask].copy()


def allocate(
    supply: pd.DataFrame,
    bookings: pd.DataFrame,
    segments: pd.DataFrame,
    brief: Brief,
) -> pd.DataFrame:
    cells = cell_frame(supply, brief)
    if cells.empty:
        return cells

    status_ok = ["firm"]
    if brief.include_options:
        status_ok.append("option")
    live = bookings.loc[bookings["status"].isin(status_ok)].copy()

    rows = []
    for _, cell in cells.iterrows():
        day = cell["date"]
        day_bookings = live.loc[
            (live["channel"] == brief.channel)
            & (live["region"] == brief.region)
            & (live["daypart"] == brief.daypart)
            & (live["start_date"] <= day)
            & (live["end_date"] >= day)
        ]
        naive_taken = int(day_bookings["daily_impressions"].sum()) if len(day_bookings) else 0
        overlap_taken = 0.0
        contenders = []
        for _, book in day_bookings.iterrows():
            factor = booking_hit(segments, brief.segment_id, book["segment_id"])
            take = factor * float(book["daily_impressions"])
            if take > 0:
                overlap_taken += take
                contenders.append(f"{book['booking_id']} · {book['advertiser']} ({book['status']})")
        brief_share = 1.0 if brief.segment_id == "all_adults" else _share(segments, brief.segment_id, "all_adults")
        matched_p50 = int(cell["supply_p50"] * brief_share)
        matched_p20 = int(cell["supply_p20"] * brief_share)
        # Optimistic naive: leftover on the whole cell, ignoring nested targets.
        naive_left = int(cell["supply_p50"]) - naive_taken
        overlap_left_p50 = matched_p50 - overlap_taken
        overlap_left_p20 = matched_p20 - overlap_taken
        rows.append(
            {
                "date": day,
                "matched_p50": matched_p50,
                "matched_p20": matched_p20,
                "naive_taken": naive_taken,
                "overlap_taken": int(overlap_taken),
                "naive_remaining": naive_left,
                "sellable_p50": int(overlap_left_p50),
                "sellable_p20": int(overlap_left_p20),
                "brief_need": brief.daily_impressions,
                "p50_covers_brief": overlap_left_p50 >= brief.daily_impressions,
                "p20_covers_brief": overlap_left_p20 >= brief.daily_impressions,
                "contenders": " | ".join(contenders) if contenders else "none",
            }
        )
    return pd.DataFrame(rows)


def summarise(daily: pd.DataFrame, brief: Brief) -> dict:
    if daily.empty:
        return {
            "days": 0,
            "status": "EMPTY",
            "verdict": "No matching supply cells for this brief.",
            "reason": "Change channel, region, daypart, or dates.",
        }
    days_p20_short = int((~daily["p20_covers_brief"]).sum())
    days_p50_short = int((~daily["p50_covers_brief"]).sum())
    min_p20 = int(daily["sellable_p20"].min())
    min_p50 = int(daily["sellable_p50"].min())
    min_naive = int(daily["naive_remaining"].min())

    if days_p50_short > 0 or min_p50 < 0:
        status = "SHORT"
        verdict = "Do not book. Sellable inventory on this target is already short."
        reason = (
            "Naive leftover on the whole cell can look healthy while the "
            "target pool is exhausted — broad All-adults bookings share "
            "viewers with Women 25–49."
        )
    elif days_p20_short > 0:
        status = "TIGHT"
        verdict = "Typical forecast (P50) covers the brief, but conservative P20 does not."
        reason = (
            "Audience may come in light (e.g. Sunday prime). Hold a buffer "
            "or shrink the brief before confirming."
        )
    else:
        status = "SELLABLE"
        verdict = "Conservative forecast (P20) still covers the brief."
        reason = "Booking is conservative-safe in this synthetic lab."

    contenders = sorted(
        {
            part.strip()
            for cell in daily["contenders"]
            for part in str(cell).split("|")
            if part.strip() and part.strip() != "none"
        }
    )
    return {
        "days": len(daily),
        "need_total": brief.daily_impressions * len(daily),
        "min_sellable_p20": min_p20,
        "min_sellable_p50": min_p50,
        "min_naive": min_naive,
        "days_p20_short": days_p20_short,
        "days_p50_short": days_p50_short,
        "status": status,
        "verdict": verdict,
        "reason": reason,
        "contenders": contenders,
    }


def worst_day_breakdown(
    daily: pd.DataFrame,
    bookings: pd.DataFrame,
    segments: pd.DataFrame,
    brief: Brief,
) -> dict:
    """Slices for pie charts on the tightest day (lowest overlap-aware P50)."""
    if daily.empty:
        return {}
    row = daily.loc[daily["sellable_p50"].idxmin()]
    day = str(row["date"])
    status_ok = ["firm"]
    if brief.include_options:
        status_ok.append("option")
    day_bookings = bookings.loc[
        (bookings["channel"] == brief.channel)
        & (bookings["region"] == brief.region)
        & (bookings["daypart"] == brief.daypart)
        & (bookings["start_date"] <= day)
        & (bookings["end_date"] >= day)
        & (bookings["status"].isin(status_ok))
    ]
    leftover = max(int(row["sellable_p50"]), 0)
    slices = []
    for _, book in day_bookings.iterrows():
        hit = booking_hit(segments, brief.segment_id, str(book["segment_id"]))
        take = hit * float(book["daily_impressions"])
        if take <= 0:
            continue
        slices.append(
            {
                "label": f"{book['advertiser']} ({book['status']})",
                "impressions": int(take),
            }
        )
    slices.sort(key=lambda s: s["impressions"], reverse=True)
    if leftover > 0:
        slices.append({"label": "Still free in this pool", "impressions": leftover})
    return {
        "date": day,
        "matched_p50": int(row["matched_p50"]),
        "matched_p20": int(row["matched_p20"]),
        "naive_taken": int(row["naive_taken"]),
        "naive_remaining": int(row["naive_remaining"]),
        "sellable_p50": int(row["sellable_p50"]),
        "sellable_p20": int(row["sellable_p20"]),
        "brief_need": int(row["brief_need"]),
        "overlap_taken": int(row["overlap_taken"]),
        "slices": slices,
        "oversold_by": max(-int(row["sellable_p50"]), 0),
    }
