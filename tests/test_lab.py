from __future__ import annotations

import sqlite3
import sys
import unittest
from contextlib import closing
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from availability import Brief, allocate, summarise  # noqa: E402
from forecasting import cell_history, forecast_metrics, rolling_backtest  # noqa: E402
from generate_data import DEFAULT_BRIEF, DB_PATH, main as rebuild  # noqa: E402
from pipeline import data_quality_checks, inventory_mart, load_tables  # noqa: E402
from pricing import price_scenarios, recommend_price  # noqa: E402


class SellableLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rebuild()
        cls.tables = load_tables()

    def test_default_brief_is_short_after_overlap(self) -> None:
        brief = Brief(**DEFAULT_BRIEF)
        daily = allocate(
            self.tables["supply"], self.tables["bookings"], self.tables["segments"], brief
        )
        result = summarise(daily, brief)
        self.assertEqual(result["status"], "SHORT")
        self.assertGreater(result["min_naive"], 0)
        self.assertLess(result["min_sellable_p50"], 0)

    def test_quality_gate_passes_synthetic_fixture(self) -> None:
        checks = data_quality_checks(self.tables)
        self.assertTrue(bool(checks.passed.all()))

    def test_rolling_backtest_has_all_models_and_finite_metrics(self) -> None:
        history = cell_history(self.tables["supply"], "north_peak", "D-CH", "prime")
        backtest = rolling_backtest(history)
        metrics = forecast_metrics(backtest)
        self.assertEqual(len(metrics), 4)
        self.assertTrue((metrics.wape >= 0).all())
        self.assertFalse(metrics[["mae", "wape", "bias", "rmse"]].isna().any().any())

    def test_pricing_never_sells_more_than_safe_supply(self) -> None:
        scenarios = price_scenarios(200_000, 300_000)
        self.assertTrue((scenarios.sold_impressions <= 200_000).all())
        winner = recommend_price(scenarios)
        self.assertGreater(winner["expected_revenue"], 0)

    def test_bi_mart_has_expected_grain(self) -> None:
        mart = inventory_mart(self.tables)
        grain = ["date", "channel", "region", "daypart", "segment_id"]
        self.assertFalse(mart.duplicated(grain).any())
        self.assertEqual(len(mart), len(self.tables["supply"]) * len(self.tables["segments"]))

    def test_sqlite_database_is_readable(self) -> None:
        with closing(sqlite3.connect(DB_PATH)) as connection:
            count = pd.read_sql("SELECT COUNT(*) AS n FROM supply", connection).iloc[0].n
        self.assertEqual(int(count), 336)


if __name__ == "__main__":
    unittest.main()
