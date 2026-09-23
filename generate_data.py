"""Create a tiny synthetic Swiss-like TV inventory world in SQLite.

Frozen shape (do not expand without updating the default demo):
- 2 channels, 2 regions, 2 dayparts, 3 segments, 5 bookings
- Fixed seed so the default Women 25–49 brief always shows SHORT
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(__file__).parent / "inventory_lab.db"
SEED = 7
RNG = np.random.default_rng(SEED)

# Default brief that must stay SHORT after overlap (used by the app).
DEFAULT_BRIEF = {
    "channel": "north_peak",
    "region": "D-CH",
    "daypart": "prime",
    "segment_id": "w_25_49",
    "start_date": "2026-09-22",
    "end_date": "2026-10-02",
    "daily_impressions": 80_000,
    "include_options": True,
}

CHANNELS = [
    ("north_peak", "North Peak", "linear"),
    ("lake_city", "Lake City", "linear"),
]
REGIONS = ["D-CH", "F-CH"]
DAYPARTS = ["daytime", "prime"]
SEGMENTS = [
    ("all_adults", "All adults 15+", None, 1.00),
    ("w_25_49", "Women 25–49", "all_adults", 0.28),
    ("m_25_49", "Men 25–49", "all_adults", 0.26),
]


def _supply_row(day: date, channel: str, region: str, daypart: str) -> dict:
    weekday = day.weekday()
    base = 420_000
    if region == "F-CH":
        base *= 0.42
    if daypart == "prime":
        base *= 1.55
    if weekday >= 5:
        base *= 0.82
    if weekday == 6 and daypart == "prime":
        base *= 0.88  # Sunday prime is systematically over-forecast at P50
    noise = RNG.normal(1.0, 0.06)
    p50 = max(20_000, int(base * noise))
    p20 = int(p50 * 0.78)
    p80 = int(p50 * 1.18)
    actual = int(p50 * RNG.normal(0.97, 0.08))
    if weekday == 6 and daypart == "prime":
        actual = int(actual * 0.86)
    return {
        "date": day.isoformat(),
        "channel": channel,
        "region": region,
        "daypart": daypart,
        "supply_p20": p20,
        "supply_p50": p50,
        "supply_p80": p80,
        "actual_impressions": max(8_000, actual),
    }


def main() -> None:
    start = date(2026, 9, 1)
    days = [start + timedelta(days=i) for i in range(42)]
    supply = [
        _supply_row(day, channel, region, daypart)
        for day in days
        for channel, _, _ in CHANNELS
        for region in REGIONS
        for daypart in DAYPARTS
    ]
    supply_df = pd.DataFrame(supply)

    # Five bookings only. Alpine Bank (women) + Lake Insurance (all adults)
    # collide on North Peak D-CH prime — that is the teaching case.
    bookings = pd.DataFrame(
        [
            {
                "booking_id": "B-100",
                "advertiser": "Alpine Bank",
                "status": "firm",
                "channel": "north_peak",
                "region": "D-CH",
                "daypart": "prime",
                "segment_id": "w_25_49",
                "start_date": "2026-09-15",
                "end_date": "2026-10-05",
                "daily_impressions": 95_000,
                "priority": 1,
            },
            {
                "booking_id": "B-101",
                "advertiser": "Lake Insurance",
                "status": "firm",
                "channel": "north_peak",
                "region": "D-CH",
                "daypart": "prime",
                "segment_id": "all_adults",
                "start_date": "2026-09-20",
                "end_date": "2026-10-02",
                "daily_impressions": 160_000,
                "priority": 2,
            },
            {
                "booking_id": "B-102",
                "advertiser": "City Retail",
                "status": "option",
                "channel": "north_peak",
                "region": "D-CH",
                "daypart": "prime",
                "segment_id": "w_25_49",
                "start_date": "2026-09-22",
                "end_date": "2026-10-12",
                "daily_impressions": 70_000,
                "priority": 3,
            },
            {
                "booking_id": "B-200",
                "advertiser": "Romandie Food",
                "status": "firm",
                "channel": "lake_city",
                "region": "F-CH",
                "daypart": "prime",
                "segment_id": "all_adults",
                "start_date": "2026-09-18",
                "end_date": "2026-10-08",
                "daily_impressions": 55_000,
                "priority": 1,
            },
            {
                "booking_id": "B-201",
                "advertiser": "Daytime Shop",
                "status": "firm",
                "channel": "lake_city",
                "region": "D-CH",
                "daypart": "daytime",
                "segment_id": "w_25_49",
                "start_date": "2026-09-10",
                "end_date": "2026-09-30",
                "daily_impressions": 28_000,
                "priority": 2,
            },
        ]
    )

    segments = pd.DataFrame(
        [
            {"segment_id": sid, "label": label, "parent_id": parent, "share_of_parent": share}
            for sid, label, parent, share in SEGMENTS
        ]
    )
    channels = pd.DataFrame(
        [{"channel": c, "label": label, "product": product} for c, label, product in CHANNELS]
    )

    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    supply_df.to_sql("supply", con, index=False)
    bookings.to_sql("bookings", con, index=False)
    segments.to_sql("segments", con, index=False)
    channels.to_sql("channels", con, index=False)
    con.execute(
        """
        CREATE VIEW booking_days AS
        SELECT b.*, s.date AS date
        FROM bookings b
        JOIN supply s
          ON s.channel = b.channel
         AND s.region = b.region
         AND s.daypart = b.daypart
         AND s.date BETWEEN b.start_date AND b.end_date
        """
    )
    con.commit()
    con.close()
    print(f"Wrote {DB_PATH} ({len(supply_df)} supply rows, {len(bookings)} bookings)")


if __name__ == "__main__":
    main()
