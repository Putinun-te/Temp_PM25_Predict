"""Archive of CAMS PM2.5 forecasts for today and tomorrow, kept for later training.

The CAMS forecast for the target day is a promising feature, but Open-Meteo does
not keep past CAMS forecasts (its `previous_day` air quality fields are empty),
and its history is the analysis, which would leak hindsight. So the pipeline
saves each morning's forecast from now on. Once about a year has accumulated it
can be tested as a feature under the same promotion gate.
"""

from __future__ import annotations

import time as time_module
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from pm25.features import MIN_HOURS_PER_DAY, TIMEZONE
from pm25.ingest import get_with_retry, load_series, upsert

CAMS_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
CAMS_FILENAME = "cams_forecast_archive.csv"


def fetch_cams_forecast(
    latitude: float,
    longitude: float,
    as_of: pd.Timestamp,
    issued_at: str,
    http_get: Callable[..., Any] = requests.get,
    sleep: Callable[[float], None] = time_module.sleep,
) -> pd.DataFrame:
    """Return the Bangkok daily mean CAMS PM2.5 forecast for as_of and the day after."""
    response = get_with_retry(
        http_get,
        CAMS_URL,
        {"latitude": latitude, "longitude": longitude, "hourly": "pm2_5", "forecast_days": 3, "timezone": "GMT"},
        sleep,
        pause=0.2,
    )
    hourly = response.json()["hourly"]
    times = pd.to_datetime(hourly["time"], utc=True)
    frame = pd.DataFrame({"date": times.tz_convert(TIMEZONE).tz_localize(None).normalize(), "pm25": pd.to_numeric(pd.Series(hourly["pm2_5"]), errors="coerce")})
    rows = []
    for horizon in (1, 2):
        day = as_of + pd.Timedelta(days=horizon - 1)
        values = frame.loc[frame["date"] == day, "pm25"].dropna()
        if len(values) >= MIN_HOURS_PER_DAY:
            rows.append(
                {
                    "time": pd.Timestamp(day, tz=TIMEZONE).tz_convert("UTC"),
                    "issued": as_of.date().isoformat(),
                    "issued_at": issued_at,
                    "horizon_days": horizon,
                    "cams_pm25": round(float(values.mean()), 2),
                }
            )
    return pd.DataFrame(rows)


def archive_cams(data_dir: Path, frame: pd.DataFrame) -> int:
    """Add today's rows. A rerun on the same day replaces them."""
    return upsert(data_dir / CAMS_FILENAME, frame, keys=["time", "horizon_days"])


def load_archive(data_dir: Path) -> pd.DataFrame:
    return load_series(data_dir / CAMS_FILENAME)
