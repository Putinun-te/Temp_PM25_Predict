"""Hourly PM2.5 forecast for the rest of today and all of tomorrow.

The daily run makes this forecast once each morning, so it needs no extra
scheduled jobs. Station hours reach OpenAQ two to three hours late and the run
starts between 07:17 and 08:00 in Bangkok, so features only use hours up to
03:00 of the forecast day. Targets run from 04:00 today to 23:00 tomorrow.

One model covers every lead time; the hour of day and the lead are features.
Weather for each target hour comes from the same previous-run forecasts as the
daily model (see pm25.nwp), so training never sees hindsight.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import make_pipeline

from pm25.evaluate import metrics, promotion_gate, walk_forward_predict
from pm25.features import MIN_STATIONS, TIMEZONE
from pm25.transform import DropEmptyColumns
from pm25.ingest import PARAMETER, TIME, VALUE

HOURLY_FILENAME = "hourly_forecast.json"
MODEL_FILENAME = "pm25_hourly.joblib"
LAST_KNOWN_HOUR = 3  # 03:00 on the forecast day
FIRST_LEAD = LAST_KNOWN_HOUR + 1
LEADS = tuple(range(FIRST_LEAD, 48))  # Hours after midnight of the forecast day
KNOWN_OFFSETS = tuple(range(-24, FIRST_LEAD))  # Yesterday 00:00 to today 03:00
NWP_HOURLY = ("temp_c", "rh_pct", "precip_mm", "wind_kmh", "wind_u", "wind_v", "pressure_hpa", "cloud_pct")
BASELINES = ("same_hour", "yesterday_mean")
MODEL = "gradient_boosting"
MEASURED_HOURS_SHOWN = 28


def make_model() -> Any:
    # Early folds have feature columns with no values yet, which the regressor rejects.
    return make_pipeline(DropEmptyColumns(), HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=1.0, random_state=0
    ))


def hourly_city(openaq: pd.DataFrame) -> pd.Series:
    """Return the Bangkok hourly PM2.5: the median across stations, by local hour."""
    frame = openaq[openaq[PARAMETER] == "pm25"]
    grouped = frame.groupby(TIME)[VALUE].agg(["median", "count"])
    series = grouped.loc[grouped["count"] >= MIN_STATIONS["pm25"], "median"]
    series.index = series.index.tz_convert(TIMEZONE).tz_localize(None)
    return series.rename("pm25").sort_index()


def _local_nwp(nwp_hourly: pd.DataFrame) -> pd.DataFrame:
    """Index the hourly weather forecasts by local hour and add wind components."""
    if nwp_hourly.empty:
        return pd.DataFrame()
    frame = nwp_hourly.set_index(nwp_hourly[TIME].dt.tz_convert(TIMEZONE).dt.tz_localize(None)).drop(columns=[TIME])
    for day in (1, 2):
        radians = np.deg2rad(frame[f"nwp{day}_wind_deg"])
        frame[f"nwp{day}_wind_u"] = -frame[f"nwp{day}_wind_kmh"] * np.sin(radians)
        frame[f"nwp{day}_wind_v"] = -frame[f"nwp{day}_wind_kmh"] * np.cos(radians)
    return frame


def build_hourly(
    city: pd.Series, nwp_hourly: pd.DataFrame, days: pd.DatetimeIndex
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Return features, labels and baselines with one row per forecast day and lead.

    The index is the forecast day. Every feature comes from hours up to 03:00
    of that day, or from weather forecasts issued before it.
    """
    nwp = _local_nwp(nwp_hourly)
    known = pd.DataFrame(
        {f"obs_{offset:+d}": city.reindex(days + pd.Timedelta(hours=offset)).to_numpy() for offset in KNOWN_OFFSETS},
        index=days,
    )
    yesterday = known[[f"obs_{o:+d}" for o in range(-24, 0)]]
    shared = known.copy()
    shared["yesterday_mean"] = yesterday.mean(axis=1).where(yesterday.notna().sum(axis=1) >= 18)
    shared["yesterday_max"] = yesterday.max(axis=1)
    shared["last6_mean"] = known[[f"obs_{o:+d}" for o in range(-2, FIRST_LEAD)]].mean(axis=1)
    shared["trend"] = shared["last6_mean"] - shared["yesterday_mean"]
    day_of_year = days.day_of_year
    shared["doy_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    shared["doy_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)

    features, labels, baselines = [], [], []
    for lead in LEADS:
        target = days + pd.Timedelta(hours=lead)
        hour = lead % 24
        part = shared.copy()
        part["lead"] = lead
        part["hour_sin"] = np.sin(2 * np.pi * hour / 24)
        part["hour_cos"] = np.cos(2 * np.pi * hour / 24)
        part["dow_sin"] = np.sin(2 * np.pi * target.day_of_week / 7)
        part["dow_cos"] = np.cos(2 * np.pi * target.day_of_week / 7)
        # The newest known value at the same hour of day: today for 00:00 to 03:00, else yesterday.
        same_hour = known[f"obs_{hour if hour <= LAST_KNOWN_HOUR else hour - 24:+d}"]
        part["same_hour"] = same_hour
        run_age = 1 if lead < 24 else 2
        for name in NWP_HOURLY:
            column = f"nwp{run_age}_{name}"
            part[f"nwp_{name}"] = nwp[column].reindex(target).to_numpy() if column in nwp else np.nan
        features.append(part)
        labels.append(pd.Series(city.reindex(target).to_numpy(), index=days))
        baselines.append(pd.DataFrame({"same_hour": same_hour, "yesterday_mean": shared["yesterday_mean"]}))
    return pd.concat(features), pd.concat(labels), pd.concat(baselines)


def train_hourly(
    city: pd.Series, nwp_hourly: pd.DataFrame, as_of: pd.Timestamp, models_dir: Path, now: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate the hourly model walk-forward and return its registry entry and report."""
    first = city.index.min().normalize() + pd.Timedelta(days=1)
    days = pd.date_range(first, as_of - pd.Timedelta(days=1), freq="D")
    features, labels, baselines = build_hourly(city, nwp_hourly, days)
    predicted = walk_forward_predict(features, labels, make_model, horizon=2)
    frame = pd.DataFrame({"actual": labels, MODEL: predicted, **{name: baselines[name] for name in BASELINES}})
    frame["lead"] = features["lead"].to_numpy()
    frame = frame.dropna()
    if frame.empty:
        raise ValueError("hourly: no rows to evaluate")

    overall = {name: metrics(frame["actual"], frame[name]) for name in (MODEL, *BASELINES)}
    parts = {"today": frame[frame["lead"] < 24], "tomorrow": frame[frame["lead"] >= 24]}
    by_part = {
        part: {name: float((rows["actual"] - rows[name]).abs().mean()) for name in (MODEL, *BASELINES)}
        for part, rows in parts.items()
    }
    promote, reason = promotion_gate(overall[MODEL]["mae"], {name: overall[name]["mae"] for name in BASELINES})
    method = MODEL if promote else min(BASELINES, key=lambda name: overall[name]["mae"])
    entry: dict[str, Any] = {
        "method": method,
        "reason": f"promoted: {reason}" if promote else f"baseline used: model {reason}",
        "residual_q80": {
            part: float(np.quantile((rows["actual"] - rows[method]).abs(), 0.8)) for part, rows in parts.items()
        },
    }
    if promote:
        known = labels.notna().to_numpy()
        model = make_model().fit(features[known], labels[known])
        models_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, models_dir / MODEL_FILENAME)
        entry.update({"features": list(features.columns), "promoted_at": now})
    report = {
        "published_method": method,
        "decision": entry["reason"],
        "overall": overall,
        "mae_by_day": by_part,
        "evaluated_hours": int(len(frame)),
    }
    return entry, report


def forecast_hourly(
    city: pd.Series,
    nwp_hourly: pd.DataFrame,
    entry: dict[str, Any],
    models_dir: Path,
    as_of: pd.Timestamp,
    generated_at: str,
) -> dict[str, Any]:
    """Return the hourly forecast document for `as_of` and the following day."""
    days = pd.DatetimeIndex([as_of])
    features, _, baselines = build_hourly(city, nwp_hourly, days)
    if entry["method"] == MODEL:
        values = joblib.load(models_dir / MODEL_FILENAME).predict(features.reindex(columns=entry["features"]))
    else:
        values = baselines[entry["method"]].to_numpy()
    hours = []
    for lead, value in zip(LEADS, values):
        part = "today" if lead < 24 else "tomorrow"
        q80 = entry["residual_q80"][part]
        missing = pd.isna(value)
        value = max(float(value), 0.0) if not missing else None
        hours.append(
            {
                "time": (as_of + pd.Timedelta(hours=lead)).strftime("%Y-%m-%dT%H:%M"),
                "day": part,
                "pm25": None if missing else round(value, 1),
                "low": None if missing else round(max(value - q80, 0.0), 1),
                "high": None if missing else round(value + q80, 1),
            }
        )
    known_until = as_of + pd.Timedelta(hours=LAST_KNOWN_HOUR)
    recent = city[(city.index > known_until - pd.Timedelta(hours=MEASURED_HOURS_SHOWN)) & (city.index <= known_until)]
    return {
        "generated_at": generated_at,
        "as_of": as_of.date().isoformat(),
        "timezone": TIMEZONE,
        "unit": "ug/m3",
        "method": entry["method"],
        "inputs_through": known_until.strftime("%Y-%m-%dT%H:%M"),
        "measured": [{"time": t.strftime("%Y-%m-%dT%H:%M"), "pm25": round(float(v), 1)} for t, v in recent.items()],
        "hours": hours,
    }
