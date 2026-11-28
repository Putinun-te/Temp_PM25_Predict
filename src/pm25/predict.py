"""Build the forecast document from the registry of promoted methods."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from pm25.features import (
    ALL_TARGETS,
    UNITS,
    build_features,
    daily_baselines,
    model_inputs,
    monthly_forecast,
    monthly_targets,
    with_weather_targets,
)
from pm25.evaluate import entry_chance_above, entry_chances_above, range_for, recent_bias
from pm25.train import CANDIDATES, model_path

FORECAST_FILENAME = "forecast.json"
SCHEMA_VERSION = 2
# Horizon 1 is today. After tomorrow a day is labelled by how many days it lies after today.
DAILY_LABELS = {1: "today", 2: "tomorrow", **{horizon: f"day{horizon - 1}" for horizon in range(3, 8)}}
MONTHS_AHEAD = (1, 2, 3)


def _rounded(value: float) -> float | None:
    return None if pd.isna(value) else round(float(value), 1)


def _with_range(row: dict[str, Any], target: str, value: float, q80: float | None) -> None:
    """Add a value and its range. Unavailable numbers are null, never estimated."""
    value = np.nan if pd.isna(value) else max(float(value), 0.0)
    row[target] = _rounded(value)
    row[f"{target}_low"] = _rounded(max(value - q80, 0.0)) if q80 is not None else None
    row[f"{target}_high"] = _rounded(value + q80) if q80 is not None else None


def recent_errors(history: pd.DataFrame | None, measured: pd.Series, target: str, label: str) -> pd.Series:
    """Errors of the model's own past daily forecasts for one day label, indexed by the date measured.

    `model_value` is the forecast before any correction; rows saved before that
    column existed were published uncorrected, so their `value` is the same.
    """
    if history is None or history.empty:
        return pd.Series(dtype=float)
    rows = history[(history["kind"] == "daily") & (history["target"] == target) & (history["label"] == label)]
    raw = pd.to_numeric(rows["value"], errors="coerce")
    if "model_value" in rows:
        raw = pd.to_numeric(rows["model_value"], errors="coerce").fillna(raw)
    periods = pd.to_datetime(rows["period"])
    errors = pd.Series(measured.reindex(periods).to_numpy() - raw.to_numpy(), index=periods)
    return errors[~errors.index.duplicated(keep="last")].dropna().sort_index()


def _daily_row(
    origin: pd.Timestamp,
    horizon: int,
    targets: pd.DataFrame,
    exogenous: pd.DataFrame,
    registry: dict[str, Any],
    models_dir: Path,
    tmd: dict[str, dict[str, float]],
    history: pd.DataFrame | None = None,
) -> dict[str, Any]:
    target_date = origin + pd.Timedelta(days=horizon)
    date_key = target_date.date().isoformat()
    row: dict[str, Any] = {"date": date_key, "label": DAILY_LABELS[horizon], "horizon_days": horizon}
    features = build_features(targets, exogenous, horizon).loc[[origin]]
    for target in ALL_TARGETS:
        slot = f"{target}_h{horizon}"
        entry = registry["daily"].get(slot)
        if entry is None:
            continue
        method = entry["method"]
        if method in CANDIDATES:
            value = joblib.load(model_path(models_dir, slot)).predict(model_inputs(features, entry))[0]
        else:
            value = daily_baselines(targets[target], horizon)[method].loc[origin]
        if entry.get("bias_correction") and not pd.isna(value):
            errors = recent_errors(history, targets[target], target, DAILY_LABELS[horizon])
            bias = recent_bias(errors, origin)
            row[f"{target}_model"] = _rounded(value)
            row[f"{target}_bias"] = round(bias, 2)
            value = value + bias
        _with_range(row, target, value, range_for(entry, target_date, value))
        row[f"{target}_method"] = method
        if entry.get("exceedance"):
            standard = entry_chance_above(entry, row[target])
            if standard is not None:
                row[f"{target}_p_above_standard"] = standard
            row[f"{target}_p_above"] = entry_chances_above(entry, row[target])
    # The TMD forecast is a separate reference, kept under its own names.
    for name, value in tmd.get(date_key, {}).items():
        row[f"tmd_{name}"] = value
    return row


def fill_missing_tmd(forecast: dict[str, Any], tmd: dict[str, dict[str, float]]) -> list[str]:
    """Add TMD values to daily rows that have none yet; return the dates filled.

    Rows that already carry TMD values keep them, so a later fetch never
    rewrites what the morning run published.
    """
    filled = []
    for row in forecast["daily"]:
        if "tmd_temp_c" in row or row["date"] not in tmd:
            continue
        for name, value in tmd[row["date"]].items():
            row[f"tmd_{name}"] = value
        filled.append(row["date"])
    return filled


def _monthly_row(
    months_ahead: int,
    as_of: pd.Timestamp,
    monthly: pd.DataFrame,
    registry: dict[str, Any],
) -> dict[str, Any]:
    origin = as_of.to_period("M").to_timestamp() - pd.DateOffset(months=1)
    horizon = months_ahead + 1
    month = origin + pd.DateOffset(months=horizon)
    row: dict[str, Any] = {"month": month.strftime("%Y-%m"), "months_ahead": months_ahead}
    for target in ALL_TARGETS:
        entry = registry["monthly"].get(f"{target}_m{horizon}")
        if entry is None:
            continue
        history = monthly[target][monthly.index <= origin]
        value = monthly_forecast(history, month, horizon)[entry["method"]]
        _with_range(row, target, value, entry["residual_q80"])
        row[f"{target}_method"] = entry["method"]
    return row


def build_forecast(
    targets: pd.DataFrame,
    exogenous: pd.DataFrame,
    registry: dict[str, Any],
    models_dir: Path,
    as_of: pd.Timestamp,
    generated_at: str,
    tmd: dict[str, dict[str, float]] | None = None,
    history: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Return the forecast document, using only data complete before `as_of`.

    `history` is the forecast history; it gives the recent errors behind the
    temperature correction.
    """
    targets = with_weather_targets(targets, exogenous)
    origin = as_of - pd.Timedelta(days=1)
    latest = targets["pm25"].last_valid_index()
    age_days = (origin - latest).days
    monthly = monthly_targets(targets)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "as_of": as_of.date().isoformat(),
        "latest_data_date": latest.date().isoformat(),
        "data_age_days": age_days,
        "status": "ok" if age_days == 0 else "stale",
        "units": dict(UNITS),
        "daily": [
            _daily_row(origin, horizon, targets, exogenous, registry, models_dir, tmd or {}, history)
            for horizon in DAILY_LABELS
        ],
        "monthly": [_monthly_row(ahead, as_of, monthly, registry) for ahead in MONTHS_AHEAD],
    }


def write_forecast(forecast: dict[str, Any], models_dir: Path) -> Path:
    path = models_dir / FORECAST_FILENAME
    path.write_text(json.dumps(forecast, indent=2) + "\n", encoding="utf-8")
    return path
