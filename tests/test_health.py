from datetime import date

from pm25.health import check_health, render

TODAY = date(2026, 11, 13)
FORECAST = {"as_of": "2026-11-13", "latest_data_date": "2026-11-12"}
QUALITY = {"passed": True, "checks": []}


def test_fresh_outputs_are_healthy():
    assert check_health(FORECAST, QUALITY, {"alerts": []}, TODAY) == []
    assert render([], TODAY) == "Pipeline healthy on 2026-11-13."


def test_missing_daily_run_is_reported():
    problems = check_health({**FORECAST, "as_of": "2026-11-12"}, QUALITY, None, TODAY)
    assert len(problems) == 1 and "No forecast was published today" in problems[0]


def test_data_older_than_two_days_is_reported():
    assert check_health({**FORECAST, "latest_data_date": "2026-11-10"}, QUALITY, None, TODAY) == []
    problems = check_health({**FORECAST, "latest_data_date": "2026-11-09"}, QUALITY, None, TODAY)
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
