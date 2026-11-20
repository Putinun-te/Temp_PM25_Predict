from datetime import date

import pandas as pd

from pm25.weekly import build_weekly


def test_weekly_summary_covers_the_last_seven_days():
    daily = pd.DataFrame(
        {
            "date": pd.date_range("2026-11-15", periods=10, freq="D").strftime("%Y-%m-%d"),
            "pm25": [10, 20, 40, 50, 30, 20, 10, 15, 99, 99],
            "pm10": [30] * 10,
            "temp_c": [30.0] * 10,
            "rh_pct": [70.0] * 10,
        }
    )
    summary = {
        "rows": [
            {"target": "pm25", "label": "tomorrow", "source": "forecast", "window_days": 7, "n": 7, "mae": 3.0,
             "persistence_mae": 4.0, "skill_vs_persistence": 0.25, "coverage": 0.86,
             "chances": [{"threshold": 37.5, "chance_n": 7, "chance_events": 2, "brier": 0.05, "base_rate_brier": 0.2}]},
        ],
        "stations": [{"label": "today", "window_days": 7, "n": 140, "days": 7, "mae": 4.0, "persistence_mae": 5.0,
                      "coverage": 0.8}],
        "alerts": ["pm25 tomorrow: something"],
    }
    forecast = {"as_of": "2026-11-23", "daily": [{"date": "2026-11-23", "pm25": 30.0, "pm25_low": 25.0,
                                                  "pm25_high": 35.0, "pm25_p_above_standard": 0.004}]}
    text = build_weekly(daily, summary, forecast, date(2026, 11, 23))
    assert text.startswith("Week of 2026-11-16 to 2026-11-22.")
    # 16 to 22 November: 20, 40, 50, 30, 20, 10, 15; the 99s are outside the week.
    assert "| PM2.5 µg/m³ | 26.4 | 50.0 (2026-11-18) | 2 of 7 (standard 37.5) |" in text
    assert "| PM2.5 | tomorrow | 7 | 3.00 | 4.00 | 25% | 86% |" in text
    assert "| Station PM2.5 | today | 140 |" in text
    assert "| City PM2.5 | tomorrow | 37.5 | 7 | 2 | 0.050 | 0.200 |" in text
    assert "- pm25 tomorrow: something" in text
    assert "| 2026-11-23 | 30.0 | 25.0 to 35.0 | <1% |" in text


def test_weekly_summary_with_nothing_scored():
    empty = pd.DataFrame(columns=["date", "pm25", "pm10", "temp_c", "rh_pct"])
    text = build_weekly(empty, None, None, date(2026, 11, 23))
    assert "No measured days in this week." in text and "Nothing scored this week." in text
