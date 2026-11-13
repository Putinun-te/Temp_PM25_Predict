"""Idempotent ingestion of OpenAQ station data and Open-Meteo model data.

OpenAQ supplies measured concentrations, which are the forecast target.
Open-Meteo supplies weather and modelled pollutants, which are features only.

Every series is stored as CSV with UTC timestamps. A run finds the hours that
are missing locally, fetches only those, and upserts by key, so repeating a run
never creates duplicates.
"""

from __future__ import annotations

import os
import tempfile
import time as time_module
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
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


def upsert(path: Path, new: pd.DataFrame, keys: Sequence[str] = (TIME,)) -> int:
    """Merge rows into a stored series and return how many new keys were added.

    The file is replaced atomically, so a crash cannot leave it half written.
    On a key conflict the incoming row wins.
    """
    if new.empty:
        return 0
    old = load_series(path)
    combined = pd.concat([old, new], ignore_index=True) if not old.empty else new
    combined = (
        combined.drop_duplicates(list(keys), keep="last")
        .sort_values(list(keys))
        .reset_index(drop=True)
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
    extra: Mapping[str, str] = field(default_factory=dict)  # Extra query parameters, such as a model


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


OPEN_METEO_SECONDS_BETWEEN_REQUESTS = 0.2


def get_with_retry(
    http_get: Callable[..., Any],
    url: str,
    params: Mapping[str, Any],
    sleep: Callable[[float], None],
    pause: float,
    headers: Mapping[str, str] | None = None,
    attempts: int = 5,
    timeout: float = 120,
) -> Any:
    """GET with pacing, waiting out rate limits and retrying network and server errors.

    Shared CI runners see slow or refused connections now and then, so one
    failed request must not end the whole run.
    """
    options: dict[str, Any] = {"params": params, "timeout": timeout}
    if headers:
        options["headers"] = headers
    response = None
    for attempt in range(attempts):
        sleep(pause)
        try:
            response = http_get(url, **options)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == attempts - 1:
                raise
            sleep(5 * (attempt + 1))
            continue
        if response.status_code == 429:
            sleep(int(response.headers.get("x-ratelimit-reset", 60)) + 1)
        elif response.status_code >= 500:
            sleep(5 * (attempt + 1))
        else:
            break
    response.raise_for_status()
    return response


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
    sleep: Callable[[float], None] = time_module.sleep,
) -> pd.DataFrame:
    """Fetch hourly UTC values and drop hours where every variable is null.

    Null hours must not be stored: they would look filled and never be retried
    once the source publishes them.
    """
    response = get_with_retry(
        http_get,
        source.url,
        {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(source.variables),
            "start_date": first.isoformat(),
            "end_date": last.isoformat(),
            "timezone": "GMT",
            **source.extra,
        },
        sleep,
        pause=OPEN_METEO_SECONDS_BETWEEN_REQUESTS,
    )
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
    sleep: Callable[[float], None] = time_module.sleep,
) -> int:
    """Fetch only the hours missing from [start, end] and return how many were added.

    Open-Meteo returns whole days, so hours after `end` are removed. Those are
    forecasts, and storing them as history would leak the future into training.
    """
    path = data_dir / source.filename
    gaps = find_gaps(load_series(path)[TIME], start, end, HOUR)
    added = 0
    for first, last in _date_ranges(gaps, HOUR):
        frame = fetch_open_meteo(source, latitude, longitude, first, last, http_get, sleep)
        added += upsert(path, frame[(frame[TIME] >= start) & (frame[TIME] <= end)])
    return added


# --- OpenAQ station data ---

OPENAQ_URL = "https://api.openaq.org/v3/sensors/{sensor_id}/hours"
OPENAQ_FILENAME = "openaq_hourly.csv"
SENSOR = "sensor_id"
PARAMETER = "parameter"
VALUE = "value"
OPENAQ_SECONDS_BETWEEN_REQUESTS = 1.05  # The free tier allows 60 requests per minute
MAX_PLAUSIBLE_CONCENTRATION = 1000.0


@dataclass(frozen=True)
class OpenAQSensor:
    sensor_id: int
    parameter: str
    location_id: int


# Fixed panel of Air4Thai reference monitors within 25 km of central Bangkok.
# They were chosen for reporting steadily from 2021 to now. The panel must stay
# fixed: a changing set of stations would look like a change in air quality.
OPENAQ_PANEL = (
    OpenAQSensor(1304255, "pm25", 701),
    OpenAQSensor(1304120, "pm25", 2375),
    OpenAQSensor(1304207, "pm25", 906),
    OpenAQSensor(1304205, "pm25", 2167),
    OpenAQSensor(1304222, "pm25", 5545),
    OpenAQSensor(1304328, "pm25", 225612),
    OpenAQSensor(1304077, "pm25", 225629),
    OpenAQSensor(1304404, "pm25", 225637),
    OpenAQSensor(1304152, "pm25", 225650),
    OpenAQSensor(1304128, "pm25", 225653),
    OpenAQSensor(1304406, "pm10", 225629),
    OpenAQSensor(1304308, "pm10", 225637),
    OpenAQSensor(1304271, "pm10", 225650),
)


def _openaq_get(
    http_get: Callable[..., Any],
    url: str,
    params: Mapping[str, Any],
    api_key: str,
    sleep: Callable[[float], None],
) -> Any:
    return get_with_retry(
        http_get,
        url,
        params,
        sleep,
        pause=OPENAQ_SECONDS_BETWEEN_REQUESTS,
        headers={"X-API-Key": api_key},
    )


def fetch_openaq_hours(
    sensor: OpenAQSensor,
    first: date,
    last: date,
    api_key: str,
    http_get: Callable[..., Any] = requests.get,
    sleep: Callable[[float], None] = time_module.sleep,
    page_size: int = 1000,
) -> pd.DataFrame:
    """Fetch hourly averages for whole UTC days, labelled by the start of each hour.

    Missing, negative and implausibly large values are dropped, so those hours
    stay visible as gaps instead of entering the target.
    """
    rows = []
    page = 1
    while True:
        response = _openaq_get(
            http_get,
            OPENAQ_URL.format(sensor_id=sensor.sensor_id),
            {
                "datetime_from": f"{first.isoformat()}T00:00:00Z",
                "datetime_to": f"{last.isoformat()}T23:59:59Z",
                "limit": page_size,
                "page": page,
            },
            api_key,
            sleep,
        )
        results = response.json()["results"]
        rows.extend((item["period"]["datetimeFrom"]["utc"], item["value"]) for item in results)
        if len(results) < page_size:
            break
        page += 1

    frame = pd.DataFrame(rows, columns=[TIME, VALUE])
    frame[TIME] = pd.to_datetime(frame[TIME], utc=True)
    frame[VALUE] = pd.to_numeric(frame[VALUE], errors="coerce")
    frame = frame[frame[VALUE].between(0.0, MAX_PLAUSIBLE_CONCENTRATION)].copy()
    frame[SENSOR] = sensor.sensor_id
    frame[PARAMETER] = sensor.parameter
    return frame[[TIME, SENSOR, PARAMETER, VALUE]]


def backfill_openaq(
    data_dir: Path,
    api_key: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    lookback_days: int = 14,
    sensors: Sequence[OpenAQSensor] = OPENAQ_PANEL,
    http_get: Callable[..., Any] = requests.get,
    sleep: Callable[[float], None] = time_module.sleep,
) -> int:
    """Fetch only the station hours missing locally and return how many were added.

    Stations have long permanent outages, so older gaps are not searched again
    on every run. Only the lookback window is, which also picks up late reports.
    Loading runs oldest first and saves as it goes, so an interrupted first load
    resumes from the last stored hour.
    """
    path = data_dir / OPENAQ_FILENAME
    stored = load_series(path)
    added = 0
    for sensor in sensors:
        mine = stored[stored[SENSOR] == sensor.sensor_id] if SENSOR in stored else stored
        window_start = start
        if not mine.empty:
            window_start = max(start, min(mine[TIME].max(), end - pd.Timedelta(days=lookback_days)))
        gaps = find_gaps(mine[TIME], window_start, end, HOUR)
        for first, last in _date_ranges(gaps, HOUR, max_days=365):
            frame = fetch_openaq_hours(sensor, first, last, api_key, http_get, sleep)
            added += upsert(path, frame[frame[TIME] <= end], keys=(TIME, SENSOR))
    return added
