"""Run the learning pipeline: quality checks, forecast backtest, BI exports.

This is intentionally a small local orchestrator. In production the same
steps could be tasks in Airflow, Prefect, or Dagster.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

from availability import Brief, allocate
from forecasting import best_model, cell_history, forecast_metrics, rolling_backtest
from generate_data import DB_PATH, main as rebuild

ROOT = Path(__file__).parent
BI_DIR = ROOT / "bi_exports"


def load_tables() -> dict[str, pd.DataFrame]:
    if not DB_PATH.exists():
        rebuild()
    connection = sqlite3.connect(DB_PATH)
    try:
        return {
            name: pd.read_sql(f"SELECT * FROM {name}", connection)
            for name in ("supply", "bookings", "segments", "channels")
        }
    finally:
        connection.close()


def data_quality_checks(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    supply = tables["supply"]
    bookings = tables["bookings"]
    segments = tables["segments"]
    channels = tables["channels"]
    grain = ["date", "channel", "region", "daypart"]
    known_segments = set(segments["segment_id"])
    known_channels = set(channels["channel"])
    checks = [
        ("Unique supply grain", not supply.duplicated(grain).any(), "One row per date × channel × region × daypart"),
        ("Forecast bands ordered", bool(((supply.supply_p20 <= supply.supply_p50) & (supply.supply_p50 <= supply.supply_p80)).all()), "P20 ≤ P50 ≤ P80"),
        ("Positive supply", bool((supply[["supply_p20", "supply_p50", "supply_p80"]] >= 0).all().all()), "No negative forecast inputs"),
        ("Booking dates valid", bool((bookings.start_date <= bookings.end_date).all()), "Start date is not after end date"),
        ("Booking channels known", set(bookings.channel).issubset(known_channels), "Every booking maps to a channel dimension"),
        ("Booking segments known", set(bookings.segment_id).issubset(known_segments), "Every booking maps to a segment dimension"),
    ]
    return pd.DataFrame(
        [{"check": name, "passed": passed, "rule": rule} for name, passed, rule in checks]
    )


def inventory_mart(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Create a BI-ready daily fact table for all cells and target segments."""
    supply = tables["supply"]
    bookings = tables["bookings"]
    segments = tables["segments"]
    rows = []
    segment_shares = dict(zip(segments.segment_id, segments.share_of_parent))
    for cell in supply.itertuples(index=False):
        for segment_id in segments.segment_id:
            brief = Brief(
                channel=cell.channel,
                region=cell.region,
                daypart=cell.daypart,
                segment_id=segment_id,
                start_date=cell.date,
                end_date=cell.date,
                daily_impressions=0,
                include_options=True,
            )
            allocated = allocate(supply, bookings, segments, brief).iloc[0]
            share = 1.0 if segment_id == "all_adults" else float(segment_shares[segment_id])
            actual_matched = int(round(float(cell.actual_impressions) * share))
            rows.append(
                {
                    "date": cell.date,
                    "channel": cell.channel,
                    "region": cell.region,
                    "daypart": cell.daypart,
                    "segment_id": segment_id,
                    "forecast_p20": int(allocated.matched_p20),
                    "forecast_p50": int(allocated.matched_p50),
                    "actual_impressions": actual_matched,
                    "forecast_error": actual_matched - int(allocated.matched_p50),
                    "overlap_commitments": int(allocated.overlap_taken),
                    "sellable_p20": int(allocated.sellable_p20),
                    "sellable_p50": int(allocated.sellable_p50),
                }
            )
    return pd.DataFrame(rows)


def export_bi_tables(tables: dict[str, pd.DataFrame]) -> list[Path]:
    BI_DIR.mkdir(exist_ok=True)
    supply = tables["supply"].copy()
    dates = pd.to_datetime(supply["date"]).drop_duplicates().sort_values()
    dim_date = pd.DataFrame(
        {
            "date": dates.dt.strftime("%Y-%m-%d"),
            "weekday": dates.dt.day_name(),
            "week": dates.dt.isocalendar().week.astype(int),
            "is_weekend": dates.dt.weekday >= 5,
        }
    )
    exports = {
        "fact_inventory_daily.csv": inventory_mart(tables),
        "fact_booking_daily.csv": _booking_days(),
        "dim_date.csv": dim_date,
        "dim_channel.csv": tables["channels"],
        "dim_segment.csv": tables["segments"],
    }
    paths = []
    for filename, frame in exports.items():
        path = BI_DIR / filename
        frame.to_csv(path, index=False)
        paths.append(path)
    return paths


def _booking_days() -> pd.DataFrame:
    connection = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql("SELECT * FROM booking_days", connection)
    finally:
        connection.close()


def run_pipeline(rebuild_data: bool = False, export: bool = True) -> dict[str, object]:
    if rebuild_data or not DB_PATH.exists():
        rebuild()
    tables = load_tables()
    checks = data_quality_checks(tables)
    history = cell_history(tables["supply"], "north_peak", "D-CH", "prime")
    backtest = rolling_backtest(history)
    metrics = forecast_metrics(backtest)
    paths = export_bi_tables(tables) if export else []
    return {
        "checks": checks,
        "all_checks_pass": bool(checks.passed.all()),
        "forecast_metrics": metrics,
        "best_model": best_model(metrics),
        "exports": paths,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Sellable learning pipeline")
    parser.add_argument("--rebuild", action="store_true", help="Recreate the synthetic SQLite data")
    parser.add_argument("--no-export", action="store_true", help="Skip BI CSV exports")
    args = parser.parse_args()
    result = run_pipeline(rebuild_data=args.rebuild, export=not args.no_export)
    print("\nDATA QUALITY")
    print(result["checks"].to_string(index=False))
    print("\nFORECAST BACKTEST")
    print(result["forecast_metrics"].to_string(index=False, formatters={"wape": "{:.1%}".format}))
    print(f"\nBest synthetic backtest model: {result['best_model']}")
    if result["exports"]:
        print("\nBI EXPORTS")
        for path in result["exports"]:
            print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
