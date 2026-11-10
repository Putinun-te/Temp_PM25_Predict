"""Idempotent ingestion of Open-Meteo air quality and weather data.

Every series is stored as CSV with UTC timestamps. A run finds the hours that
are missing locally, fetches only those, and upserts by timestamp, so repeating
a run never creates duplicates.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

TIME = "time"
HOUR = pd.Timedelta(hours=1)


def load_series(path: Path) -> pd.DataFrame:
    """Read a stored series, or return an empty frame if it does not exist yet."""
    if not path.exists():
        return pd.DataFrame({TIME: pd.DatetimeIndex([], tz="UTC")})
    frame = pd.read_csv(path)
    frame[TIME] = pd.to_datetime(frame[TIME], utc=True)
    return frame


def upsert(path: Path, new: pd.DataFrame) -> int:
    """Merge rows into a stored series and return how many new timestamps were added.

    The file is replaced atomically, so a crash cannot leave it half written.
    On a timestamp conflict the incoming row wins.
    """
    if new.empty:
        return 0
    old = load_series(path)
    combined = pd.concat([old, new], ignore_index=True) if not old.empty else new
    combined = (
        combined.drop_duplicates(TIME, keep="last").sort_values(TIME).reset_index(drop=True)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(descriptor)
    try:
        combined.to_csv(temporary, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return len(combined) - len(old)


def find_gaps(
    times: Iterable[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    step: pd.Timedelta,
    tolerance: float = 1.5,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Return missing ranges in [start, end] as (low, high) pairs, both exclusive.

    A gap is any distance between neighbouring points above step * tolerance.
    Virtual points one step outside the window make the head and tail of the
    window behave like any other gap.
    """
    if start > end:
        return []
    index = pd.to_datetime(list(times), utc=True).unique().sort_values()
    inside = index[(index >= start) & (index <= end)]
    points = [start - step, *inside, end + step]
    return [(low, high) for low, high in zip(points, points[1:]) if high - low > step * tolerance]


# --- Open-Meteo reference data ---


@dataclass(frozen=True)
class OpenMeteoSource:
    """One Open-Meteo endpoint and the mapping from its variables to our columns."""

    filename: str
    url: str
    variables: Mapping[str, str]


AIR_QUALITY = OpenMeteoSource(
    filename="openmeteo_air_quality.csv",
    url="https://air-quality-api.open-meteo.com/v1/air-quality",
    variables={
        "pm2_5": "om_pm25",
        "pm10": "om_pm10",
        "nitrogen_dioxide": "om_no2",
        "ozone": "om_o3",
        "sulphur_dioxide": "om_so2",
        "carbon_monoxide": "om_co",
    },
)

WEATHER = OpenMeteoSource(
    filename="openmeteo_weather.csv",
    url="https://archive-api.open-meteo.com/v1/archive",
    variables={
        "temperature_2m": "om_temp_c",
        "relative_humidity_2m": "om_rh_pct",
        "precipitation": "om_precip_mm",
        "wind_speed_10m": "om_wind_kmh",
        "wind_direction_10m": "om_wind_deg",
    },
)


def _date_ranges(
    gaps: Iterable[tuple[pd.Timestamp, pd.Timestamp]],
    step: pd.Timedelta,
    max_days: int = 90,
) -> list[tuple[date, date]]:
    """Convert exclusive gaps to inclusive date ranges, merged and split into small requests."""
    spans = sorted(
        (min(first, last), max(first, last))
        for first, last in (((low + step).date(), (high - step).date()) for low, high in gaps)
    )
    merged: list[tuple[date, date]] = []
    for first, last in spans:
        if merged and first <= merged[-1][1] + timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], last))
        else:
            merged.append((first, last))

    chunks: list[tuple[date, date]] = []
    for first, last in merged:
        while first <= last:
            stop = min(first + timedelta(days=max_days - 1), last)
            chunks.append((first, stop))
            first = stop + timedelta(days=1)
    return chunks


def fetch_open_meteo(
    source: OpenMeteoSource,
    latitude: float,
    longitude: float,
    first: date,
    last: date,
    http_get: Callable[..., Any] = requests.get,
) -> pd.DataFrame:
    """Fetch hourly UTC values and drop hours where every variable is null.

    Null hours must not be stored: they would look filled and never be retried
    once the source publishes them.
    """
    response = http_get(
        source.url,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(source.variables),
            "start_date": first.isoformat(),
            "end_date": last.isoformat(),
            "timezone": "GMT",
        },
        timeout=60,
    )
    response.raise_for_status()
    hourly = response.json()["hourly"]
    frame = pd.DataFrame({TIME: pd.to_datetime(hourly["time"], utc=True)})
    for api_name, column in source.variables.items():
        frame[column] = pd.to_numeric(pd.Series(hourly.get(api_name)), errors="coerce")
    return frame.dropna(subset=list(source.variables.values()), how="all")


def backfill_open_meteo(
    source: OpenMeteoSource,
    data_dir: Path,
    latitude: float,
    longitude: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
    http_get: Callable[..., Any] = requests.get,
) -> int:
    """Fetch only the hours missing from [start, end] and return how many were added.

    Open-Meteo returns whole days, so hours after `end` are removed. Those are
    forecasts, and storing them as history would leak the future into training.
    """
    path = data_dir / source.filename
    gaps = find_gaps(load_series(path)[TIME], start, end, HOUR)
    added = 0
    for first, last in _date_ranges(gaps, HOUR):
        frame = fetch_open_meteo(source, latitude, longitude, first, last, http_get)
        added += upsert(path, frame[(frame[TIME] >= start) & (frame[TIME] <= end)])
    return added
