"""Weather forecasts for the target day, as they were issued before it.

Station and reanalysis features only describe days that have passed. The
weather on the target day (wind, rain, humidity) matters more for PM2.5, so the
model also gets a numerical weather prediction (NWP) for that day.

Training on today's best estimate of past weather would leak hindsight. The
Open-Meteo Previous Runs API instead returns, for each hour, the value from the
model run made one or two days before (`*_previous_day1`, `*_previous_day2`).
The JMA model is used because it has these archives back to 2021.

Lead times line up with the live forecast. Bangkok day D covers 17:00 UTC on
D-1 to 17:00 UTC on D. For today (horizon 1) `previous_day1` and for tomorrow
(horizon 2) `previous_day2` both come from runs started before 17:00 UTC on
the day before the forecast is made, which the daily run at 00:17 UTC already has.
"""

from __future__ import annotations

import time as time_module
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from pm25.features import MIN_HOURS_PER_DAY, NWP_DAILY_COLUMNS, NWP_FEATURES, NWP_HORIZONS, TIMEZONE
from pm25.ingest import HOUR, TIME, OpenMeteoSource, backfill_open_meteo, fetch_open_meteo, upsert

NWP_VARIABLES = {
    "temperature_2m": "temp_c",
    "relative_humidity_2m": "rh_pct",
    "precipitation": "precip_mm",
    "wind_speed_10m": "wind_kmh",
    "wind_direction_10m": "wind_deg",
    "pressure_msl": "pressure_hpa",
    "cloud_cover": "cloud_pct",
}
NWP = OpenMeteoSource(
    filename="openmeteo_nwp.csv",
    url="https://previous-runs-api.open-meteo.com/v1/forecast",
    variables={
        f"{api}_previous_day{day}": f"nwp{day}_{name}"
        for day in NWP_HORIZONS
        for api, name in NWP_VARIABLES.items()
    },
    extra={"models": "jma_seamless"},
)
REFRESH_DAYS = 4  # Recent hours are fetched again, because they were stored before every run existed
AHEAD = pd.Timedelta(days=2)  # Far enough to cover tomorrow in Bangkok


def backfill_nwp(
    data_dir: Path,
    latitude: float,
    longitude: float,
    start: pd.Timestamp,
    now: pd.Timestamp,
    http_get: Callable[..., Any] = requests.get,
    sleep: Callable[[float], None] = time_module.sleep,
) -> int:
    """Fill missing history, then refresh the last few days and the next two.

    Unlike reanalysis data, hours after `now` are kept: they are forecasts that
    were issued in the past, which is exactly what the feature needs.
    """
    end = now.floor("h") + AHEAD
    added = backfill_open_meteo(NWP, data_dir, latitude, longitude, start, end, http_get, sleep)
    first = (now - pd.Timedelta(days=REFRESH_DAYS)).date()
    frame = fetch_open_meteo(NWP, latitude, longitude, first, end.date(), http_get, sleep)
    added += upsert(data_dir / NWP.filename, frame[frame[TIME] <= end])
    return added


def daily_nwp(hourly: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Return Bangkok daily NWP values per run age: columns nwp1_* and nwp2_*.

    Rows run up to the day after `as_of`, the furthest day a forecast targets.
    A day needs MIN_HOURS_PER_DAY hours for a run age, like the other daily data.
    """
    columns = list(NWP_DAILY_COLUMNS)
    if hourly.empty:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], name="date"))
    frame = hourly.assign(date=hourly[TIME].dt.tz_convert(TIMEZONE).dt.tz_localize(None).dt.normalize())
    frame = frame[frame["date"] <= as_of + pd.Timedelta(days=1)]
    daily: dict[str, pd.Series] = {}
    for day in NWP_HORIZONS:
        p = f"nwp{day}_"
        part = frame.dropna(subset=[f"{p}temp_c", f"{p}wind_kmh"])
        radians = np.deg2rad(part[f"{p}wind_deg"])
        part = part.assign(
            **{
                f"{p}wind_u": -part[f"{p}wind_kmh"] * np.sin(radians),
                f"{p}wind_v": -part[f"{p}wind_kmh"] * np.cos(radians),
            }
        )
        grouped = part.groupby("date")
        enough = grouped.size() >= MIN_HOURS_PER_DAY
        sums = {f"{p}precip_mm"}
        for name in NWP_FEATURES:
            column = f"{p}{name}"
            values = grouped[column].sum() if column in sums else grouped[column].mean()
            daily[column] = values.where(enough)
    result = pd.DataFrame(daily).reindex(columns=columns)
    result.index.name = "date"
    return result
