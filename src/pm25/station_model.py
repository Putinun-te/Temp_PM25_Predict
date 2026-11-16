"""PM2.5 forecast for each reference station, today and tomorrow.

One pooled model per horizon covers all stations: a row is a station on an
origin day. It sees that station's own recent values, how it differs from the
city median, and every feature of the city model. Pooling keeps training cheap
(two models instead of twenty) and lets stations with gaps borrow from the rest.

The model is published only if it beats both a station's own persistence and
simply using the city forecast for every station.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import make_pipeline

from pm25.evaluate import metrics, promotion_gate, range_for, seasonal_q80, walk_forward_predict
from pm25.features import MIN_HOURS_PER_DAY, TIMEZONE, build_features
from pm25.transform import DropEmptyColumns
from pm25.ingest import OPENAQ_PANEL, PARAMETER, SENSOR, TIME, VALUE, OpenAQSensor

MODEL = "gradient_boosting"
BASELINES = ("persistence", "city_forecast")
HORIZONS = (1, 2)
LABELS = {1: "today", 2: "tomorrow"}
STATION_LAGS = (0, 1, 2, 6)


def model_filename(horizon: int) -> str:
    return f"station_pm25_h{horizon}.joblib"


def make_model() -> Any:
    # Early folds have feature columns with no values yet, which the regressor rejects.
    return make_pipeline(DropEmptyColumns(), HistGradientBoostingRegressor(
        max_iter=250, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=30, l2_regularization=1.0, random_state=0
    ))


def station_daily(
    openaq: pd.DataFrame, as_of: pd.Timestamp, sensors: Sequence[OpenAQSensor] = OPENAQ_PANEL
) -> pd.DataFrame:
    """Return daily PM2.5 per station (columns are location ids), complete days before `as_of`."""
    locations = {s.sensor_id: s.location_id for s in sensors if s.parameter == "pm25"}
    frame = openaq[(openaq[PARAMETER] == "pm25") & openaq[SENSOR].isin(list(locations))]
    frame = frame.assign(date=frame[TIME].dt.tz_convert(TIMEZONE).dt.tz_localize(None).dt.normalize())
    frame = frame[frame["date"] < as_of]
    daily = frame.groupby([SENSOR, "date"])[VALUE].agg(["mean", "count"])
    daily = daily[daily["count"] >= MIN_HOURS_PER_DAY]["mean"].unstack(SENSOR)
    daily = daily.rename(columns=locations).reindex(columns=list(locations.values()))
    calendar = pd.date_range(daily.index.min(), as_of - pd.Timedelta(days=1), freq="D", name="date")
    return daily.reindex(calendar)


def build_station_rows(
    stations: pd.DataFrame, targets: pd.DataFrame, exogenous: pd.DataFrame, horizon: int
) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """Return features, labels, the station id and persistence, one row per station and origin day."""
    city = build_features(targets[["pm25", "pm10"]], exogenous, horizon)
    stations = stations.reindex(city.index)
    order = {location: position for position, location in enumerate(stations.columns)}
    features, labels, ids, persistence = [], [], [], []
    for location in stations.columns:
        series = stations[location]
        part = city.copy()
        for lag in STATION_LAGS:
            part[f"station_lag{lag}"] = series.shift(lag)
        part["station_mean3"] = series.rolling(3, min_periods=2).mean()
        part["station_mean7"] = series.rolling(7, min_periods=4).mean()
        # How this station usually sits against the city, which is fairly stable.
        part["station_minus_city"] = series - targets["pm25"].reindex(city.index)
        part["station_minus_city_mean14"] = part["station_minus_city"].rolling(14, min_periods=5).mean()
        part["station_code"] = order[location]
        features.append(part)
        labels.append(series.shift(-horizon))
        ids.append(pd.Series(location, index=city.index))
        persistence.append(series)
    return pd.concat(features), pd.concat(labels), pd.concat(ids), pd.concat(persistence)


def train_stations(
    stations: pd.DataFrame,
    targets: pd.DataFrame,
    exogenous: pd.DataFrame,
    horizon: int,
    city_forecast: pd.Series,
    models_dir: Path,
    now: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate the pooled station model walk-forward against both baselines.

    `city_forecast` is the city model's own out-of-sample prediction per origin
    day, so the comparison shows whether per-station modelling adds anything.
    """
    features, labels, ids, persistence = build_station_rows(stations, targets, exogenous, horizon)
    predicted = walk_forward_predict(features, labels, make_model, horizon)
    frame = pd.DataFrame(
        {
            "actual": labels,
            MODEL: predicted,
            "persistence": persistence,
            "city_forecast": city_forecast.reindex(features.index).to_numpy(),
            "station": ids,
        }
    ).dropna()
    if frame.empty:
        raise ValueError(f"stations h{horizon}: no rows to evaluate")
    overall = {name: metrics(frame["actual"], frame[name]) for name in (MODEL, *BASELINES)}
    promote, reason = promotion_gate(overall[MODEL]["mae"], {name: overall[name]["mae"] for name in BASELINES})
    method = MODEL if promote else min(BASELINES, key=lambda name: overall[name]["mae"])
    entry: dict[str, Any] = {
        "method": method,
        "reason": f"promoted: {reason}" if promote else f"baseline used: model {reason}",
        "residual_q80": float(np.quantile((frame["actual"] - frame[method]).abs(), 0.8)),
        "residual_q80_by_season": seasonal_q80(frame["actual"], frame[method], horizon),
    }
    if promote:
        known = labels.notna().to_numpy()
        models_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(make_model().fit(features[known], labels[known]), models_dir / model_filename(horizon))
        entry.update({"features": list(features.columns), "promoted_at": now})
    by_station = {
        str(location): {name: float((rows["actual"] - rows[name]).abs().mean()) for name in (MODEL, *BASELINES)}
        for location, rows in frame.groupby("station")
    }
    report = {
        "published_method": method,
        "decision": entry["reason"],
        "overall": overall,
        "mae_by_station": by_station,
    }
    return entry, report


def forecast_stations(
    stations: pd.DataFrame,
    targets: pd.DataFrame,
    exogenous: pd.DataFrame,
    registry: dict[str, Any],
    models_dir: Path,
    as_of: pd.Timestamp,
    city_values: dict[int, float | None],
) -> list[dict[str, Any]]:
    """Return today's and tomorrow's forecast per station.

    `city_values` is the published city forecast per horizon, used when the
    city-forecast baseline is the published method.
    """
    origin = as_of - pd.Timedelta(days=1)
    result = {int(location): {"location_id": int(location)} for location in stations.columns}
    for horizon in HORIZONS:
        entry = registry.get(f"pm25_h{horizon}")
        if entry is None:
            continue
        features, _, ids, persistence = build_station_rows(stations, targets, exogenous, horizon)
        at_origin = features.index == origin
        if entry["method"] == MODEL:
            model = joblib.load(models_dir / model_filename(horizon))
            values = model.predict(features[at_origin].reindex(columns=entry["features"]))
        elif entry["method"] == "persistence":
            values = persistence[at_origin].to_numpy()
        else:
            values = np.full(int(at_origin.sum()), city_values.get(horizon) or np.nan, dtype=float)
        q80 = range_for(entry, origin + pd.Timedelta(days=horizon))
        for location, value in zip(ids[at_origin], values):
            missing = pd.isna(value)
            value = None if missing else max(float(value), 0.0)
            result[int(location)][LABELS[horizon]] = {
                "pm25": None if missing else round(value, 1),
                "low": None if missing or q80 is None else round(max(value - q80, 0.0), 1),
                "high": None if missing or q80 is None else round(value + q80, 1),
                "method": entry["method"],
            }
    return list(result.values())
