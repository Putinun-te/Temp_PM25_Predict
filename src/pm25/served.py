"""Keep the inputs each daily forecast was made from, and compare them with the stored data later.

A forecast can only be explained afterwards if its inputs are known. The data
on disk changes after the forecast: late station hours arrive, and the weather
forecast for a past day is replaced by the run issued the right number of days
before it. Saving the feature rows at forecast time shows which inputs a
forecast really saw, and the comparison shows which inputs differ from what
training would see for the same day.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from pm25.features import build_features, with_weather_targets

SERVED_FILENAME = "served_features.csv"
CHECK_FILENAME = "served_feature_check.json"
SERVED_KEYS = ["as_of", "horizon"]
HORIZONS = tuple(range(1, 8))
CHECK_DAYS = 14
# Two values closer than this are the same input (CSV rounding).
TOLERANCE = 1e-6


def served_rows(targets: pd.DataFrame, exogenous: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """One row per horizon with the feature values the forecast of `as_of` uses."""
    targets = with_weather_targets(targets, exogenous)
    origin = as_of - pd.Timedelta(days=1)
    rows = []
    for horizon in HORIZONS:
        features = build_features(targets, exogenous, horizon)
        if origin not in features.index:
            continue
        row = features.loc[origin].to_dict()
        rows.append({"as_of": as_of.date().isoformat(), "horizon": horizon, **row})
    return pd.DataFrame(rows)


def append_served(path: Path, rows: pd.DataFrame) -> None:
    """Add today's rows; rerunning a day replaces them."""
    if rows.empty:
        return
    rows = rows.astype({"as_of": str, "horizon": int})
    if path.exists():
        rows = pd.concat([pd.read_csv(path, dtype={"as_of": str}), rows], ignore_index=True)
    rows = rows.drop_duplicates(SERVED_KEYS, keep="last").sort_values(SERVED_KEYS)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(path, index=False)


def compare_served(
    served: pd.DataFrame, targets: pd.DataFrame, exogenous: pd.DataFrame, today: pd.Timestamp, days: int = CHECK_DAYS
) -> dict[str, Any]:
    """Compare the inputs of the last `days` forecasts with the same inputs rebuilt from the stored data.

    Per feature: how many values were compared, how often an input was missing
    at forecast time but is there now (or the other way), and how far the
    values that exist in both differ.
    """
    served = served[pd.to_datetime(served["as_of"]) > today - pd.Timedelta(days=days)]
    result: dict[str, Any] = {"days": days, "forecasts": int(served["as_of"].nunique()) if not served.empty else 0,
                              "features": []}
    if served.empty:
        return result
    targets = with_weather_targets(targets, exogenous)
    later_parts = []
    for horizon, group in served.groupby("horizon"):
        features = build_features(targets, exogenous, int(horizon))
        origins = pd.to_datetime(group["as_of"]) - pd.Timedelta(days=1)
        later = features.reindex(origins)
        later.index = group.index
        later_parts.append(later)
    later = pd.concat(later_parts).reindex(served.index)
    for column in later.columns:
        if column not in served:
            continue
        then = pd.to_numeric(served[column], errors="coerce")
        now = pd.to_numeric(later[column], errors="coerce")
        both = then.notna() & now.notna()
        diff = (then[both] - now[both]).abs()
        result["features"].append(
            {
                "feature": column,
                "compared": int(both.sum()),
                "missing_at_forecast": int((then.isna() & now.notna()).sum()),
                "missing_now": int((then.notna() & now.isna()).sum()),
                "changed": int((diff > TOLERANCE).sum()),
                "mean_abs_diff": None if diff.empty else round(float(diff.mean()), 4),
                "max_abs_diff": None if diff.empty else round(float(diff.max()), 4),
            }
        )
    result["features"].sort(
        key=lambda f: (-(f["missing_at_forecast"] + f["missing_now"] + f["changed"]), -(f["mean_abs_diff"] or 0))
    )
    return result


def differing(check: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Features whose value at forecast time differed from the stored data."""
    return [
        f for f in (check or {}).get("features", [])
        if f["missing_at_forecast"] or f["missing_now"] or f["changed"]
    ]

