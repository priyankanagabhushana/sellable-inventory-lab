from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forecast_workbench import (  # noqa: E402
    evaluate_models,
    generate_history,
    interval_coverage,
    uncertainty_for_row,
)
from learning_data import (  # noqa: E402
    SQL_EXAMPLES,
    data_quality_report,
    run_sql_example,
    stable_case,
)
from schedule_source import load_schedule, stable_demo_schedule  # noqa: E402


class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case = stable_case()
        cls.artifacts = evaluate_models()

    def test_stable_demo_is_reproducible_and_has_unique_programme_keys(self) -> None:
        first = stable_demo_schedule()
        second = stable_demo_schedule()
        self.assertTrue(first.equals(second))
        self.assertFalse(first["programme_id"].duplicated().any())

    def test_default_schedule_does_not_require_network(self) -> None:
        with patch("schedule_source.urllib.request.urlopen", side_effect=AssertionError("network used")):
            schedule, source = load_schedule()
        self.assertFalse(schedule.empty)
        self.assertIn("fictional", source.lower())

    def test_failed_optional_refresh_falls_back_without_breaking(self) -> None:
        with patch("schedule_source.fetch_schedule", side_effect=OSError("offline")):
            schedule, source = load_schedule(refresh=True, allow_remote=True)
        self.assertFalse(schedule.empty)
        self.assertIn("refresh failed", source.lower())

    def test_data_quality_contracts_pass(self) -> None:
        report = data_quality_report(
            self.case["programmes"],
            self.case["breaks"],
            self.case["requests"],
            self.case["placements"],
        )
        self.assertTrue((report["status"] == "PASS").all())

    def test_campaign_goal_sql_returns_one_row_per_campaign(self) -> None:
        result = run_sql_example(self.case, SQL_EXAMPLES["Campaign delivery counted once"])
        self.assertEqual(len(result), len(self.case["requests"]))
        self.assertFalse(result["request_id"].duplicated().any())

    def test_history_and_metrics_are_reproducible(self) -> None:
        first = generate_history()
        second = generate_history()
        self.assertTrue(first.equals(second))
        again = evaluate_models(first)
        pd.testing.assert_frame_equal(self.artifacts.metrics, again.metrics)

    def test_time_split_has_no_future_leakage(self) -> None:
        dates = self.artifacts.split_dates
        self.assertLess(dates.train_end, dates.validation_end)
        self.assertLess(dates.validation_end, dates.test_end)
        test_dates = self.artifacts.predictions["date"]
        self.assertTrue((test_dates > dates.validation_end).all())
        self.assertEqual(self.artifacts.training_cutoff, dates.train_end)

    def test_forecast_metrics_are_finite(self) -> None:
        metrics = self.artifacts.metrics
        self.assertEqual(set(metrics["model"]), {"seasonal_naive", "rolling_average", "linear_regression", "xgboost"})
        self.assertFalse(metrics[["mae", "wape", "bias"]].isna().any().any())
        self.assertTrue((metrics["mae"] >= 0).all())
        self.assertTrue((metrics["wape"] >= 0).all())

    def test_uncertainty_bands_are_ordered(self) -> None:
        row = self.artifacts.predictions[self.artifacts.predictions["model"] == "xgboost"].iloc[0]
        bands = uncertainty_for_row(row, self.artifacts.residual_quantiles)
        self.assertLessEqual(bands["calibrated_p20"], bands["p50"])
        self.assertLessEqual(bands["p50"], bands["calibrated_p80"])

    def test_interval_coverage_is_a_probability(self) -> None:
        coverage = interval_coverage(self.artifacts)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in coverage.values()))
        self.assertLessEqual(coverage["below_p20"], coverage["below_p80"])


if __name__ == "__main__":
    unittest.main()
