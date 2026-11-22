"""A weekly summary of what was measured, how the published forecasts scored and what comes next.

Written every Monday as a GitHub issue, so the haze season can be followed
without opening the dashboard. Everything comes from files the daily run
already writes: the silver daily data, the live accuracy summary and the
newest forecast.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from pm25.evaluate import STANDARDS

WEEK_DAYS = 7
TARGET_NAMES = {"pm25": "PM2.5", "pm10": "PM10", "temp_c": "Temperature", "rh_pct": "Humidity"}
EXTRA_NAMES = {
    "hourly": "Hourly PM2.5, morning run",
    "hourly_afternoon": "Hourly PM2.5, afternoon run",
    "hourly_evening": "Hourly PM2.5, evening run",
    "hourly_pm10": "Hourly PM10, morning run",
    "hourly_pm10_afternoon": "Hourly PM10, afternoon run",
    "hourly_pm10_evening": "Hourly PM10, evening run",
    "stations": "Station PM2.5",
    "stations_pm10": "Station PM10",
}


def _number(value: Any, digits: int = 2) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{float(value):.{digits}f}"


def _percent(value: Any) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{float(value):.0%}"


def _chance(value: Any) -> str:
    """Like the dashboard: a small chance never reads as none."""
    if value is None or pd.isna(value):
        return "n/a"
    return "<1%" if value < 0.01 else ">99%" if value > 0.99 else f"{value:.0%}"


def _measured(daily: pd.DataFrame, start: date, end: date) -> list[str]:
    frame = daily.assign(date=pd.to_datetime(daily["date"]).dt.date)
    week = frame[(frame["date"] >= start) & (frame["date"] <= end)]
    lines = ["## Measured", ""]
    if week.empty:
        return lines + ["No measured days in this week.", ""]
    lines += ["| Value | Mean | Highest | Days above the standard |", "|---|---|---|---|"]
    for target in ("pm25", "pm10"):
        values = week[target].dropna()
        if values.empty:
            continue
        peak = week.loc[values.idxmax(), "date"]
        above = int((values > STANDARDS[target]).sum())
        lines.append(
            f"| {TARGET_NAMES[target]} µg/m³ | {values.mean():.1f} | {values.max():.1f} ({peak}) "
            f"| {above} of {len(values)} (standard {STANDARDS[target]:g}) |"
        )
    for target, unit in (("temp_c", "°C"), ("rh_pct", "%")):
        values = week[target].dropna() if target in week else pd.Series(dtype=float)
        if not values.empty:
            lines.append(f"| {TARGET_NAMES[target]} {unit} | {values.mean():.1f} | {values.max():.1f} | – |")
    return lines + [""]


def _city_scores(summary: dict[str, Any]) -> list[str]:
    rows = [
        row
        for row in summary.get("rows", [])
        if row["window_days"] == WEEK_DAYS and row["source"] == "forecast" and row["n"] > 0
        and row["label"] in ("today", "tomorrow", "day3", "day6")
    ]
    lines = ["## City forecasts, last 7 days", ""]
    if not rows:
        return lines + ["Nothing scored this week.", ""]
    lines += [
        "| Value | Day | Scored | MAE | Persistence MAE | Skill | Inside range |",
        "|---|---|---|---|---|---|---|",
    ]
    order = list(TARGET_NAMES)
    labels = ["today", "tomorrow", "day3", "day6"]
    for row in sorted(rows, key=lambda r: (order.index(r["target"]), labels.index(r["label"]))):
        lines.append(
            f"| {TARGET_NAMES[row['target']]} | {row['label']} | {row['n']} | {_number(row['mae'])} "
            f"| {_number(row['persistence_mae'])} | {_percent(row['skill_vs_persistence'])} | {_percent(row['coverage'])} |"
        )
    return lines + [""]


def _extra_scores(summary: dict[str, Any]) -> list[str]:
    lines = ["## Hourly and station forecasts, last 7 days", ""]
    body = []
    for key, name in EXTRA_NAMES.items():
        for row in summary.get(key) or []:
            if row["window_days"] != WEEK_DAYS or row["n"] == 0:
                continue
            body.append(
                f"| {name} | {row['label']} | {row['n']} | {_number(row['mae'])} "
                f"| {_number(row['persistence_mae'])} | {_percent(row['coverage'])} |"
            )
    if not body:
        return lines + ["Nothing scored this week.", ""]
    return lines + ["| Forecast | Day | Scored | MAE | Baseline MAE | Inside range |", "|---|---|---|---|---|---|", *body, ""]


def _chance_scores(summary: dict[str, Any]) -> list[str]:
    sources = [(f"City {TARGET_NAMES[row['target']]}", row) for row in summary.get("rows", [])
               if row["source"] == "forecast" and row["target"] in STANDARDS]
    sources += [(EXTRA_NAMES[key], row) for key in ("stations", "stations_pm10") for row in summary.get(key) or []]
    body = []
    for name, row in sources:
        if row["window_days"] != WEEK_DAYS:
            continue
        for score in row.get("chances") or []:
            if not score.get("chance_n"):
                continue
            body.append(
                f"| {name} | {row['label']} | {score['threshold']:g} | {score['chance_n']} | {score['chance_events']} "
                f"| {_number(score['brier'], 3)} | {_number(score['base_rate_brier'], 3)} |"
            )
    lines = ["## Chance above the band edges, last 7 days", ""]
    if not body:
        return lines + ["No published chance was scored this week.", ""]
    return lines + [
        "Brier score, 0 is perfect. The reference always says the share of days above the edge in the same week.",
        "",
        "| Forecast | Day | Edge µg/m³ | Scored | Times above | Brier | Reference |",
        "|---|---|---|---|---|---|---|",
        *body,
        "",
    ]


def _outlook(forecast: dict[str, Any] | None) -> list[str]:
    lines = ["## The coming week", ""]
    if not forecast:
        return lines + ["No forecast found.", ""]
    lines += [f"Forecast of {forecast['as_of']}.", "", "| Date | PM2.5 | Range | Chance above 37.5 |", "|---|---|---|---|"]
    for row in forecast.get("daily", []):
        chance = row.get("pm25_p_above_standard")
        lines.append(
            f"| {row['date']} | {_number(row.get('pm25'), 1)} | {_number(row.get('pm25_low'), 1)} to "
            f"{_number(row.get('pm25_high'), 1)} | {_chance(chance)} |"
        )
    return lines + [""]


def _inputs(check: dict[str, Any] | None) -> list[str]:
    lines = ["## Forecast inputs against the stored data", ""]
    if not check or not check.get("forecasts"):
        return lines + ["No saved forecast inputs yet.", ""]
    rows = [f for f in check["features"] if f["missing_at_forecast"] or f["missing_now"] or f["changed"]]
    lines += [
        f"{check['forecasts']} forecasts in the last {check['days']} days. Weather forecast inputs (`nwp_`) are "
        "expected to change: a past day's forecast is later replaced by the run issued the right number of days "
        "before it. Any other input that differs means training and forecasting saw different data.",
        "",
    ]
    if not rows:
        return lines + ["Every input matched.", ""]
    lines += ["| Input | Compared | Missing at forecast | Missing now | Changed | Mean difference |", "|---|---|---|---|---|---|"]
    for f in rows[:12]:
        lines.append(
            f"| {f['feature']} | {f['compared']} | {f['missing_at_forecast']} | {f['missing_now']} "
            f"| {f['changed']} | {_number(f['mean_abs_diff'], 3)} |"
        )
    if len(rows) > 12:
        lines.append(f"\n{len(rows) - 12} more inputs differ; see gold/served_feature_check.json.")
    return lines + [""]


def build_weekly(
    daily: pd.DataFrame,
    summary: dict[str, Any] | None,
    forecast: dict[str, Any] | None,
    today: date,
    served_check: dict[str, Any] | None = None,
) -> str:
    """Return the weekly summary as Markdown for the seven days before `today`."""
    start, end = today - timedelta(days=WEEK_DAYS), today - timedelta(days=1)
    summary = summary or {}
    lines = [f"Week of {start} to {end}.", ""]
    lines += _measured(daily, start, end)
    lines += _city_scores(summary)
    lines += _extra_scores(summary)
    lines += _chance_scores(summary)
    alerts = summary.get("alerts") or []
    lines += ["## Alerts", ""] + ([f"- {alert}" for alert in alerts] or ["None."]) + [""]
    lines += _inputs(served_check)
    lines += _outlook(forecast)
    return "\n".join(lines)
