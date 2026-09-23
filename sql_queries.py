"""Commented SQL proofs for the Learn drawer.

These run against inventory_lab.db. They demonstrate JOIN, GROUP BY, CTE,
window functions, quality checks, and reusable KPI definitions.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 1) Daily remaining on a cell (naive: forecast − sum of bookings)
# Grain: channel × region × daypart × date
# ---------------------------------------------------------------------------
DAILY_REMAINING = """
-- Naive leftover on the whole cell (ignores nested target overlap).
WITH day_booked AS (
  SELECT
    s.date,
    s.channel,
    s.region,
    s.daypart,
    s.supply_p50,
    COALESCE(SUM(b.daily_impressions), 0) AS booked
  FROM supply s
  LEFT JOIN bookings b
    ON b.channel = s.channel
   AND b.region = s.region
   AND b.daypart = s.daypart
   AND s.date BETWEEN b.start_date AND b.end_date
   AND b.status IN ('firm', 'option')
  WHERE s.channel = 'north_peak'
    AND s.region = 'D-CH'
    AND s.daypart = 'prime'
    AND s.date BETWEEN '2026-09-22' AND '2026-10-02'
  GROUP BY s.date, s.channel, s.region, s.daypart, s.supply_p50
)
SELECT
  date,
  supply_p50,
  booked,
  supply_p50 - booked AS naive_remaining
FROM day_booked
ORDER BY date;
"""

# ---------------------------------------------------------------------------
# 2) Overlap-taken for Women 25–49
# A women booking hits 100%. An all-adults booking hits share_of_parent (0.28).
# ---------------------------------------------------------------------------
OVERLAP_TAKEN = """
-- How much of each booking lands in the Women 25–49 pool.
SELECT
  bd.date,
  bd.booking_id,
  bd.advertiser,
  bd.segment_id,
  bd.status,
  bd.daily_impressions,
  CASE
    WHEN bd.segment_id = 'w_25_49' THEN bd.daily_impressions
    WHEN bd.segment_id = 'all_adults' THEN CAST(bd.daily_impressions * 0.28 AS INTEGER)
    ELSE 0
  END AS hits_women_pool
FROM booking_days bd
WHERE bd.channel = 'north_peak'
  AND bd.region = 'D-CH'
  AND bd.daypart = 'prime'
  AND bd.date BETWEEN '2026-09-22' AND '2026-10-02'
  AND bd.status IN ('firm', 'option')
ORDER BY bd.date, bd.priority;
"""

# ---------------------------------------------------------------------------
# 3) Weekday bias: actual − P50 (Sunday prime is systematically light)
# ---------------------------------------------------------------------------
WEEKDAY_BIAS = """
-- Forecast error by weekday. Negative = over-forecast (dangerous for selling).
SELECT
  CASE CAST(strftime('%w', date) AS INTEGER)
    WHEN 0 THEN 'Sunday'
    WHEN 1 THEN 'Monday'
    WHEN 2 THEN 'Tuesday'
    WHEN 3 THEN 'Wednesday'
    WHEN 4 THEN 'Thursday'
    WHEN 5 THEN 'Friday'
    WHEN 6 THEN 'Saturday'
  END AS weekday,
  ROUND(AVG(actual_impressions - supply_p50)) AS avg_error_p50,
  ROUND(AVG(actual_impressions - supply_p20)) AS avg_error_p20,
  COUNT(*) AS n_days
FROM supply
WHERE channel = 'north_peak'
  AND region = 'D-CH'
  AND daypart = 'prime'
GROUP BY strftime('%w', date)
ORDER BY CAST(strftime('%w', date) AS INTEGER);
"""

# Optional: 7-day moving average of actuals (window function proof).
MOVING_AVG = """
SELECT
  date,
  actual_impressions,
  ROUND(AVG(actual_impressions) OVER (
    ORDER BY date
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
  )) AS actual_7d_avg
FROM supply
WHERE channel = 'north_peak'
  AND region = 'D-CH'
  AND daypart = 'prime'
ORDER BY date;
"""

# ---------------------------------------------------------------------------
# 5) Data-quality check: the supply business key must be unique
# ---------------------------------------------------------------------------
GRAIN_QUALITY = """
-- A result row means the source has duplicate supply at the expected grain.
SELECT
  date,
  channel,
  region,
  daypart,
  COUNT(*) AS row_count
FROM supply
GROUP BY date, channel, region, daypart
HAVING COUNT(*) > 1;
"""

# ---------------------------------------------------------------------------
# 6) BI-style KPI query: one governed definition, reusable by every chart
# ---------------------------------------------------------------------------
BI_KPIS = """
-- KPI layer for one filtered cell. Negative bias = forecast was too high.
SELECT
  channel,
  region,
  daypart,
  COUNT(*) AS days,
  ROUND(AVG(supply_p50)) AS avg_forecast_p50,
  ROUND(AVG(actual_impressions)) AS avg_actual,
  ROUND(AVG(actual_impressions - supply_p50)) AS forecast_bias,
  ROUND(
    SUM(ABS(actual_impressions - supply_p50)) * 1.0
    / NULLIF(SUM(actual_impressions), 0),
    4
  ) AS forecast_wape
FROM supply
WHERE channel = 'north_peak'
  AND region = 'D-CH'
  AND daypart = 'prime'
GROUP BY channel, region, daypart;
"""

QUERIES = {
    "Daily remaining (naive)": DAILY_REMAINING,
    "Overlap into Women 25–49": OVERLAP_TAKEN,
    "Weekday forecast bias": WEEKDAY_BIAS,
    "7-day moving average (window function)": MOVING_AVG,
    "Data-quality check: duplicate grain": GRAIN_QUALITY,
    "BI KPI layer": BI_KPIS,
}
