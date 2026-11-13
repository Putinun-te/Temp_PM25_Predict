"""Medallion storage layout and the data quality gate between bronze and silver.

bronze: raw hourly data as fetched, one CSV per source.
silver: cleaned daily Bangkok series that passed the quality checks.
gold:   forecast history and evaluation metrics, ready for dashboards.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from pm25.features import TIMEZONE, daily_exogenous, daily_targets, with_weather_targets
from pm25.ingest import AIR_QUALITY, OPENAQ_FILENAME, PARAMETER, SENSOR, TIME, VALUE, WEATHER

BRONZE, SILVER, GOLD = "bronze", "silver", "gold"
DAILY_FILENAME = "daily_city.csv"
QUALITY_FILENAME = "quality_report.json"
MAX_AGE_HOURS = 72
MIN_PM25_NOT_ABOVE_PM10 = 0.95


def layer(data_dir: Path, name: str) -> Path:
    path = data_dir / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def migrate_to_medallion(data_dir: Path) -> list[str]:
    """Move files from the earlier flat layout into their layers. Safe to run every time."""
    moves = {
        data_dir / OPENAQ_FILENAME: data_dir / BRONZE / OPENAQ_FILENAME,
        data_dir / AIR_QUALITY.filename: data_dir / BRONZE / AIR_QUALITY.filename,
        data_dir / WEATHER.filename: data_dir / BRONZE / WEATHER.filename,
        data_dir.parent / "reports" / "forecast_history.csv": data_dir / GOLD / "forecast_history.csv",
    }
    moved = []
    for source, target in moves.items():
        if source.exists() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            moved.append(target.name)
    return moved


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    severity: str  # "error" stops the pipeline, "warning" is only reported
    detail: str


def _unique(frame: pd.DataFrame, keys: list[str], name: str) -> Check:
    duplicates = int(frame.duplicated(keys).sum())
    return Check(f"{name} has no duplicate rows", duplicates == 0, "error", f"{duplicates} duplicates")


def _within(series: pd.Series, low: float, high: float, name: str) -> Check:
    outside = int((~series.dropna().between(low, high)).sum())
    return Check(f"{name} within {low:g} to {high:g}", outside == 0, "error", f"{outside} values outside")


def _fresh(times: pd.Series, now: pd.Timestamp, name: str) -> Check:
    if times.empty:
        return Check(f"{name} is fresh", False, "error", "no rows")
    age = (now - times.max()).total_seconds() / 3600
    return Check(
        f"{name} is fresh", age <= MAX_AGE_HOURS, "error", f"newest row {age:.0f} hours old"
    )


def run_checks(
    openaq: pd.DataFrame,
    air_quality: pd.DataFrame,
    weather: pd.DataFrame,
    daily: pd.DataFrame,
    now: pd.Timestamp,
) -> list[Check]:
    """Return every check. Errors mean the data must not reach the model."""
    checks = [
        _unique(openaq, [TIME, SENSOR], "OpenAQ"),
        _unique(air_quality, [TIME], "Open-Meteo air quality"),
        _unique(weather, [TIME], "Open-Meteo weather"),
        _within(openaq[VALUE] if VALUE in openaq else pd.Series(dtype=float), 0, 1000, "Station PM"),
        _within(weather.get("om_temp_c", pd.Series(dtype=float)), -10, 50, "Temperature"),
        _within(weather.get("om_rh_pct", pd.Series(dtype=float)), 0, 100, "Humidity"),
        _fresh(openaq[TIME], now, "OpenAQ"),
        _fresh(weather[TIME], now, "Open-Meteo weather"),
    ]

    recent = daily[daily.index > daily.index.max() - pd.Timedelta(days=365)]
    both = recent.dropna(subset=["pm25", "pm10"])
    share = float((both["pm25"] <= both["pm10"]).mean()) if len(both) else 0.0
    checks.append(
        Check(
            "PM2.5 does not exceed PM10",
            share >= MIN_PM25_NOT_ABOVE_PM10,
            "error",
            f"{share:.1%} of {len(both)} days in the last year",
        )
    )

    last_week = daily["pm25"].iloc[-7:]
    checks.append(
        Check(
            "Station panel reported most of the last week",
            int(last_week.notna().sum()) >= 5,
            "warning",
            f"{int(last_week.notna().sum())} of 7 days",
        )
    )
    return checks


def build_silver(
    openaq: pd.DataFrame,
    air_quality: pd.DataFrame,
    weather: pd.DataFrame,
    as_of: pd.Timestamp,
    fires: pd.DataFrame | None = None,
    nwp: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return the cleaned daily Bangkok table: targets plus daily weather and fire features."""
    exogenous = daily_exogenous(air_quality, weather, as_of, fires, nwp)
    targets = with_weather_targets(daily_targets(openaq, as_of), exogenous)
    extra = exogenous.drop(columns=list(targets.columns), errors="ignore").reindex(targets.index)
    return targets.join(extra)


def write_quality_report(path: Path, checks: list[Check], now: pd.Timestamp) -> dict[str, Any]:
    report = {
        "checked_at": now.tz_convert(TIMEZONE).isoformat(timespec="seconds"),
        "passed": all(check.passed for check in checks if check.severity == "error"),
        "checks": [asdict(check) for check in checks],
    }
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def write_silver(path: Path, daily: pd.DataFrame) -> None:
    daily.round(3).to_csv(path, index_label="date", date_format="%Y-%m-%d")
