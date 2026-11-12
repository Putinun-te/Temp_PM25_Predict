import numpy as np
import pandas as pd

from pm25.ingest import PARAMETER, SENSOR, TIME, VALUE
from pm25.layers import migrate_to_medallion, run_checks

NOW = pd.Timestamp("2026-11-12 00:00", tz="UTC")


def frames(hours=48, pm_value=20.0):
    times = pd.date_range(NOW - pd.Timedelta(hours=hours), NOW, freq="h")
    openaq = pd.DataFrame({TIME: times, SENSOR: 1, PARAMETER: "pm25", VALUE: pm_value})
    air = pd.DataFrame({TIME: times, "om_pm25": 10.0})
    weather = pd.DataFrame({TIME: times, "om_temp_c": 28.0, "om_rh_pct": 70.0})
    index = pd.date_range("2025-11-12", "2026-11-11", freq="D")
    daily = pd.DataFrame({"pm25": 20.0, "pm10": 30.0}, index=index)
    return openaq, air, weather, daily


def failed(checks):
    return {check.name for check in checks if not check.passed}


def test_clean_data_passes_every_check():
    assert failed(run_checks(*frames(), NOW)) == set()


def test_duplicate_station_rows_fail():
    openaq, air, weather, daily = frames()
    openaq = pd.concat([openaq, openaq.iloc[:3]])
    assert "OpenAQ has no duplicate rows" in failed(run_checks(openaq, air, weather, daily, NOW))


def test_impossible_humidity_fails():
    openaq, air, weather, daily = frames()
    weather.loc[0, "om_rh_pct"] = 140.0
    assert "Humidity within 0 to 100" in failed(run_checks(openaq, air, weather, daily, NOW))


def test_stale_station_data_fails():
    openaq, air, weather, daily = frames()
    openaq[TIME] = openaq[TIME] - pd.Timedelta(days=5)
    assert "OpenAQ is fresh" in failed(run_checks(openaq, air, weather, daily, NOW))


def test_mixed_units_are_caught_when_pm25_exceeds_pm10():
    openaq, air, weather, daily = frames()
    daily["pm25"] = 90.0
    assert "PM2.5 does not exceed PM10" in failed(run_checks(openaq, air, weather, daily, NOW))


def test_missing_week_is_only_a_warning():
    openaq, air, weather, daily = frames()
    daily.iloc[-7:, daily.columns.get_loc("pm25")] = np.nan
    checks = run_checks(openaq, air, weather, daily, NOW)
    warning = next(c for c in checks if c.name.startswith("Station panel"))
    assert not warning.passed and warning.severity == "warning"


def test_migration_moves_flat_files_into_bronze_and_gold(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "openaq_hourly.csv").write_text("time\n", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "forecast_history.csv").write_text("as_of\n", encoding="utf-8")
    moved = migrate_to_medallion(data)
    assert sorted(moved) == ["forecast_history.csv", "openaq_hourly.csv"]
    assert (data / "bronze" / "openaq_hourly.csv").exists()
    assert (data / "gold" / "forecast_history.csv").exists()
    assert migrate_to_medallion(data) == []
