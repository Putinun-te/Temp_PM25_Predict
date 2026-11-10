import numpy as np
import pandas as pd
import pytest

from pm25.features import (
    EXOGENOUS_COLUMNS,
    TARGETS,
    build_features,
    build_labels,
    daily_baselines,
    daily_targets,
    monthly_forecast,
    monthly_targets,
)
from pm25.ingest import PARAMETER, SENSOR, TIME, VALUE


def station_hours(sensor, parameter, local_start, hours, value):
    times = pd.date_range(local_start, periods=hours, freq="h", tz="Asia/Bangkok").tz_convert("UTC")
    return pd.DataFrame({TIME: times, SENSOR: sensor, PARAMETER: parameter, VALUE: value})


def panel(day, hours=24, stations=5, value=10.0):
    return pd.concat(
        [station_hours(i, "pm25", day, hours, value + i) for i in range(stations)], ignore_index=True
    )


AS_OF = pd.Timestamp("2024-01-03")


def test_city_value_is_the_median_across_stations():
    targets = daily_targets(panel("2024-01-01"), AS_OF)
    assert targets.loc["2024-01-01", "pm25"] == 12.0


def test_days_follow_bangkok_time():
    frame = panel("2024-01-01")
    assert frame[TIME].min() == pd.Timestamp("2023-12-31 17:00", tz="UTC")
    targets = daily_targets(frame, AS_OF)
    assert targets.first_valid_index() == pd.Timestamp("2024-01-01")


def test_station_day_needs_enough_hours():
    assert daily_targets(panel("2024-01-01", hours=17), AS_OF)["pm25"].dropna().empty


def test_city_day_needs_enough_stations():
    assert daily_targets(panel("2024-01-01", stations=4), AS_OF)["pm25"].dropna().empty


def test_incomplete_current_day_is_excluded():
    frame = pd.concat([panel("2024-01-02"), panel("2024-01-03")], ignore_index=True)
    assert daily_targets(frame, AS_OF).index.max() == pd.Timestamp("2024-01-02")


def synthetic_inputs(days=200, seed=1):
    index = pd.date_range("2023-01-01", periods=days, freq="D", name="date")
    rng = np.random.default_rng(seed)
    targets = pd.DataFrame({name: rng.uniform(5, 80, days) for name in TARGETS}, index=index)
    exogenous = pd.DataFrame(
        {name: rng.uniform(0, 50, days) for name in EXOGENOUS_COLUMNS}, index=index
    )
    return targets, exogenous


@pytest.mark.parametrize("horizon", [1, 2])
def test_no_feature_uses_data_after_its_origin(horizon):
    targets, exogenous = synthetic_inputs()
    baseline = build_features(targets, exogenous, horizon)
    cut = 120
    changed_targets, changed_exogenous = targets.copy(), exogenous.copy()
    changed_targets.iloc[cut + 1 :] = 9999.0
    changed_exogenous.iloc[cut + 1 :] = 9999.0
    changed = build_features(changed_targets, changed_exogenous, horizon)
    pd.testing.assert_frame_equal(baseline.iloc[: cut + 1], changed.iloc[: cut + 1])


def test_changing_the_origin_day_does_change_its_features():
    targets, exogenous = synthetic_inputs()
    changed = targets.copy()
    changed.iloc[120, 0] = 9999.0
    row = build_features(changed, exogenous, 1).iloc[120]
    assert row["pm25_lag0"] == 9999.0


def test_lags_are_calendar_days_across_gaps():
    targets, exogenous = synthetic_inputs()
    targets.iloc[50] = np.nan
    features = build_features(targets, exogenous, 1)
    assert np.isnan(features["pm25_lag1"].iloc[51])
    assert np.isnan(features["pm25_lag2"].iloc[52])
    assert features["pm25_lag2"].iloc[51] == targets["pm25"].iloc[49]


def test_calendar_features_describe_the_target_date():
    targets, exogenous = synthetic_inputs()
    features = build_features(targets, exogenous, 2)
    target_date = targets.index[10] + pd.Timedelta(days=2)
    assert features["dow_sin"].iloc[10] == pytest.approx(np.sin(2 * np.pi * target_date.day_of_week / 7))


@pytest.mark.parametrize("horizon", [1, 2])
def test_labels_are_the_value_at_the_horizon(horizon):
    targets, _ = synthetic_inputs()
    assert build_labels(targets, horizon)["pm25"].iloc[10] == targets["pm25"].iloc[10 + horizon]


@pytest.mark.parametrize("horizon", [1, 2])
def test_baselines_only_use_known_days(horizon):
    targets, _ = synthetic_inputs()
    baselines = daily_baselines(targets["pm25"], horizon)
    assert baselines["persistence"].iloc[30] == targets["pm25"].iloc[30]
    assert baselines["seasonal7"].iloc[30] == targets["pm25"].iloc[30 + horizon - 7]


def test_month_needs_enough_valid_days():
    index = pd.date_range("2024-01-01", "2024-02-29", freq="D")
    targets = pd.DataFrame({"pm25": 10.0, "pm10": 20.0}, index=index)
    targets.loc["2024-02-01":"2024-02-15"] = np.nan
    monthly = monthly_targets(targets)
    assert monthly.loc["2024-01-01", "pm25"] == 10.0
    assert np.isnan(monthly.loc["2024-02-01", "pm25"])


def test_climatology_is_the_mean_of_the_same_calendar_month():
    index = pd.date_range("2022-01-01", periods=30, freq="MS")
    history = pd.Series(np.arange(30, dtype=float), index=index)
    result = monthly_forecast(history, pd.Timestamp("2024-08-01"), 2)
    assert result["climatology"] == pytest.approx((7.0 + 19.0) / 2)
