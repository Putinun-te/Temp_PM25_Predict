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

    assert entry["method"] == "gradient_boosting_change"
    assert report["overall"]["gradient_boosting_change"]["mae"] < report["overall"]["same_hour"]["mae"]
    assert set(entry["residual_q80"]) == {"today", "tomorrow"}

    document = forecast_hourly(city, pd.DataFrame(), entry, tmp_path, as_of, "now")
    assert document["inputs_through"] == "2026-03-06T03:00"
    assert document["hours"][0]["time"] == "2026-03-06T04:00" and document["hours"][0]["day"] == "today"
    assert document["hours"][-1]["time"] == "2026-03-07T23:00" and document["hours"][-1]["day"] == "tomorrow"
    assert all(hour["low"] <= hour["pm25"] <= hour["high"] for hour in document["hours"])
    assert len(document["measured"]) == 28


def test_afternoon_run_sees_hours_up_to_nine_and_forecasts_from_ten(tmp_path):
    from pm25.hourly import AFTERNOON_KNOWN_HOUR, has_recent_hours, leads_for, model_filename

    city = city_series()
    day = pd.DatetimeIndex([pd.Timestamp("2025-02-01")])
    features, labels, baselines = build_hourly(city, pd.DataFrame(), day, AFTERNOON_KNOWN_HOUR)
    changed = city.copy()
    changed[changed.index > pd.Timestamp("2025-02-01 09:00")] = 999.0
    features_changed, _, _ = build_hourly(changed, pd.DataFrame(), day, AFTERNOON_KNOWN_HOUR)

    leads = leads_for(AFTERNOON_KNOWN_HOUR)
    assert len(features) == len(leads) == 38
    pd.testing.assert_frame_equal(features, features_changed)
    assert features["obs_+9"].iloc[0] == city[pd.Timestamp("2025-02-01 09:00")]
    # 08:00 tomorrow uses 08:00 today, which the morning run could not know.
    assert baselines["same_hour"].iloc[leads.index(32)] == city[pd.Timestamp("2025-02-01 08:00")]

    as_of = pd.Timestamp("2026-03-06")
    entry, _ = train_hourly(city, pd.DataFrame(), as_of, tmp_path, "now", AFTERNOON_KNOWN_HOUR)
    assert (tmp_path / model_filename(AFTERNOON_KNOWN_HOUR)).name == "pm25_hourly_h09.joblib"
    document = forecast_hourly(city, pd.DataFrame(), entry, tmp_path, as_of, "now", AFTERNOON_KNOWN_HOUR)
    assert document["inputs_through"] == "2026-03-06T09:00"
    assert document["hours"][0]["time"] == "2026-03-06T10:00"

    assert not has_recent_hours(city[city.index < as_of + pd.Timedelta(hours=7)], as_of, AFTERNOON_KNOWN_HOUR)
    assert has_recent_hours(city[city.index < as_of + pd.Timedelta(hours=8)], as_of, AFTERNOON_KNOWN_HOUR)


def test_pm10_has_its_own_models_and_is_merged_into_each_hour(tmp_path):
    from pm25.hourly import AFTERNOON_KNOWN_HOUR, merge_pm10, model_filename, registry_key

    assert registry_key("pm25", 3) == "hourly" and registry_key("pm25", AFTERNOON_KNOWN_HOUR) == "hourly_afternoon"
    assert registry_key("pm10", 3) == "hourly_pm10" and registry_key("pm10", 9) == "hourly_pm10_afternoon"
    assert registry_key("pm25", 16) == "hourly_evening" and registry_key("pm10", 16) == "hourly_pm10_evening"
    assert model_filename(16, "pm25") == "pm25_hourly_h16.joblib"
    assert model_filename(3, "pm10") == "pm10_hourly_h03.joblib"
    assert model_filename(3) == "pm25_hourly.joblib"  # Existing PM2.5 files keep their names

    # Two PM10 stations are enough for a city value.
    times = pd.to_datetime(["2026-11-14T17:00:00Z"] * 2)
    openaq = pd.DataFrame({"time": times, "sensor_id": [1, 2], "parameter": "pm10", "value": [40.0, 60.0]})
    assert hourly_city(openaq, "pm10").tolist() == [50.0]

    pm25 = city_series()
    pm10 = (pm25 * 1.6).rename("pm10")
    as_of = pd.Timestamp("2026-03-06")
    entry25, _ = train_hourly(pm25, pd.DataFrame(), as_of, tmp_path, "now")
    entry10, _ = train_hourly(pm10, pd.DataFrame(), as_of, tmp_path, "now", target="pm10")
    assert (tmp_path / "pm10_hourly_h03.joblib").exists() and (tmp_path / "pm25_hourly.joblib").exists()

    document = forecast_hourly(pm25, pd.DataFrame(), entry25, tmp_path, as_of, "now")
    extra = forecast_hourly(pm10, pd.DataFrame(), entry10, tmp_path, as_of, "now", target="pm10")
    assert "pm10" in extra["hours"][0] and "pm25" not in extra["hours"][0]
    merged = merge_pm10(document, extra)
    hour = merged["hours"][0]
    assert hour["pm10"] > hour["pm25"] and hour["pm10_low"] <= hour["pm10"] <= hour["pm10_high"]
    assert merged["measured"][0]["pm10"] > merged["measured"][0]["pm25"]
    assert merged["pm10_method"] == entry10["method"]


def test_map_only_stations_stay_out_of_the_city_median():
    from pm25.ingest import MAP_PANEL, OPENAQ_PANEL

    time = pd.Timestamp("2026-11-19T03:00", tz="UTC")
    panel = [s for s in OPENAQ_PANEL if s.parameter == "pm25"][:5]
    rows = [{"time": time, "sensor_id": s.sensor_id, "parameter": "pm25", "value": 20.0} for s in panel]
    rows += [{"time": time, "sensor_id": s.sensor_id, "parameter": "pm25", "value": 90.0} for s in MAP_PANEL[:9]]
    assert hourly_city(pd.DataFrame(rows), "pm25").tolist() == [20.0]


def test_hourly_width_uses_the_fitted_range_per_part():
    from pm25.hourly import hourly_width

    entry = {
        "residual_q80": {"today": 3.0, "tomorrow": 5.0},
        "range": {"today": {"range_method": "level", "residual_q80_by_level": {"edges": [20.0], "q80": [2.0, 6.0]}}},
    }
    assert hourly_width(entry, "today", 10.0) == 2.0
    assert hourly_width(entry, "today", 40.0) == 6.0
    assert hourly_width(entry, "today", None) == 3.0  # No value: the flat fallback
    assert hourly_width(entry, "tomorrow", 40.0) == 5.0  # No fitted range for this part
    assert hourly_width({"residual_q80": {"today": 3.0}}, "today", 40.0) == 3.0  # Older models


def test_a_model_saved_under_the_old_name_is_still_served(tmp_path):
    city = city_series()
    as_of = city.index.max().normalize()
    entry, _ = train_hourly(city, pd.DataFrame(), as_of, tmp_path, "now")
    # Registries written before 25 November 2026 name the hourly model gradient_boosting.
    old = {**entry, "method": "gradient_boosting"}
    document = forecast_hourly(city, pd.DataFrame(), old, tmp_path, as_of, "now")
    assert all(hour["pm25"] is not None for hour in document["hours"])
