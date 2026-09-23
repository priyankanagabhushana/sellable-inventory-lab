from __future__ import annotations

import io
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from allotment import (  # noqa: E402
    allot,
    build_breaks,
    campaign_requests,
    grain_check,
    policy_difference,
    split_list,
)
from schedule_source import ZURICH, parse_xmltv, synthetic_schedule  # noqa: E402

XMLTV = b"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="3+.ch"><display-name>3+</display-name></channel>
  <programme start="20260921181500 +0000" stop="20260921203000 +0000" channel="3+.ch">
    <title lang="de">Prime film</title>
    <category lang="en">Film</category>
  </programme>
  <programme start="20260921181500 +0000" stop="20260921190000 +0000" channel="SRF1.ch">
    <title lang="de">Not our channel</title>
  </programme>
</tv>
"""


class AllotmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schedule = synthetic_schedule(anchor=datetime(2026, 9, 21, tzinfo=ZURICH))
        cls.breaks = build_breaks(schedule)
        cls.requests = campaign_requests(schedule["start"].min())
        cls.results = {
            (policy, plan): allot(cls.breaks, cls.requests, policy, plan)
            for policy in ("firm_first", "first_come")
            for plan in ("p20", "p50")
        }

    def test_parser_keeps_only_the_four_channels_in_zurich_time(self) -> None:
        grid = parse_xmltv(io.BytesIO(XMLTV))
        self.assertEqual(list(grid["channel"]), ["3+"])
        self.assertEqual(grid.iloc[0]["start"].strftime("%H:%M"), "20:15")
        self.assertEqual(int(grid.iloc[0]["duration_min"]), 135)

    def test_teleshopping_gets_no_breaks_and_presold_fits(self) -> None:
        self.assertFalse((self.breaks["genre"] == "Einkauf").any())
        self.assertTrue((self.breaks["presold_sec"] <= self.breaks["capacity_sec"]).all())
        self.assertFalse(self.breaks["break_id"].duplicated().any())

    def test_no_break_is_overfilled(self) -> None:
        for (_, _), (_, _, fill) in self.results.items():
            self.assertTrue((fill["used_sec"] <= fill["capacity_sec"]).all())
            self.assertTrue((fill["allotted_sec"] >= 0).all())

    def test_only_listed_channels_and_dayparts_are_used(self) -> None:
        lookup = self.requests.set_index("request_id")
        for (_, _), (placements, _, _) in self.results.items():
            for row in placements.itertuples(index=False):
                request = lookup.loc[row.request_id]
                self.assertIn(row.channel, split_list(request.eligible_channels))
                self.assertIn(row.daypart, split_list(request.dayparts))

    def test_one_spot_per_campaign_per_break(self) -> None:
        for (_, _), (placements, _, _) in self.results.items():
            self.assertFalse(placements.duplicated(["request_id", "break_id"]).any())

    def test_spot_limits_are_respected(self) -> None:
        limits = self.requests.set_index("request_id")["max_spots"]
        for (_, _), (_, summary, _) in self.results.items():
            spots = summary.set_index("request_id")["spots"]
            self.assertTrue((spots <= limits.reindex(spots.index)).all())

    def test_firm_first_outcome_does_not_depend_on_options(self) -> None:
        _, with_options, _ = self.results[("firm_first", "p20")]
        firm_only = self.requests[self.requests["status"] == "firm"]
        _, alone, _ = allot(self.breaks, firm_only, "firm_first", "p20")
        columns = ["request_id", "spots", "planned_p20", "verdict"]
        served = with_options[with_options["status"] == "firm"][columns].reset_index(drop=True)
        self.assertTrue(served.equals(alone[columns].reset_index(drop=True)))

    def test_policy_difference_lists_every_request(self) -> None:
        diff = policy_difference(self.breaks, self.requests)
        self.assertEqual(sorted(diff["request_id"]), sorted(self.requests["request_id"]))

    def test_splitting_the_channel_list_inflates_the_goal(self) -> None:
        grain = grain_check(self.requests)
        expected_rows = sum(len(split_list(cell)) for cell in self.requests["eligible_channels"])
        self.assertEqual(grain["exploded_rows"], expected_rows)
        self.assertGreater(grain["exploded_goal"], grain["true_goal"])
        self.assertEqual(grain["exploded"].groupby("request_id")["goal_impressions"].first().sum(), grain["true_goal"])


if __name__ == "__main__":
    unittest.main()
