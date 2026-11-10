"""Temperature and humidity forecasts from the Thai Meteorological Department (TMD).

TMD runs a 3 km weather model over Thailand. Its forecast is published next to
our own as an independent reference, never mixed into our model.
"""

from __future__ import annotations

import time as time_module
from collections.abc import Callable
from typing import Any

import pandas as pd
import requests

from pm25.features import TIMEZONE
from pm25.ingest import get_with_retry

TMD_URL = "https://data.tmd.go.th/nwpapi/v1/forecast/location/hourly/at"
MIN_HOURS_PER_DAY = 18


def fetch_tmd_daily(
    token: str,
    latitude: float,
    longitude: float,
    as_of: pd.Timestamp,
    days: int = 2,
    http_get: Callable[..., Any] = requests.get,
    sleep: Callable[[float], None] = time_module.sleep,
) -> dict[str, dict[str, float]]:
    """Return daily mean, minimum and maximum temperature and mean humidity per local date."""
    response = get_with_retry(
        http_get,
        TMD_URL,
        {
            "lat": latitude,
            "lon": longitude,
            "fields": "tc,rh",
            "date": as_of.date().isoformat(),
            "hour": 0,
            "duration": 24 * days,
        },
        sleep,
        pause=0.0,
        headers={"accept": "application/json", "authorization": f"Bearer {token}"},
    )
    forecasts = response.json()["WeatherForecasts"][0]["forecasts"]
    frame = pd.DataFrame(
        {
            "time": [item["time"] for item in forecasts],
            "tc": [item["data"].get("tc") for item in forecasts],
            "rh": [item["data"].get("rh") for item in forecasts],
        }
    )
    frame["date"] = pd.to_datetime(frame["time"], utc=True).dt.tz_convert(TIMEZONE).dt.date
    summary: dict[str, dict[str, float]] = {}
    for day, group in frame.groupby("date"):
        valid = group.dropna(subset=["tc", "rh"])
        if len(valid) < MIN_HOURS_PER_DAY:
            continue
        summary[day.isoformat()] = {
            "temp_c": round(float(valid["tc"].mean()), 1),
            "temp_c_min": round(float(valid["tc"].min()), 1),
            "temp_c_max": round(float(valid["tc"].max()), 1),
            "rh_pct": round(float(valid["rh"].mean()), 1),
        }
    return summary
