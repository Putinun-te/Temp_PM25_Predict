import pandas as pd

from pm25.ingest import OpenAQSensor
from pm25.stations import station_days

SENSORS = (OpenAQSensor(1, "pm25", 5545), OpenAQSensor(2, "pm10", 5545), OpenAQSensor(3, "pm25", 701))


def hours(sensor_id, parameter, day, count, value):
    # Bangkok midnight is 17:00 UTC the day before.
    start = pd.Timestamp(day, tz="Asia/Bangkok").tz_convert("UTC")
    return pd.DataFrame(
        {
            "time": pd.date_range(start, periods=count, freq="h"),
            "sensor_id": sensor_id,
            "parameter": parameter,
            "value": value,
        }
    )


def test_station_days_groups_sensors_by_location_and_skips_thin_days():
    openaq = pd.concat(
        [
            hours(1, "pm25", "2026-11-12", 24, 20.0),
            hours(2, "pm10", "2026-11-12", 24, 40.0),
            hours(3, "pm25", "2026-11-12", 10, 99.0),  # Too few hours to count
            hours(1, "pm25", "2026-11-13", 24, 50.0),  # Today, still incomplete
        ],
        ignore_index=True,
    )

    result = station_days(openaq, pd.Timestamp("2026-11-13"), "now", SENSORS, days=2)

    assert result["dates"] == ["2026-11-11", "2026-11-12"]
    chula, stou = result["stations"]
    assert chula["name"] == "Chulalongkorn Hospital"
    assert chula["pm25"] == [None, 20.0] and chula["pm10"] == [None, 40.0]
    assert stou["pm25"] == [None, None] and "pm10" not in stou
