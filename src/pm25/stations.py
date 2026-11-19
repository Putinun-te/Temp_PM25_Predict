"""Per-station daily values for the dashboard map."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from pm25.features import MIN_HOURS_PER_DAY, TIMEZONE
from pm25.ingest import OPENAQ_SENSORS, PARAMETER, SENSOR, TIME, VALUE, OpenAQSensor

STATIONS_FILENAME = "stations.json"
STATION_DAYS = 14

# Names and coordinates from the OpenAQ v3 /locations endpoint, fetched once.
# They are fixed for the panel, so the daily run does not spend API calls on them.
LOCATIONS = {
    701: ("Sukhothai Thammathirat Open University", "Nonthaburi", 13.907861, 100.535641),
    2375: ("Bodindecha Sing Singhaseni School", "Bangkok", 13.769634, 100.614567),
    906: ("Residence for Dept. of Mineral Resources", "Samut Prakan", 13.652141, 100.531805),
    2167: ("Highway District", "Samut Sakhon", 13.7054879, 100.315622),
    5545: ("Chulalongkorn Hospital", "Bangkok", 13.729852, 100.536501),
    225612: ("Bansomdejchaopraya Rajabhat University", "Bangkok", 13.732846, 100.487662),
    225629: ("Department of Disease Control", "Nonthaburi", 13.852778, 100.529444),
    225637: ("South Bangkok Power Plant", "Samut Prakan", 13.618, 100.5562),
    225650: ("The Government Public Relations Department", "Bangkok", 13.783185, 100.540489),
    225653: ("Chokchai Police Station", "Bangkok", 13.7954248, 100.5930298),
    225568: ("Bang Khen District Office", "Bangkok", 13.873603, 100.595839),
    225677: ("Lak Si District Office", "Bangkok", 13.887395, 100.579247),
    225671: ("Khlong Sam Wa District Office", "Bangkok", 13.859911, 100.704002),
    225651: ("Saphan Sung District Office", "Bangkok", 13.768892, 100.685743),
    225604: ("Seacon Square", "Bangkok", 13.695561, 100.647615),
    225678: ("Bang Khae District Office", "Bangkok", 13.696314, 100.409049),
    225621: ("Thon Buri Market Sanam Luang 2", "Bangkok", 13.746257, 100.355099),
    225595: ("Bang Bon 5 Market", "Bangkok", 13.639165, 100.372958),
    225622: ("Huai Khwang District Office", "Bangkok", 13.77682, 100.579543),
    225679: ("Dusit District Office", "Bangkok", 13.776664, 100.520982),
}


def _value(value: float) -> float | None:
    return None if pd.isna(value) else round(float(value), 1)


def station_days(
    openaq: pd.DataFrame,
    as_of: pd.Timestamp,
    generated_at: str,
    sensors: Sequence[OpenAQSensor] = OPENAQ_SENSORS,
    days: int = STATION_DAYS,
) -> dict[str, Any]:
    """Return each station's daily means for the last complete `days` days.

    A station-day needs the same minimum hours as the city median, so the map
    never shows a value the forecast would not have trusted.
    """
    first = as_of - pd.Timedelta(days=days)
    frame = openaq.assign(
        date=openaq[TIME].dt.tz_convert(TIMEZONE).dt.tz_localize(None).dt.normalize()
    )
    frame = frame[(frame["date"] >= first) & (frame["date"] < as_of)]
    daily = frame.groupby([SENSOR, PARAMETER, "date"])[VALUE].agg(["mean", "count"])
    daily = daily[daily["count"] >= MIN_HOURS_PER_DAY]["mean"]

    dates = [d.date().isoformat() for d in pd.date_range(first, as_of - pd.Timedelta(days=1))]
    stations: dict[int, dict[str, Any]] = {}
    for sensor in sensors:
        name, locality, latitude, longitude = LOCATIONS[sensor.location_id]
        station = stations.setdefault(
            sensor.location_id,
            {
                "location_id": sensor.location_id,
                "name": name,
                "locality": locality,
                "latitude": latitude,
                "longitude": longitude,
            },
        )
        station[sensor.parameter] = [
            _value(daily.get((sensor.sensor_id, sensor.parameter, pd.Timestamp(day)), float("nan")))
            for day in dates
        ]
    return {"generated_at": generated_at, "dates": dates, "stations": list(stations.values())}
