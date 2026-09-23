"""Small, dependency-light forecasting models for the learning lab.

The goal is not to crown a production model. It is to demonstrate the
professional workflow: establish baselines, use rolling time splits, compare
error *and* bias, and add complexity only when it earns its place.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


MODEL_LABELS = {
    "seasonal_naive": "Seasonal naive (same weekday)",
    "moving_average": "7-day moving average",
    "trend_weekday": "Trend + weekday regression",
    "ar_lag": "AR-style lag regression",
}

MODEL_EXPLANATIONS = {
    "seasonal_naive": (
        "Uses the actual audience from seven days earlier. This is the first "
        "baseline a more advanced model should beat."
    ),
    "moving_average": (
        "Averages the previous seven actual values. It smooths noise but can "
        "react slowly when the audience changes."
    ),
    "trend_weekday": (
        "Fits a simple line for growth or decline and a separate adjustment "
        "for each weekday. This is explainable feature-based modelling."
    ),
    "ar_lag": (
        "Uses yesterday and the same weekday last week. This demonstrates the "
        "autoregressive idea used inside ARIMA without claiming to be full ARIMA."
    ),
}


def cell_history(
    supply: pd.DataFrame,
    channel: str,
    region: str,
    daypart: str,
) -> pd.DataFrame:
    """Return one ordered time series at one explicit business grain."""
    mask = (
        (supply["channel"] == channel)
        & (supply["region"] == region)
        & (supply["daypart"] == daypart)
    )
    frame = supply.loc[mask].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.sort_values("date").reset_index(drop=True)


def _weekday_design(dates: pd.Series, positions: np.ndarray) -> np.ndarray:
    weekday = pd.to_datetime(dates).dt.weekday.to_numpy()
    columns = [np.ones(len(dates)), positions]
    columns.extend((weekday == day).astype(float) for day in range(1, 7))
    return np.column_stack(columns)


def _trend_weekday_prediction(history: pd.DataFrame, target_date: pd.Timestamp) -> float:
    positions = np.arange(len(history), dtype=float)
    x_train = _weekday_design(history["date"], positions)
    y_train = history["actual_impressions"].to_numpy(dtype=float)
    coefficients, *_ = np.linalg.lstsq(x_train, y_train, rcond=None)
    target = pd.Series([target_date])
    x_target = _weekday_design(target, np.array([float(len(history))]))
    return float((x_target @ coefficients)[0])


def _ar_lag_prediction(history: pd.DataFrame) -> float:
    """One-step AR-style regression using lag 1 and lag 7.

    Rolling evaluation uses only actual values known before the prediction
    date. That prevents future leakage.
    """
    actual = history["actual_impressions"].to_numpy(dtype=float)
    if len(actual) < 14:
        return float(actual[-7])
    rows = []
    targets = []
    for index in range(7, len(actual)):
        rows.append([1.0, actual[index - 1], actual[index - 7]])
        targets.append(actual[index])
    coefficients, *_ = np.linalg.lstsq(
        np.asarray(rows, dtype=float), np.asarray(targets, dtype=float), rcond=None
    )
    return float(np.array([1.0, actual[-1], actual[-7]]) @ coefficients)


def rolling_backtest(history: pd.DataFrame, test_days: int = 14) -> pd.DataFrame:
    """Compare four models on the final days using rolling-origin backtests."""
    if len(history) < 21:
        raise ValueError("At least 21 ordered observations are required")
    start = max(14, len(history) - test_days)
    rows: list[dict[str, object]] = []
    for index in range(start, len(history)):
        train = history.iloc[:index]
        actual = float(history.iloc[index]["actual_impressions"])
        target_date = pd.Timestamp(history.iloc[index]["date"])
        predictions = {
            "seasonal_naive": float(train.iloc[-7]["actual_impressions"]),
            "moving_average": float(train.tail(7)["actual_impressions"].mean()),
            "trend_weekday": _trend_weekday_prediction(train, target_date),
            "ar_lag": _ar_lag_prediction(train),
        }
        for model, prediction in predictions.items():
            prediction = max(0.0, prediction)
            rows.append(
                {
                    "date": target_date,
                    "model": model,
                    "model_label": MODEL_LABELS[model],
                    "actual": actual,
                    "prediction": prediction,
                    "error_actual_minus_forecast": actual - prediction,
                }
            )
    return pd.DataFrame(rows)


def forecast_metrics(backtest: pd.DataFrame) -> pd.DataFrame:
    """Return model metrics where negative bias means systematic over-forecast."""
    rows = []
    for model, group in backtest.groupby("model", sort=False):
        actual = group["actual"].to_numpy(dtype=float)
        prediction = group["prediction"].to_numpy(dtype=float)
        error = actual - prediction
        denominator = max(float(np.abs(actual).sum()), 1.0)
        rows.append(
            {
                "model": model,
                "model_label": MODEL_LABELS[str(model)],
                "mae": float(np.abs(error).mean()),
                "wape": float(np.abs(error).sum() / denominator),
                "bias": float(error.mean()),
                "rmse": float(np.sqrt(np.mean(np.square(error)))),
            }
        )
    return pd.DataFrame(rows).sort_values(["wape", "mae"]).reset_index(drop=True)


def best_model(metrics: pd.DataFrame) -> str:
    if metrics.empty:
        raise ValueError("No forecast metrics are available")
    return str(metrics.iloc[0]["model"])
