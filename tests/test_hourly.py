import numpy as np
import pandas as pd

from pm25.hourly import LEADS, build_hourly, forecast_hourly, hourly_city, train_hourly


def city_series(days=430, seed=0):
    index = pd.date_range("2025-01-01", periods=24 * days, freq="h")
    rng = np.random.default_rng(seed)
    level = 20 + 8 * np.sin(2 * np.pi * index.day_of_year / 365)
    diurnal = 5 * np.sin(2 * np.pi * (index.hour - 6) / 24)
    return pd.Series(level + diurnal + rng.normal(0, 1, len(index)), index=index, name="pm25")


def test_hourly_city_needs_five_stations_and_uses_local_time():
    times = pd.to_datetime(["2026-11-14T17:00:00Z"] * 5 + ["2026-11-14T18:00:00Z"] * 4)
    openaq = pd.DataFrame(
        {"time": times, "sensor_id": range(9), "parameter": "pm25", "value": [10, 20, 30, 40, 50, 1, 2, 3, 4]}
    )
    city = hourly_city(openaq)
    assert list(city.index) == [pd.Timestamp("2026-11-15 00:00")]  # 17:00 UTC is midnight in Bangkok
    assert city.iloc[0] == 30.0


def test_features_ignore_everything_after_three_in_the_morning():
    city = city_series(40)
    day = pd.DatetimeIndex([pd.Timestamp("2025-02-01")])
    features, labels, baselines = build_hourly(city, pd.DataFrame(), day)

    changed = city.copy()
    changed[changed.index > pd.Timestamp("2025-02-01 03:00")] = 999.0
    features_changed, labels_changed, _ = build_hourly(changed, pd.DataFrame(), day)

    assert len(features) == len(LEADS) == 44
    pd.testing.assert_frame_equal(features, features_changed)
    assert (labels_changed == 999.0).all() and not (labels == 999.0).any()
    # 05:00 today falls back to 05:00 yesterday; 02:00 tomorrow uses 02:00 today.
    assert baselines["same_hour"].iloc[1] == city[pd.Timestamp("2025-01-31 05:00")]
    assert baselines["same_hour"].iloc[LEADS.index(26)] == city[pd.Timestamp("2025-02-01 02:00")]


def test_training_promotes_a_model_that_beats_the_baselines_and_forecasts(tmp_path):
    city = city_series()
    as_of = pd.Timestamp("2026-03-06")
    entry, report = train_hourly(city, pd.DataFrame(), as_of, tmp_path, "now")

    assert entry["method"] == "gradient_boosting"
    assert report["overall"]["gradient_boosting"]["mae"] < report["overall"]["same_hour"]["mae"]
    assert set(entry["residual_q80"]) == {"today", "tomorrow"}

    document = forecast_hourly(city, pd.DataFrame(), entry, tmp_path, as_of, "now")
    assert document["inputs_through"] == "2026-03-06T03:00"
    assert document["hours"][0]["time"] == "2026-03-06T04:00" and document["hours"][0]["day"] == "today"
    assert document["hours"][-1]["time"] == "2026-03-07T23:00" and document["hours"][-1]["day"] == "tomorrow"
    assert all(hour["low"] <= hour["pm25"] <= hour["high"] for hour in document["hours"])
    assert len(document["measured"]) == 28
