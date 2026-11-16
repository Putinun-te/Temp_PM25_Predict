import numpy as np
import pandas as pd

from pm25.features import EXOGENOUS_COLUMNS
from pm25.ingest import OpenAQSensor
from pm25.station_model import build_station_rows, forecast_stations, station_daily, train_stations

SENSORS = (OpenAQSensor(1, "pm25", 101), OpenAQSensor(2, "pm25", 102), OpenAQSensor(3, "pm10", 101))


def test_station_daily_keeps_complete_days_per_location():
    start = pd.Timestamp("2026-11-12", tz="Asia/Bangkok").tz_convert("UTC")
    hours = pd.date_range(start, periods=24, freq="h")
    openaq = pd.concat(
        [
            pd.DataFrame({"time": hours, "sensor_id": 1, "parameter": "pm25", "value": 20.0}),
            pd.DataFrame({"time": hours[:10], "sensor_id": 2, "parameter": "pm25", "value": 99.0}),
            pd.DataFrame({"time": hours, "sensor_id": 3, "parameter": "pm10", "value": 50.0}),
        ]
    )
    daily = station_daily(openaq, pd.Timestamp("2026-11-13"), SENSORS)
    assert list(daily.columns) == [101, 102]
    assert daily.loc["2026-11-12", 101] == 20.0 and np.isnan(daily.loc["2026-11-12", 102])


def synthetic(days=460):
    index = pd.date_range("2025-01-01", periods=days, freq="D", name="date")
    rng = np.random.default_rng(1)
    city = 25 + 10 * np.sin(2 * np.pi * index.day_of_year / 365) + rng.normal(0, 2, days).cumsum() * 0.05
    targets = pd.DataFrame({"pm25": city, "pm10": city * 1.8}, index=index)
    stations = pd.DataFrame({101: city + 6 + rng.normal(0, 1, days), 102: city - 4 + rng.normal(0, 1, days)}, index=index)
    exogenous = pd.DataFrame({name: rng.uniform(0, 10, days) for name in EXOGENOUS_COLUMNS}, index=index)
    return stations, targets, exogenous


def test_rows_are_stacked_per_station_with_its_own_lags():
    stations, targets, exogenous = synthetic(60)
    features, labels, ids, persistence = build_station_rows(stations, targets, exogenous, horizon=1)
    assert len(features) == 120 and list(ids.unique()) == [101, 102]
    origin = pd.Timestamp("2025-02-10")
    first = features[ids == 101].loc[origin]
    assert first["station_lag0"] == stations.loc[origin, 101]
    assert first["station_minus_city"] == stations.loc[origin, 101] - targets.loc[origin, "pm25"]
    assert labels[ids == 101].loc[origin] == stations.loc[origin + pd.Timedelta(days=1), 101]
    assert persistence[ids == 102].loc[origin] == stations.loc[origin, 102]


def test_station_model_beats_using_the_city_forecast_for_every_station(tmp_path):
    stations, targets, exogenous = synthetic()
    city_forecast = targets["pm25"]  # A perfect persistence-like city forecast still misses station offsets
    entry, report = train_stations(stations, targets, exogenous, 1, city_forecast, tmp_path, "now")
    assert report["overall"]["gradient_boosting"]["mae"] < report["overall"]["city_forecast"]["mae"]
    assert set(report["mae_by_station"]) == {"101", "102"}

    as_of = targets.index.max() + pd.Timedelta(days=1)
    rows = forecast_stations(stations, targets, exogenous, {"pm25_h1": entry}, tmp_path, as_of, {1: 25.0})
    assert [row["location_id"] for row in rows] == [101, 102]
    assert rows[0]["today"]["pm25"] > rows[1]["today"]["pm25"]  # Station 101 runs higher than 102
    assert rows[0]["today"]["low"] <= rows[0]["today"]["pm25"] <= rows[0]["today"]["high"]
    assert "tomorrow" not in rows[0]
