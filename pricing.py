"""Transparent synthetic price scenarios for the learning lab."""
from __future__ import annotations

import numpy as np
import pandas as pd


def price_scenarios(
    sellable_impressions: int,
    demand_at_reference_price: int,
    reference_cpm: float = 60.0,
    elasticity: float = 1.4,
    floor_cpm: float = 40.0,
    ceiling_cpm: float = 100.0,
    step: float = 2.0,
) -> pd.DataFrame:
    """Estimate demand, sold impressions, and revenue for candidate CPMs.

    This is a teaching curve, not a market-calibrated price model. Demand falls
    as price rises; sales cannot exceed safely sellable inventory.
    """
    if sellable_impressions < 0 or demand_at_reference_price < 0:
        raise ValueError("Supply and demand must be non-negative")
    if reference_cpm <= 0 or floor_cpm <= 0 or ceiling_cpm < floor_cpm:
        raise ValueError("Invalid CPM limits")
    prices = np.arange(floor_cpm, ceiling_cpm + step / 2, step, dtype=float)
    rows = []
    for cpm in prices:
        demand = demand_at_reference_price * (reference_cpm / cpm) ** elasticity
        sold = min(float(sellable_impressions), float(demand))
        rows.append(
            {
                "cpm": cpm,
                "expected_demand": demand,
                "sold_impressions": sold,
                "unused_inventory": max(float(sellable_impressions) - sold, 0.0),
                "expected_revenue": sold / 1000.0 * cpm,
            }
        )
    return pd.DataFrame(rows)


def recommend_price(scenarios: pd.DataFrame) -> dict[str, float]:
    if scenarios.empty:
        raise ValueError("No price scenarios are available")
    winner = scenarios.loc[scenarios["expected_revenue"].idxmax()]
    return {key: float(winner[key]) for key in scenarios.columns}
