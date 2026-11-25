"""PM2.5 and PM10 forecast for each reference station, for the next seven days.

One pooled model per horizon covers all stations: a row is a station on an
origin day. It sees that station's own recent values, how it differs from the
city median, and every feature of the city model. Pooling keeps training cheap
(two models instead of twenty) and lets stations with gaps borrow from the rest.

The model is published only if it beats both a station's own persistence and
simply using the city forecast for every station.

PM10 uses the same code with its own models. Only three stations of the panel
report PM10, so its pooled model has far fewer rows.
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

from pm25.evaluate import entry_chance_above, entry_chances_above, metrics, promotion_gate, range_entry, range_for, walk_forward_predict
from pm25.features import MIN_HOURS_PER_DAY, TIMEZONE, build_features
from pm25.transform import ChangeFromLast, DropEmptyColumns
from pm25.ingest import OPENAQ_SENSORS, PARAMETER, SENSOR, TIME, VALUE, OpenAQSensor

MODEL = "gradient_boosting"
# A model of the change from the station's own last value. It beat the level model
# today to three days after today and lost further ahead, so it is only tried there.
CHANGE_MODEL = "gradient_boosting_change"
CHANGE_HORIZONS = (1, 2, 3, 4)
MODELS = (MODEL, CHANGE_MODEL)
BASELINES = ("persistence", "city_forecast")
HORIZONS = tuple(range(1, 8))
# Same labels as the city forecast: today, tomorrow, then day2 to day6 (days after today).
LABELS = {1: "today", 2: "tomorrow", **{horizon: f"day{horizon - 1}" for horizon in range(3, 8)}}
STATION_LAGS = (0, 1, 2, 6)
STATION_TARGETS = ("pm25", "pm10")


def model_filename(horizon: int, target: str = "pm25") -> str:
    return f"station_{target}_h{horizon}.joblib"


def make_model() -> Any:
    # Early folds have feature columns with no values yet, which the regressor rejects.
    return make_pipeline(DropEmptyColumns(), HistGradientBoostingRegressor(
        max_iter=250, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=30, l2_regularization=1.0, random_state=0
    ))


def make_change_model() -> Any:
    return ChangeFromLast(make_model(), "station")


def candidates(horizon: int) -> dict[str, Any]:
    """The models tried for a horizon, by name."""
    found = {MODEL: make_model}
    if horizon in CHANGE_HORIZONS:
        found[CHANGE_MODEL] = make_change_model
    return found


def station_daily(
    openaq: pd.DataFrame,
    as_of: pd.Timestamp,
    sensors: Sequence[OpenAQSensor] = OPENAQ_SENSORS,
    target: str = "pm25",
) -> pd.DataFrame:
    """Return the daily mean per station (columns are location ids), complete days before `as_of`."""
    locations = {s.sensor_id: s.location_id for s in sensors if s.parameter == target}
    frame = openaq[(openaq[PARAMETER] == target) & openaq[SENSOR].isin(list(locations))]
    frame = frame.assign(date=frame[TIME].dt.tz_convert(TIMEZONE).dt.tz_localize(None).dt.normalize())
    frame = frame[frame["date"] < as_of]
    daily = frame.groupby([SENSOR, "date"])[VALUE].agg(["mean", "count"])
    daily = daily[daily["count"] >= MIN_HOURS_PER_DAY]["mean"].unstack(SENSOR)
    daily = daily.rename(columns=locations).reindex(columns=list(locations.values()))
    calendar = pd.date_range(daily.index.min(), as_of - pd.Timedelta(days=1), freq="D", name="date")
    return daily.reindex(calendar)


def build_station_rows(
    stations: pd.DataFrame, targets: pd.DataFrame, exogenous: pd.DataFrame, horizon: int, target: str = "pm25"
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
        part["station_minus_city"] = series - targets[target].reindex(city.index)
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
    target: str = "pm25",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate the pooled station model walk-forward against both baselines.

    `city_forecast` is the city model's own out-of-sample prediction per origin
    day, so the comparison shows whether per-station modelling adds anything.
    """
    features, labels, ids, persistence = build_station_rows(stations, targets, exogenous, horizon, target)
    tried = candidates(horizon)
    predicted = {name: walk_forward_predict(features, labels, make, horizon) for name, make in tried.items()}
    frame = pd.DataFrame(
        {
            "actual": labels,
            **predicted,
            "persistence": persistence,
            "city_forecast": city_forecast.reindex(features.index).to_numpy(),
            "station": ids,
        }
    ).dropna()
    if frame.empty:
        raise ValueError(f"stations {target} h{horizon}: no rows to evaluate")
    overall = {name: metrics(frame["actual"], frame[name]) for name in (*tried, *BASELINES)}
    # The model with the lower error over all folds is the one put to the gate.
    best = min(tried, key=lambda name: overall[name]["mae"])
    promote, reason = promotion_gate(overall[best]["mae"], {name: overall[name]["mae"] for name in BASELINES})
    method = best if promote else min(BASELINES, key=lambda name: overall[name]["mae"])
    entry: dict[str, Any] = {
        "method": method,
        "reason": f"promoted: {reason}" if promote else f"baseline used: model {reason}",
    }
    range_fields, range_report = range_entry(frame["actual"], frame[method], horizon, target)
    entry.update(range_fields)
    if promote:
        known = labels.notna().to_numpy()
        models_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(tried[best]().fit(features[known], labels[known]), models_dir / model_filename(horizon, target))
        entry.update({"features": list(features.columns), "promoted_at": now})
    by_station = {
        str(location): {name: float((rows["actual"] - rows[name]).abs().mean()) for name in (*tried, *BASELINES)}
        for location, rows in frame.groupby("station")
    }
    report = {
        "published_method": method,
        "decision": entry["reason"],
        "overall": overall,
        "mae_by_station": by_station,
        "range": range_report,
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
    target: str = "pm25",
) -> list[dict[str, Any]]:
    """Return each station's forecast for every horizon; the value sits under the target's name.

    `city_values` is the published city forecast per horizon, used when the
    city-forecast baseline is the published method.
    """
    origin = as_of - pd.Timedelta(days=1)
    result = {int(location): {"location_id": int(location)} for location in stations.columns}
    for horizon in HORIZONS:
        entry = registry.get(f"{target}_h{horizon}")
        if entry is None:
            continue
        features, _, ids, persistence = build_station_rows(stations, targets, exogenous, horizon, target)
        at_origin = features.index == origin
        if entry["method"] in MODELS:
            model = joblib.load(models_dir / model_filename(horizon, target))
            values = model.predict(features[at_origin].reindex(columns=entry["features"]))
        elif entry["method"] == "persistence":
            values = persistence[at_origin].to_numpy()
        else:
            values = np.full(int(at_origin.sum()), city_values.get(horizon) or np.nan, dtype=float)
        for location, value in zip(ids[at_origin], values):
            missing = pd.isna(value)
            value = None if missing else max(float(value), 0.0)
            q80 = None if missing else range_for(entry, origin + pd.Timedelta(days=horizon), value)
            result[int(location)][LABELS[horizon]] = {
                target: None if missing else round(value, 1),
                "low": None if missing or q80 is None else round(max(value - q80, 0.0), 1),
                "high": None if missing or q80 is None else round(value + q80, 1),
                "method": entry["method"],
                "p_above_standard": None if missing else entry_chance_above(entry, value),
                "p_above": None if missing else entry_chances_above(entry, value),
            }
    return list(result.values())


def merge_pm10(stations: list[dict[str, Any]], pm10: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add each station's PM10 forecast under `pm10` of its daily entries."""
    by_location = {item["location_id"]: item for item in pm10}
    for station in stations:
        extra = by_location.get(station["location_id"], {})
        for label in LABELS.values():
            if label in extra:
                station.setdefault(label, {})["pm10"] = extra[label]
    return stations
