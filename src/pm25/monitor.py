"""Score published forecasts against what was later measured.

Walk-forward validation estimates accuracy before a model is used. This module
checks the forecasts that were actually published, once the measured value for
their date exists. Each forecast is compared with persistence as it stood on
the day the forecast was issued: the newest measured day before `as_of`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from pm25.features import ALL_TARGETS

ACCURACY_FILENAME = "live_accuracy.csv"
SUMMARY_FILENAME = "live_accuracy_summary.json"
WINDOWS = (7, 30, 90)
# TMD forecasts are scored against the same measured series as our own temperature
# and humidity forecasts, so the two can be compared directly.
TMD_TARGETS = {"tmd_temp_c": "temp_c", "tmd_rh_pct": "rh_pct"}
# A model is flagged only after enough scored days, so one bad week does not alert.
DEGRADATION_WINDOW = 30
DEGRADATION_MIN_DAYS = 14
ACCURACY_COLUMNS = [
    "as_of",
    "period",
    "label",
    "target",
    "source",
    "method",
    "forecast",
    "low",
    "high",
    "actual",
    "persistence",
    "abs_error",
    "persistence_abs_error",
    "in_range",
]


def score_history(history: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Return one row per published daily forecast whose date has a measured value."""
    rows = history[history["kind"] == "daily"].copy()
    rows["source"] = np.where(rows["target"].isin(list(TMD_TARGETS)), "tmd", "forecast")
    rows["target"] = rows["target"].replace(TMD_TARGETS)
    rows = rows[rows["target"].isin(ALL_TARGETS)]
    if rows.empty:
        return pd.DataFrame(columns=ACCURACY_COLUMNS)

    measured = daily.copy()
    measured["date"] = pd.to_datetime(measured["date"])
    actual = measured.melt(id_vars="date", value_vars=list(ALL_TARGETS), var_name="target", value_name="actual")
    actual = actual.dropna(subset=["actual"])

    rows["period_date"] = pd.to_datetime(rows["period"])
    rows["origin"] = pd.to_datetime(rows["as_of"]) - pd.Timedelta(days=1)
    scored = rows.merge(
        actual.rename(columns={"date": "period_date"}), on=["period_date", "target"], how="inner"
    )
    scored = scored.merge(
        actual.rename(columns={"date": "origin", "actual": "persistence"}),
        on=["origin", "target"],
        how="left",
    )
    scored = scored.rename(columns={"value": "forecast"})
    scored["abs_error"] = (scored["forecast"] - scored["actual"]).abs()
    scored["persistence_abs_error"] = (scored["persistence"] - scored["actual"]).abs()
    has_range = scored["low"].notna() & scored["high"].notna()
    inside = (scored["actual"] >= scored["low"]) & (scored["actual"] <= scored["high"])
    scored["in_range"] = inside.where(has_range)
    scored = scored.dropna(subset=["forecast"])
    for column in ("actual", "persistence", "abs_error", "persistence_abs_error"):
        scored[column] = scored[column].round(3)
    scored = scored.sort_values(["period", "target", "label", "source"])
    return scored[ACCURACY_COLUMNS].reset_index(drop=True)


def _round(value: float) -> float | None:
    return None if pd.isna(value) else round(float(value), 3)


def summarize(scored: pd.DataFrame, generated_at: str) -> dict[str, Any]:
    """Rolling accuracy per target, horizon and source, plus degradation alerts.

    Persistence is compared only on days where both it and the forecast exist,
    so a missing day cannot flatter either side.
    """
    summary: dict[str, Any] = {
        "generated_at": generated_at,
        "latest_scored": None,
        "windows": list(WINDOWS),
        "rows": [],
        "alerts": [],
    }
    if scored.empty:
        return summary
    periods = pd.to_datetime(scored["period"])
    latest = periods.max()
    summary["latest_scored"] = latest.date().isoformat()
    for (target, label, source), group in scored.groupby(["target", "label", "source"]):
        group_periods = pd.to_datetime(group["period"])
        for window in WINDOWS:
            recent = group[group_periods > latest - pd.Timedelta(days=window)]
            paired = recent.dropna(subset=["persistence_abs_error"])
            mae = recent["abs_error"].mean()
            paired_mae = paired["abs_error"].mean()
            persistence_mae = paired["persistence_abs_error"].mean()
            skill = (
                1 - paired_mae / persistence_mae
                if len(paired) and persistence_mae > 0
                else np.nan
            )
            row = {
                "target": target,
                "label": label,
                "source": source,
                "window_days": window,
                "n": int(len(recent)),
                "mae": _round(mae),
                "persistence_mae": _round(persistence_mae),
                "skill_vs_persistence": _round(skill),
                "coverage": _round(recent["in_range"].astype(float).mean()),
            }
            summary["rows"].append(row)
            if (
                source == "forecast"
                and window == DEGRADATION_WINDOW
                and len(paired) >= DEGRADATION_MIN_DAYS
                and paired_mae > persistence_mae
            ):
                summary["alerts"].append(
                    f"{target} {label}: published forecast MAE {paired_mae:.2f} is worse than "
                    f"persistence {persistence_mae:.2f} over the last {window} days ({len(paired)} days scored)"
                )
    return summary
