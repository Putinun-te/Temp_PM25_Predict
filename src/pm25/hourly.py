"""Hourly PM2.5 and PM10 forecast for the rest of today and all of tomorrow.

The daily run makes this forecast once each morning, so it needs no extra
scheduled jobs. Station hours reach OpenAQ two to three hours late and the run
starts between 07:17 and 08:00 in Bangkok, so features only use hours up to
03:00 of the forecast day. Targets run from 04:00 today to 23:00 tomorrow.

A second, lighter run after midday repeats the forecast with the morning's
measurements (hours up to 09:00) and its own model, because the newest hours
are the strongest signal for the rest of the day.

One model covers every lead time; the hour of day and the lead are features.
Weather for each target hour comes from the same previous-run forecasts as the
daily model (see pm25.nwp), so training never sees hindsight.

PM10 uses the same code with its own models. Only three stations report PM10,
so its city value is the median of at least two of them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import make_pipeline

from pm25.evaluate import fitted_range, metrics, promotion_gate, walk_forward_predict, width_for
from pm25.features import MIN_STATIONS, TIMEZONE
from pm25.transform import DropEmptyColumns
from pm25.ingest import PARAMETER, TIME, VALUE, city_panel

HOURLY_FILENAME = "hourly_forecast.json"
MODEL_FILENAME = "pm25_hourly.joblib"
LAST_KNOWN_HOUR = 3  # 03:00 on the forecast day, for the morning run
AFTERNOON_KNOWN_HOUR = 9  # The run after midday sees hours up to 09:00
# The evening run at 19:03 sees hours up to 16:00 and refreshes the rest of today and tomorrow.
EVENING_KNOWN_HOUR = 16
# The morning model comes with the daily run; these update it later in the day.
UPDATE_KNOWN_HOURS = (AFTERNOON_KNOWN_HOUR, EVENING_KNOWN_HOUR)
KNOWN_HOURS = (LAST_KNOWN_HOUR, *UPDATE_KNOWN_HOURS)
_RUN_SUFFIX = {LAST_KNOWN_HOUR: "", AFTERNOON_KNOWN_HOUR: "_afternoon", EVENING_KNOWN_HOUR: "_evening"}
AFTERNOON_KEY = "hourly_afternoon"  # Registry and metrics key of the afternoon model
# The afternoon update is skipped unless at least one of the newest hours has arrived.
AFTERNOON_REQUIRED_HOURS = 3
HOURLY_TARGETS = ("pm25", "pm10")


def registry_key(target: str, known_hour: int) -> str:
    """Registry and metrics key: hourly, hourly_afternoon, hourly_evening for PM2.5; hourly_pm10 and so on for PM10."""
    base = "hourly" if target == "pm25" else f"hourly_{target}"
    return base + _RUN_SUFFIX[known_hour]


def leads_for(known_hour: int) -> tuple[int, ...]:
    """Hours after midnight of the forecast day that are forecast, given the last known hour."""
    return tuple(range(known_hour + 1, 48))


def model_filename(known_hour: int, target: str = "pm25") -> str:
    if target == "pm25" and known_hour == LAST_KNOWN_HOUR:
        return MODEL_FILENAME
    return f"{target}_hourly_h{known_hour:02d}.joblib"


LEADS = leads_for(LAST_KNOWN_HOUR)
NWP_HOURLY = ("temp_c", "rh_pct", "precip_mm", "wind_kmh", "wind_u", "wind_v", "pressure_hpa", "cloud_pct")
BASELINES = ("same_hour", "yesterday_mean")
MODEL = "gradient_boosting"
MEASURED_HOURS_SHOWN = 28


def make_model() -> Any:
    # Early folds have feature columns with no values yet, which the regressor rejects.
    return make_pipeline(DropEmptyColumns(), HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=1.0, random_state=0
    ))


def hourly_city(openaq: pd.DataFrame, target: str = "pm25") -> pd.Series:
    """Return the Bangkok hourly value of `target`: the median across stations, by local hour."""
    frame = city_panel(openaq)
    frame = frame[frame[PARAMETER] == target]
    grouped = frame.groupby(TIME)[VALUE].agg(["median", "count"])
    series = grouped.loc[grouped["count"] >= MIN_STATIONS[target], "median"]
    series.index = series.index.tz_convert(TIMEZONE).tz_localize(None)
    return series.rename(target).sort_index()


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
    city: pd.Series, nwp_hourly: pd.DataFrame, days: pd.DatetimeIndex, known_hour: int = LAST_KNOWN_HOUR
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Return features, labels and baselines with one row per forecast day and lead.

    The index is the forecast day. Every feature comes from hours up to
    `known_hour` of that day, or from weather forecasts issued before it.
    """
    nwp = _local_nwp(nwp_hourly)
    known = pd.DataFrame(
        {
            f"obs_{offset:+d}": city.reindex(days + pd.Timedelta(hours=offset)).to_numpy()
            for offset in range(-24, known_hour + 1)  # Yesterday 00:00 to the last known hour
        },
        index=days,
    )
    yesterday = known[[f"obs_{o:+d}" for o in range(-24, 0)]]
    shared = known.copy()
    shared["yesterday_mean"] = yesterday.mean(axis=1).where(yesterday.notna().sum(axis=1) >= 18)
    shared["yesterday_max"] = yesterday.max(axis=1)
    shared["last6_mean"] = known[[f"obs_{o:+d}" for o in range(known_hour - 5, known_hour + 1)]].mean(axis=1)
    shared["trend"] = shared["last6_mean"] - shared["yesterday_mean"]
    day_of_year = days.day_of_year
    shared["doy_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    shared["doy_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)

    features, labels, baselines = [], [], []
    for lead in leads_for(known_hour):
        target = days + pd.Timedelta(hours=lead)
        hour = lead % 24
        part = shared.copy()
        part["lead"] = lead
        part["hour_sin"] = np.sin(2 * np.pi * hour / 24)
        part["hour_cos"] = np.cos(2 * np.pi * hour / 24)
        part["dow_sin"] = np.sin(2 * np.pi * target.day_of_week / 7)
        part["dow_cos"] = np.cos(2 * np.pi * target.day_of_week / 7)
        # The newest known value at the same hour of day: today up to the last known hour, else yesterday.
        same_hour = known[f"obs_{hour if hour <= known_hour else hour - 24:+d}"]
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
    city: pd.Series,
    nwp_hourly: pd.DataFrame,
    as_of: pd.Timestamp,
    models_dir: Path,
    now: str,
    known_hour: int = LAST_KNOWN_HOUR,
    target: str = "pm25",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate the hourly model walk-forward and return its registry entry and report."""
    first = city.index.min().normalize() + pd.Timedelta(days=1)
    days = pd.date_range(first, as_of - pd.Timedelta(days=1), freq="D")
    features, labels, baselines = build_hourly(city, nwp_hourly, days, known_hour)
    predicted = walk_forward_predict(features, labels, make_model, horizon=2)
    frame = pd.DataFrame({"actual": labels, MODEL: predicted, **{name: baselines[name] for name in BASELINES}})
    frame["lead"] = features["lead"].to_numpy()
    frame = frame.dropna()
    if frame.empty:
        raise ValueError(f"hourly {target}: no rows to evaluate")

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
    # Each part of the forecast picks its own range: one value, or bands of forecast level.
    ranges, range_report = {}, {}
    for part, rows in parts.items():
        ranges[part], range_report[part] = fitted_range(rows["actual"], rows[method], None, ("flat", "level"))
    entry["range"] = ranges
    if promote:
        known = labels.notna().to_numpy()
        model = make_model().fit(features[known], labels[known])
        models_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, models_dir / model_filename(known_hour, target))
        entry.update({"features": list(features.columns), "promoted_at": now})
    report = {
        "published_method": method,
        "decision": entry["reason"],
        "overall": overall,
        "mae_by_day": by_part,
        "evaluated_hours": int(len(frame)),
        "range": range_report,
    }
    return entry, report


def forecast_hourly(
    city: pd.Series,
    nwp_hourly: pd.DataFrame,
    entry: dict[str, Any],
    models_dir: Path,
    as_of: pd.Timestamp,
    generated_at: str,
    known_hour: int = LAST_KNOWN_HOUR,
    target: str = "pm25",
) -> dict[str, Any]:
    """Return the hourly forecast document for `as_of` and the following day; values sit under the target's name."""
    days = pd.DatetimeIndex([as_of])
    features, _, baselines = build_hourly(city, nwp_hourly, days, known_hour)
    if entry["method"] == MODEL:
        model = joblib.load(models_dir / model_filename(known_hour, target))
        values = model.predict(features.reindex(columns=entry["features"]))
    else:
        values = baselines[entry["method"]].to_numpy()
    hours = []
    for lead, value in zip(leads_for(known_hour), values):
        part = "today" if lead < 24 else "tomorrow"
        missing = pd.isna(value)
        value = max(float(value), 0.0) if not missing else None
        q80 = hourly_width(entry, part, value)
        hours.append(
            {
                "time": (as_of + pd.Timedelta(hours=lead)).strftime("%Y-%m-%dT%H:%M"),
                "day": part,
                target: None if missing else round(value, 1),
                "low": None if missing else round(max(value - q80, 0.0), 1),
                "high": None if missing else round(value + q80, 1),
            }
        )
    known_until = as_of + pd.Timedelta(hours=known_hour)
    recent = city[(city.index > known_until - pd.Timedelta(hours=MEASURED_HOURS_SHOWN)) & (city.index <= known_until)]
    return {
        "generated_at": generated_at,
        "as_of": as_of.date().isoformat(),
        "timezone": TIMEZONE,
        "unit": "ug/m3",
        "method": entry["method"],
        "inputs_through": known_until.strftime("%Y-%m-%dT%H:%M"),
        "measured": [{"time": t.strftime("%Y-%m-%dT%H:%M"), target: round(float(v), 1)} for t, v in recent.items()],
        "hours": hours,
    }


def hourly_width(entry: dict[str, Any], part: str, value: float | None) -> float:
    """Range half-width for one hour; models trained before per-part ranges use the flat value."""
    spec = (entry.get("range") or {}).get(part)
    width = width_for(spec, value) if spec else None
    return entry["residual_q80"][part] if width is None else width


def has_recent_hours(city: pd.Series, as_of: pd.Timestamp, known_hour: int) -> bool:
    """True when at least one of the newest hours before `known_hour` has been measured."""
    newest = pd.date_range(end=as_of + pd.Timedelta(hours=known_hour), periods=AFTERNOON_REQUIRED_HOURS, freq="h")
    return bool(city.reindex(newest).notna().any())


def merge_pm10(hourly: dict[str, Any], pm10: dict[str, Any]) -> dict[str, Any]:
    """Add the PM10 hourly forecast to the PM2.5 document.

    Each hour gains `pm10`, `pm10_low` and `pm10_high`, each measured hour gains
    `pm10`, and `pm10_method` names the PM10 method. PM2.5 fields are unchanged.
    """
    by_time = {hour["time"]: hour for hour in pm10["hours"]}
    for hour in hourly["hours"]:
        extra = by_time.get(hour["time"])
        if extra is not None:
            hour.update({"pm10": extra["pm10"], "pm10_low": extra["low"], "pm10_high": extra["high"]})
    measured = {item["time"]: item["pm10"] for item in pm10["measured"]}
    for item in hourly["measured"]:
        if item["time"] in measured:
            item["pm10"] = measured[item["time"]]
    hourly["pm10_method"] = pm10["method"]
    return hourly
