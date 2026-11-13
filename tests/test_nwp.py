import numpy as np
import pandas as pd
import pytest

from pm25.features import NWP_FEATURES, build_features, daily_exogenous
from pm25.nwp import NWP, backfill_nwp, daily_nwp


def hourly_nwp(first_local_day, days, day1_temp=30.0, day2_temp=28.0):
    start = pd.Timestamp(first_local_day, tz="Asia/Bangkok").tz_convert("UTC")
    times = pd.date_range(start, periods=24 * days, freq="h")
    frame = pd.DataFrame({"time": times})
    for day, temp in ((1, day1_temp), (2, day2_temp)):
        frame[f"nwp{day}_temp_c"] = temp
        frame[f"nwp{day}_rh_pct"] = 60.0
        frame[f"nwp{day}_precip_mm"] = 0.5
        frame[f"nwp{day}_wind_kmh"] = 10.0
        frame[f"nwp{day}_wind_deg"] = 90.0  # From the east
        frame[f"nwp{day}_pressure_hpa"] = 1010.0
        frame[f"nwp{day}_cloud_pct"] = 40.0
    return frame


def test_source_asks_jma_for_both_run_ages():
    assert NWP.extra == {"models": "jma_seamless"}
    assert NWP.variables["wind_speed_10m_previous_day2"] == "nwp2_wind_kmh"


def test_daily_nwp_aggregates_bangkok_days_and_stops_after_tomorrow():
    daily = daily_nwp(hourly_nwp("2026-11-10", 5), pd.Timestamp("2026-11-12"))
    assert list(daily.index.strftime("%Y-%m-%d")) == ["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]
    row = daily.loc["2026-11-13"]
    assert row["nwp1_temp_c"] == 30.0 and row["nwp2_temp_c"] == 28.0
    assert row["nwp1_precip_mm"] == pytest.approx(12.0)  # Summed over 24 hours
    assert row["nwp1_wind_u"] == pytest.approx(-10.0)  # An east wind blows towards the west
    assert row["nwp1_wind_v"] == pytest.approx(0.0, abs=1e-9)


def test_short_days_are_missing():
    hourly = hourly_nwp("2026-11-10", 1).iloc[:10]
    assert daily_nwp(hourly, pd.Timestamp("2026-11-12")).empty or daily_nwp(hourly, pd.Timestamp("2026-11-12")).isna().all().all()


def test_features_use_the_run_age_matching_the_horizon_for_the_target_day():
    index = pd.date_range("2026-11-01", "2026-11-11", freq="D", name="date")
    targets = pd.DataFrame({"pm25": 20.0, "pm10": 40.0}, index=index)
    nwp = daily_nwp(hourly_nwp("2026-11-01", 13), pd.Timestamp("2026-11-12"))
    nwp.loc["2026-11-13", "nwp2_temp_c"] = 99.0  # Only the tomorrow forecast for 13 November
    exogenous = daily_exogenous(
        pd.DataFrame(columns=["time", "om_pm25", "om_no2", "om_o3", "om_so2", "om_co"]).astype({"time": "datetime64[ns, UTC]"}),
        pd.DataFrame(columns=["time", "om_temp_c", "om_rh_pct", "om_precip_mm", "om_wind_kmh", "om_wind_deg"]).astype({"time": "datetime64[ns, UTC]"}),
        pd.Timestamp("2026-11-12"),
        nwp=nwp,
    )

    today = build_features(targets, exogenous, horizon=1)
    tomorrow = build_features(targets, exogenous, horizon=2)

    origin = pd.Timestamp("2026-11-11")
    assert today.loc[origin, "nwp_temp_c"] == 30.0  # Day 1 run for 12 November
    assert tomorrow.loc[origin, "nwp_temp_c"] == 99.0  # Day 2 run for 13 November
    assert all(f"nwp_{name}" in today.columns for name in NWP_FEATURES)
    assert not np.isnan(tomorrow.loc[origin, "nwp_wind_u"])


def test_backfill_keeps_future_hours_and_refreshes_recent_days(tmp_path, fake_response):
    requests_made = []

    def http_get(url, params, timeout):
        requests_made.append((params["start_date"], params["end_date"], params["models"]))
        times = pd.date_range(params["start_date"], pd.Timestamp(params["end_date"]) + pd.Timedelta(hours=23), freq="h")
        hourly = {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in times]}
        for api in NWP.variables:
            hourly[api] = [1.0] * len(times)
        return fake_response({"hourly": hourly})

    now = pd.Timestamp("2026-11-13 00:17", tz="UTC")
    backfill_nwp(tmp_path, 13.7, 100.5, pd.Timestamp("2026-11-01", tz="UTC"), now, http_get, lambda _: None)

    stored = pd.read_csv(tmp_path / NWP.filename, parse_dates=["time"])
    assert stored["time"].max() == pd.Timestamp("2026-11-15 00:00", tz="UTC")  # Two days ahead of now
    assert requests_made[-1] == ("2026-11-09", "2026-11-15", "jma_seamless")
