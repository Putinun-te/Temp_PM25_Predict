"""Score published forecasts against what was later measured.

Walk-forward validation estimates accuracy before a model is used. This module
checks the forecasts that were actually published, once the measured value for
their date exists. Each forecast is compared with persistence as it stood on
the day the forecast was issued: the newest measured day before `as_of`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pm25.evaluate import STANDARDS
from pm25.features import ALL_TARGETS
from pm25.station_model import LABELS as STATION_HORIZON_LABELS

ACCURACY_FILENAME = "live_accuracy.csv"
SUMMARY_FILENAME = "live_accuracy_summary.json"
HOURLY_HISTORY_FILENAME = "hourly_forecast_history.csv"
STATION_HISTORY_FILENAME = "station_forecast_history.csv"
HOURLY_ACCURACY_FILENAME = "live_accuracy_hourly.csv"
STATION_ACCURACY_FILENAME = "live_accuracy_stations.csv"
HOURLY_KEYS = ["as_of", "time", "known_hour", "target"]
STATION_KEYS = ["as_of", "period", "location_id", "target"]
# The morning hourly run sees measurements up to this hour of the forecast day (see pm25.hourly).
LAST_KNOWN_HOUR = 3
WINDOWS = (7, 30, 90)
# TMD forecasts are scored against the same measured series as our own temperature
# and humidity forecasts, so the two can be compared directly.
TMD_TARGETS = {"tmd_temp_c": "temp_c", "tmd_rh_pct": "rh_pct"}
# A model is flagged only after enough scored days, so one bad week does not alert.
DEGRADATION_WINDOW = 30
DEGRADATION_MIN_DAYS = 14
# Ranges aim to hold 80 % of outcomes; below this over 30 days they have drifted.
MIN_LIVE_COVERAGE = 0.65
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
    "p_above_standard",
    "above_standard",
    "p_above",
]


def _add_events(scored: pd.DataFrame) -> pd.DataFrame:
    """Mark whether the measured value went above the standard, where a chance was published."""
    if "p_above" not in scored:
        scored["p_above"] = None
    if "p_above_standard" not in scored:
        scored["p_above_standard"] = np.nan
    scored["p_above_standard"] = pd.to_numeric(scored["p_above_standard"], errors="coerce")
    threshold = scored["target"].map(STANDARDS)
    above = (scored["actual"] > threshold).astype(float)
    scored["above_standard"] = above.where(scored["p_above_standard"].notna() & threshold.notna())
    return scored


def _parse_chances(text: Any) -> list[dict[str, float]]:
    """The chances kept as JSON in a history row, or none."""
    if not isinstance(text, str) or not text.strip():
        return []
    try:
        return [item for item in json.loads(text) if item.get("p") is not None]
    except (ValueError, AttributeError, TypeError):
        return []


def chance_outcomes(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per published chance and band edge: the edge, the chance and whether it was crossed.

    Rows from before several edges were kept carry only the chance above the standard.
    """
    records = []
    for row in rows.itertuples(index=False):
        actual = getattr(row, "actual", np.nan)
        if pd.isna(actual):
            continue
        chances = _parse_chances(getattr(row, "p_above", None))
        standard = getattr(row, "p_above_standard", np.nan)
        if not chances and not pd.isna(standard) and row.target in STANDARDS:
            chances = [{"threshold": STANDARDS[row.target], "p": float(standard)}]
        for item in chances:
            threshold = float(item["threshold"])
            records.append({"threshold": threshold, "p": float(item["p"]), "event": float(actual > threshold)})
    return pd.DataFrame(records, columns=["threshold", "p", "event"])


def _brier(outcomes: pd.DataFrame) -> dict[str, Any]:
    outcome = outcomes["event"]
    return {
        "chance_n": int(len(outcomes)),
        "chance_events": int(outcome.sum()),
        "brier": _round(((outcomes["p"] - outcome) ** 2).mean()),
        "base_rate_brier": _round(((outcome.mean() - outcome) ** 2).mean()),
    }


def chance_scores(rows: pd.DataFrame) -> dict[str, Any]:
    """Brier score of the published chances, next to always saying the rate seen in the same rows.

    The reference uses the rows' own rate, which it could not have known in
    advance, so it is a hard comparison while there are few events. The top
    level fields score the standard; `chances` scores every band edge.
    """
    if rows.empty or "target" not in rows or ("p_above" not in rows and "p_above_standard" not in rows):
        return {}
    has_chance = rows[[c for c in ("p_above", "p_above_standard") if c in rows]].notna().any(axis=1)
    outcomes = chance_outcomes(rows[has_chance])
    if outcomes.empty:
        return {}
    result: dict[str, Any] = {}
    standards = {STANDARDS[t] for t in rows["target"].unique() if t in STANDARDS}
    at_standard = outcomes[outcomes["threshold"].isin(standards)]
    if not at_standard.empty:
        result.update(_brier(at_standard))
    result["chances"] = [
        {"threshold": float(threshold), **_brier(group)} for threshold, group in outcomes.groupby("threshold")
    ]
    return result


def coverage_alerts(name: str, rows: list[dict[str, Any]]) -> list[str]:
    """Alerts for ranges that held too few outcomes over the last 30 days."""
    alerts = []
    for row in rows:
        days = row.get("days", row["n"])
        coverage = row.get("coverage")
        if (
            row["window_days"] == DEGRADATION_WINDOW
            and days >= DEGRADATION_MIN_DAYS
            and coverage is not None
            and coverage < MIN_LIVE_COVERAGE
        ):
            alerts.append(
                f"{name} {row['label']}: the 80 % range held only {coverage:.0%} of outcomes "
                f"over the last {DEGRADATION_WINDOW} days ({days} days scored)"
            )
    return alerts


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
    scored = _add_events(scored.dropna(subset=["forecast"]))
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
                # Mean absolute error as a share of the measured value; 100 minus this is the "match".
                "mape_pct": _round((recent["abs_error"] / recent["actual"].where(recent["actual"] > 0)).mean() * 100),
                "persistence_mae": _round(persistence_mae),
                "skill_vs_persistence": _round(skill),
                "coverage": _round(recent["in_range"].astype(float).mean()),
                **chance_scores(recent),
            }
            summary["rows"].append(row)
            if source == "forecast":
                summary["alerts"].extend(coverage_alerts(target, [row]))
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


def hourly_rows(hourly: dict[str, Any]) -> pd.DataFrame:
    """Flatten one published hourly forecast document into history rows."""
    known_hour = pd.Timestamp(hourly["inputs_through"]).hour
    rows = []
    for hour in hourly.get("hours", []):
        base = {"as_of": hourly["as_of"], "time": hour["time"], "known_hour": known_hour, "label": hour["day"]}
        rows.append({**base, "target": "pm25", "forecast": hour["pm25"], "low": hour["low"], "high": hour["high"],
                     "method": hourly["method"], "p_above": _chance_json(hour.get("p_above"))})
        # PM10 sits next to PM2.5 in the same hour, when its model exists.
        if "pm10" in hour:
            rows.append({**base, "target": "pm10", "forecast": hour["pm10"], "low": hour["pm10_low"],
                         "high": hour["pm10_high"], "method": hourly.get("pm10_method"),
                         "p_above": _chance_json(hour.get("pm10_p_above"))})
    return pd.DataFrame(
        rows, columns=["as_of", "time", "known_hour", "target", "label", "forecast", "low", "high", "method", "p_above"]
    )


def _chance_json(chances: list[dict[str, float]] | None) -> str | None:
    """Chances are kept in history files as JSON text, or left empty."""
    return json.dumps(chances) if chances else None


def station_rows(forecast: dict[str, Any]) -> pd.DataFrame:
    """Flatten the per-station forecasts of one published forecast into history rows."""
    as_of = pd.Timestamp(forecast["as_of"])
    rows = []
    for station in forecast.get("station_forecasts", []):
        for offset, label in enumerate(STATION_HORIZON_LABELS.values()):
            day = station.get(label) or {}
            # PM2.5 sits directly in the day's entry, PM10 in its own entry below it.
            for target, value in (("pm25", day), ("pm10", day.get("pm10") or {})):
                if target in value:
                    rows.append(
                        {"as_of": forecast["as_of"], "period": (as_of + pd.Timedelta(days=offset)).date().isoformat(),
                         "label": label, "location_id": station["location_id"], "target": target,
                         "forecast": value[target], "low": value["low"], "high": value["high"],
                         "method": value["method"], "p_above_standard": value.get("p_above_standard"),
                         "p_above": _chance_json(value.get("p_above"))}
                    )
    return pd.DataFrame(
        rows,
        columns=["as_of", "period", "label", "location_id", "target", "forecast", "low", "high", "method",
                 "p_above_standard", "p_above"],
    )


# Files written before these columns existed hold only the morning run and only PM2.5.
HISTORY_DEFAULTS = {"known_hour": str(LAST_KNOWN_HOUR), "target": "pm25"}


def read_history(path: Path, keys: list[str]) -> pd.DataFrame:
    """Read a history file with its key columns as text, filling columns added later."""
    table = pd.read_csv(path, dtype={key: str for key in keys})
    for key in keys:
        if key in HISTORY_DEFAULTS:
            table[key] = table[key].fillna(HISTORY_DEFAULTS[key]) if key in table else HISTORY_DEFAULTS[key]
    return table


def append_rows(path: Path, table: pd.DataFrame, keys: list[str]) -> None:
    """Add rows to a history file. Rerunning a day replaces that day's rows."""
    if table.empty:
        return
    table = table.astype({key: str for key in keys})
    if path.exists():
        table = pd.concat([read_history(path, keys), table], ignore_index=True)
    table = table.drop_duplicates(keys, keep="last").sort_values(keys)
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)


def _finish(scored: pd.DataFrame) -> pd.DataFrame:
    """Add the error columns shared by the hourly and station scores."""
    scored = scored.dropna(subset=["forecast", "actual"]).copy()
    scored["abs_error"] = (scored["forecast"] - scored["actual"]).abs().round(3)
    scored["persistence_abs_error"] = (scored["persistence"] - scored["actual"]).abs().round(3)
    has_range = scored["low"].notna() & scored["high"].notna()
    inside = (scored["actual"] >= scored["low"]) & (scored["actual"] <= scored["high"])
    scored["in_range"] = inside.where(has_range)
    if "p_above_standard" in scored or "p_above" in scored:
        scored = _add_events(scored)
    return scored.reset_index(drop=True)


def score_hourly(history: pd.DataFrame, city: pd.Series) -> pd.DataFrame:
    """Score published hourly forecasts against the measured city hours.

    `city` is the hourly city series indexed by local time. The baseline is the
    newest value at the same hour of day that was known when the forecast was made.
    """
    rows = history.copy()
    time = pd.to_datetime(rows["time"])
    as_of = pd.to_datetime(rows["as_of"])
    hour = time.dt.hour
    known = as_of + pd.to_timedelta(hour.where(hour <= rows["known_hour"].astype(int), hour - 24), unit="h")
    rows["actual"] = city.reindex(time).to_numpy()
    rows["persistence"] = city.reindex(known).to_numpy()
    rows["period"] = time.dt.date.astype(str)
    return _finish(rows)


def score_stations(history: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """Score published station forecasts against each station's measured daily value.

    `stations` has one column per location id, indexed by date, and `history`
    holds one target. Persistence is the station's own value on the day before
    the forecast was issued.
    """
    measured = stations.copy()
    measured.columns = [str(column) for column in measured.columns]
    long = measured.rename_axis("date").reset_index().melt(id_vars="date", var_name="location_id", value_name="actual")
    rows = history.copy()
    rows["location_id"] = rows["location_id"].astype(str)
    rows["date"] = pd.to_datetime(rows["period"])
    rows["origin"] = pd.to_datetime(rows["as_of"]) - pd.Timedelta(days=1)
    scored = rows.merge(long, on=["date", "location_id"], how="left")
    scored = scored.merge(
        long.rename(columns={"date": "origin", "actual": "persistence"}), on=["origin", "location_id"], how="left"
    )
    return _finish(scored.drop(columns=["date", "origin"]))


def summarize_extra(scored: pd.DataFrame) -> list[dict[str, Any]]:
    """Rolling accuracy per label for the hourly or station scores, same windows as `summarize`."""
    result: list[dict[str, Any]] = []
    if scored.empty:
        return result
    periods = pd.to_datetime(scored["period"])
    latest = periods.max()
    for label, group in scored.groupby("label"):
        group_periods = pd.to_datetime(group["period"])
        for window in WINDOWS:
            recent = group[group_periods > latest - pd.Timedelta(days=window)]
            paired = recent.dropna(subset=["persistence_abs_error"])
            result.append(
                {
                    "label": label,
                    "window_days": window,
                    "n": int(len(recent)),
                    "days": int(recent["period"].nunique()),
                    "mae": _round(recent["abs_error"].mean()),
                    "mape_pct": _round((recent["abs_error"] / recent["actual"].where(recent["actual"] > 0)).mean() * 100),
                    "paired_mae": _round(paired["abs_error"].mean()),
                    "persistence_mae": _round(paired["persistence_abs_error"].mean()),
                    "coverage": _round(recent["in_range"].astype(float).mean()),
                    **chance_scores(recent),
                }
            )
    return result
