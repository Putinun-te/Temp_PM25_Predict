from pm25.report import build_report


def forecast(status="ok", value=13.9):
    daily = {
        "label": "today",
        "date": "2026-11-11",
        "pm25": value,
        "pm25_low": None if value is None else 8.5,
        "pm25_high": None if value is None else 19.3,
        "pm25_method": "persistence",
        "pm10": 24.8,
        "pm10_low": 17.3,
        "pm10_high": 32.2,
        "pm10_method": "random_forest",
    }
    monthly = {
        "month": "2026-12",
        "pm25": 30.0,
        "pm25_low": 25.0,
        "pm25_high": 35.0,
        "pm25_method": "climatology",
        "pm10": 49.2,
        "pm10_low": 41.8,
        "pm10_high": 56.7,
        "pm10_method": "climatology",
    }
    return {
        "as_of": "2026-11-11",
        "generated_at": "2026-11-11T07:17:00+07:00",
        "latest_data_date": "2026-11-10",
        "data_age_days": 0 if status == "ok" else 3,
        "status": status,
        "daily": [daily],
        "monthly": [monthly],
    }


METRICS = {
    "daily": {
        "pm25_h2": {
            "published_method": "random_forest",
            "best_candidate": "random_forest",
            "overall": {"random_forest": {"mae": 4.69}, "persistence": {"mae": 5.28}},
            "skill_vs_persistence": 0.112,
            "decision": "promoted: beats every baseline",
        }
    }
}


def test_report_contains_the_forecast_values():
    text = build_report(forecast(), METRICS)
    assert "# Bangkok PM2.5 and PM10 forecast, 2026-11-11" in text
    assert "| Today | 2026-11-11 | 13.9 | 8.5 to 19.3 | persistence | 24.8 |" in text
    assert "| 2026-12 | 30.0 | 25.0 to 35.0 | 49.2 |" in text


def test_report_shows_the_evaluation_honestly():
    text = build_report(forecast(), METRICS)
    assert "| PM2.5 tomorrow | random forest | 4.69 | 5.28 | 11% |" in text


def test_report_warns_about_stale_data_and_missing_values():
    text = build_report(forecast(status="stale", value=None), METRICS)
    assert "Warning: the newest station data is 3 days old" in text
    assert "| n/a | n/a |" in text
