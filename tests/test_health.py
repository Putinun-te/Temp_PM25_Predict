from datetime import date, datetime

from pm25.health import check_health, render

TODAY = date(2026, 11, 13)
DAYS = ("today", "tomorrow", "day2", "day3", "day4", "day5", "day6")
FORECAST = {
    "as_of": "2026-11-13",
    "latest_data_date": "2026-11-12",
    "station_forecasts": [{"location_id": 1, **{day: {"pm25": 20.0} for day in DAYS}}],
}
QUALITY = {"passed": True, "checks": []}
HOURLY = {"as_of": "2026-11-13", "inputs_through": "2026-11-13T03:00", "hours": [{"time": "2026-11-13T10:00", "pm25": 18.0, "pm10": 30.0}]}


def test_fresh_outputs_are_healthy():
    assert check_health(FORECAST, QUALITY, {"alerts": []}, TODAY, HOURLY) == []
    assert render([], TODAY) == "Pipeline healthy on 2026-11-13."


def test_missing_daily_run_is_reported():
    problems = check_health({**FORECAST, "as_of": "2026-11-12"}, QUALITY, None, TODAY, HOURLY)
    assert len(problems) == 1 and "No forecast was published today" in problems[0]


def test_data_older_than_two_days_is_reported():
    assert check_health({**FORECAST, "latest_data_date": "2026-11-10"}, QUALITY, None, TODAY, HOURLY) == []
    problems = check_health({**FORECAST, "latest_data_date": "2026-11-09"}, QUALITY, None, TODAY, HOURLY)
    assert problems == [
        "Station data is 3 days old (newest complete day 2026-11-09). OpenAQ or Air4Thai may be delayed."
    ]


def test_failed_quality_gate_and_accuracy_alerts_are_reported():
    quality = {
        "passed": False,
        "checks": [
            {"name": "OpenAQ has no duplicate rows", "passed": False, "severity": "error"},
            {"name": "a warning", "passed": False, "severity": "warning"},
        ],
    }
    problems = check_health(None, quality, {"alerts": ["pm25 tomorrow: worse"]}, TODAY)
    assert problems[0].startswith("No forecast has been published")
    assert problems[1] == "Data quality checks failed: OpenAQ has no duplicate rows."
    assert problems[2] == "Live accuracy: pm25 tomorrow: worse."
    assert render(problems, TODAY).startswith("Pipeline health check found 3 problem(s)")


def test_missing_station_days_are_reported():
    assert check_health({**FORECAST, "station_forecasts": []}, QUALITY, None, TODAY, HOURLY) == [
        "The forecast has no station forecasts, so the map has nothing to show."
    ]
    short = [{"location_id": 1, "today": {"pm25": 20.0}, "tomorrow": {"pm25": 21.0}}]
    problems = check_health({**FORECAST, "station_forecasts": short}, QUALITY, None, TODAY, HOURLY)
    assert problems == ["No station has a forecast for day2, day3, day4, day5, day6."]


def test_missing_or_stale_hourly_forecast_is_reported():
    assert check_health(FORECAST, QUALITY, None, TODAY, None) == [
        "No hourly forecast has been published today (gold/hourly_forecast.json is missing)."
    ]
    assert check_health(FORECAST, QUALITY, None, TODAY, {**HOURLY, "as_of": "2026-11-12"}) == [
        "The hourly forecast is for 2026-11-12, not today."
    ]
    assert check_health(FORECAST, QUALITY, None, TODAY, {**HOURLY, "hours": []}) == ["The hourly forecast has no hours."]
    no_pm10 = {**HOURLY, "hours": [{"time": "2026-11-13T10:00", "pm25": 18.0}]}
    assert check_health(FORECAST, QUALITY, None, TODAY, no_pm10) == ["The hourly forecast has no PM10 values."]


def test_azure_sql_load_must_hold_today_runs():
    fresh = {
        "loaded_at": "2026-11-13T07:50:00+07:00",
        "newest_as_of": {"gold.forecast_history": "2026-11-13", "gold.hourly_forecast_history": "2026-11-13"},
    }
    assert check_health(FORECAST, QUALITY, None, TODAY, HOURLY, fresh) == []
    old = {**fresh, "loaded_at": "2026-11-12T07:50:00+07:00"}
    assert check_health(FORECAST, QUALITY, None, TODAY, HOURLY, old) == [
        "Azure SQL was last loaded on 2026-11-12, so Power BI shows old data. Check the load step of the daily run."
    ]
    missing = {**fresh, "newest_as_of": {"gold.forecast_history": "2026-11-13", "gold.hourly_forecast_history": None}}
    assert check_health(FORECAST, QUALITY, None, TODAY, HOURLY, missing) == [
        "Azure SQL does not have today's run in gold.hourly_forecast_history (empty)."
    ]


def test_each_hourly_run_must_publish_by_its_deadline():
    morning = check_health(FORECAST, QUALITY, None, TODAY, HOURLY, now=datetime(2026, 11, 13, 10, 37))
    assert morning == []
    afternoon = check_health(FORECAST, QUALITY, None, TODAY, HOURLY, now=datetime(2026, 11, 13, 14, 37))
    assert afternoon == [
        "The hourly forecast uses measurements through 2026-11-13T03:00, but the afternoon run "
        "should have used them through 09:00. Check the hourly update run."
    ]
    evening = {**HOURLY, "inputs_through": "2026-11-13T16:00"}
    assert check_health(FORECAST, QUALITY, None, TODAY, evening, now=datetime(2026, 11, 13, 20, 37)) == []
    late = {**HOURLY, "inputs_through": "2026-11-13T09:00"}
    assert "evening run" in check_health(FORECAST, QUALITY, None, TODAY, late, now=datetime(2026, 11, 13, 20, 37))[0]
