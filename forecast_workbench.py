"""One-week-ahead forecasting on the fictional slots used by allocation."""
from __future__ import annotations

import json
from dataclasses import dataclass
import numpy as np
import pandas as pd
from xgboost import XGBRegressor, DMatrix
from allotment import build_breaks
from schedule_source import synthetic_schedule, stable_demo_schedule

SEED = 27
MODEL_LABELS = {"seasonal_naive": "Same slot last week", "rolling_average": "Four-week average", "linear_regression": "Linear regression", "xgboost": "XGBoost"}
NUMERIC = ["weekday", "hour", "week_index", "lag_1_week", "rolling_4_week", "recent_trend"]


@dataclass(frozen=True)
class SplitDates:
    train_end: pd.Timestamp
    validation_end: pd.Timestamp
    test_end: pd.Timestamp


@dataclass
class ForecastArtifacts:
    history: pd.DataFrame
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    split_dates: SplitDates
    training_cutoff: pd.Timestamp
    calibration_start: pd.Timestamp
    residual_quantiles: tuple[float, float, float]
    calibration_quantiles: dict
    model: object
    models: dict
    feature_columns: list[str]
    validation_predictions: pd.DataFrame


def week_start(times):
    """Local calendar arithmetic preserves midnight across clock changes."""
    return times.map(lambda t: t.normalize() - pd.DateOffset(days=t.weekday()))


def add_history_features(raw):
    frame = raw.sort_values(["slot_key", "date"]).copy()
    groups = frame.groupby("slot_key", sort=False)["actual_audience"]
    frame["lag_1_week"] = groups.shift(1)
    frame["rolling_4_week"] = groups.transform(lambda s: s.shift(1).rolling(4).mean())
    frame["recent_trend"] = groups.shift(1) - groups.shift(4)
    frame["forecast_issue_time"] = week_start(frame["date"])
    frame["feature_available_at"] = frame.groupby("slot_key")["date"].shift(1)
    frame = frame.dropna(subset=["lag_1_week", "rolling_4_week", "recent_trend"])
    if not (frame.feature_available_at < frame.forecast_issue_time).all():
        raise ValueError("A feature was unavailable when the forecast was issued")
    return frame.sort_values(["date", "channel", "break_id"]).reset_index(drop=True)


def generate_history(weeks=36, seed=SEED, with_features=True):
    """Same schedule, categories and audience formula as the demonstration."""
    start = stable_demo_schedule().start.min().normalize() - pd.DateOffset(weeks=weeks)
    rng, frames = np.random.default_rng(seed), []
    for week in range(weeks):
        schedule = synthetic_schedule(anchor=(start + pd.DateOffset(weeks=week)).to_pydatetime())
        slots = build_breaks(schedule)
        frame = slots[["break_id", "slot_key", "channel", "daypart", "genre", "air_time"]].rename(columns={"air_time": "date"})
        frame["weekday"], frame["hour"], frame["week_index"] = frame.date.dt.weekday, frame.date.dt.hour, week
        frame["actual_audience"] = np.maximum(100, np.rint(slots.adults_p50 * rng.normal(1, .025, len(slots)))).astype(int)
        frames.append(frame)
    raw = pd.concat(frames, ignore_index=True)
    return add_history_features(raw) if with_features else raw


def split_history(history):
    weeks = sorted(history.week_index.unique())
    n, c = max(12, int(len(weeks) * .70)), max(4, int(len(weeks) * .15))
    train = history[history.week_index.isin(weeks[:n])].copy()
    calibration = history[history.week_index.isin(weeks[n:n+c])].copy()
    test = history[history.week_index.isin(weeks[n+c:])].copy()
    if min(len(train), len(calibration), len(test)) == 0:
        raise ValueError("History needs non-empty train, calibration and test periods")
    return train, calibration, test, SplitDates(train.date.max(), calibration.date.max(), test.date.max())


def design(frame, columns=None):
    numeric = frame[NUMERIC].reset_index(drop=True)
    categorical = pd.get_dummies(frame[["channel", "daypart", "genre"]], dtype=float).reset_index(drop=True)
    matrix = pd.concat([numeric, categorical], axis=1)
    columns = list(matrix.columns) if columns is None else columns
    return matrix.reindex(columns=columns, fill_value=0).astype(float), columns


def predict_raw(frame, model_name, models, columns):
    if model_name == "seasonal_naive":
        return frame.lag_1_week.to_numpy(dtype=float)
    if model_name == "rolling_average":
        return frame.rolling_4_week.to_numpy(dtype=float)
    matrix, _ = design(frame, columns)
    if model_name == "linear_regression":
        return np.column_stack([np.ones(len(matrix)), matrix.to_numpy()]) @ models[model_name]
    return models[model_name].predict(matrix).astype(float)


def bands_for_predictions(predictions, quantiles):
    q20, q50, q80 = quantiles
    if not q20 <= q50 <= q80:
        raise ValueError("Residual quantiles must be ordered")
    return np.maximum(np.asarray(predictions)[:, None] + np.array([q20, q50, q80]), 0)


def evaluate_models(history=None):
    history = generate_history() if history is None else history.copy()
    train, calibration, test, dates = split_history(history)
    matrix, columns = design(train)
    linear, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(matrix)), matrix.to_numpy()]), train.actual_audience, rcond=None)
    xgb = XGBRegressor(n_estimators=120, max_depth=3, learning_rate=.055, subsample=.9, colsample_bytree=.9, objective="reg:squarederror", importance_type="gain", random_state=SEED, n_jobs=1)
    xgb.fit(matrix, train.actual_audience)
    models = {"linear_regression": linear, "xgboost": xgb}
    quantiles, results, calibration_results, metrics = {}, [], [], []
    for name in MODEL_LABELS:
        cal = calibration.copy()
        cal["prediction"] = predict_raw(cal, name, models, columns)
        residuals = cal.actual_audience - cal.prediction
        quantiles[name] = tuple(float(q) for q in np.quantile(residuals, [.2, .5, .8]))
        cal["model"] = name
        calibration_results.append(cal)
        result = test.copy()
        result["prediction"] = predict_raw(test, name, models, columns)
        result[["p20", "p50", "p80"]] = bands_for_predictions(result.prediction, quantiles[name])
        result["model"], result["model_label"] = name, MODEL_LABELS[name]
        result["training_cutoff"] = dates.train_end
        result["calibration_start"], result["calibration_end"] = calibration.date.min(), dates.validation_end
        result["error"] = result.actual_audience - result.prediction
        results.append(result)
        metrics.append(dict(model=name, model_label=MODEL_LABELS[name], mae=result.error.abs().mean(), wape=result.error.abs().sum() / result.actual_audience.sum(), bias=result.error.mean()))
    return ForecastArtifacts(history, pd.concat(results, ignore_index=True), pd.DataFrame(metrics).sort_values("wape").reset_index(drop=True), dates, dates.train_end, calibration.date.min(), quantiles["xgboost"], quantiles, xgb, models, columns, pd.concat(calibration_results, ignore_index=True))


def upcoming_features(breaks, history):
    rows = []
    for slot in breaks.itertuples():
        issue = slot.air_time.normalize() - pd.DateOffset(days=slot.air_time.weekday())
        previous = history[(history.slot_key == slot.slot_key) & (history.date < issue)].sort_values("date").tail(4)
        if len(previous) != 4 or previous.iloc[-1].forecast_issue_time != issue - pd.DateOffset(weeks=1):
            raise ValueError("The programme slot needs four recent observed weeks")
        rows.append(dict(break_id=slot.break_id, slot_key=slot.slot_key, date=slot.air_time, channel=slot.channel, weekday=slot.air_time.weekday(), hour=slot.air_time.hour, daypart=slot.daypart, genre=slot.genre, week_index=int(previous.week_index.max()) + 1, lag_1_week=float(previous.actual_audience.iloc[-1]), rolling_4_week=float(previous.actual_audience.mean()), recent_trend=float(previous.actual_audience.iloc[-1] - previous.actual_audience.iloc[0]), feature_available_at=previous.date.max(), forecast_issue_time=issue))
    return pd.DataFrame(rows)


def forecast_breaks(breaks, artifacts, model_name="xgboost"):
    features = upcoming_features(breaks, artifacts.history)
    raw = predict_raw(features, model_name, artifacts.models, artifacts.feature_columns)
    result = breaks.copy()
    result["raw_prediction"] = raw
    result[["adults_p20", "adults_p50", "adults_p80"]] = bands_for_predictions(raw, artifacts.calibration_quantiles[model_name])
    result["model_name"], result["training_cutoff"] = model_name, artifacts.training_cutoff
    result["calibration_start"], result["calibration_end"] = artifacts.calibration_start, artifacts.split_dates.validation_end
    result["forecast_issue_time"] = features.forecast_issue_time.to_numpy()
    result["source_state"] = "Synthetic history · calibrated model"
    return result, features


def uncertainty_for_row(row, residual_quantiles):
    lower, median, upper = bands_for_predictions([float(row.prediction)], residual_quantiles)[0]
    return dict(fixed_p20=max(0., float(row.prediction) * .78), calibrated_p20=lower, p50=median, calibrated_p80=upper)


def interval_coverage(artifacts, model_name="xgboost"):
    rows = artifacts.predictions[artifacts.predictions.model == model_name]
    return {f"below_{q}": float((rows.actual_audience <= rows[q]).mean()) for q in ["p20", "p50", "p80"]}


def tree_explanation(artifacts, row, tree_index=0):
    """Traverse real fitted splits and reconcile leaf contributions to prediction."""
    matrix, _ = design(pd.DataFrame([dict(row)]), artifacts.feature_columns)
    booster = artifacts.model.get_booster()
    trees = [json.loads(tree) for tree in booster.get_dump(dump_format="json")]
    all_paths, contributions = [], []
    for tree in trees:
        node, path = tree, []
        while "leaf" not in node:
            feature, threshold = node["split"], float(np.float32(node["split_condition"]))
            value = float(np.float32(matrix.iloc[0][feature]))
            passed = value < threshold
            child = node["missing"] if np.isnan(value) else node["yes"] if passed else node["no"]
            path.append(dict(feature=feature, value=value, threshold=threshold, answer="Yes" if passed else "No", node_id=node["nodeid"]))
            node = next(c for c in node["children"] if c["nodeid"] == child)
        path.append(dict(leaf=float(node["leaf"]), node_id=node["nodeid"]))
        contributions.append(float(node["leaf"]))
        all_paths.append(path)
    config = json.loads(booster.save_config())
    base = float(str(config["learner"]["learner_model_param"]["base_score"]).strip("[]"))
    raw = float(booster.predict(DMatrix(matrix), output_margin=True)[0])
    leaves = booster.predict(DMatrix(matrix), pred_leaf=True)[0].astype(int).tolist()
    return dict(path=all_paths[tree_index], base=base, contributions=contributions, raw_prediction=raw, reconstructed=base + sum(contributions), leaf_ids=leaves, tree_index=tree_index)
