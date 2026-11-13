import pandas as pd
import pytest

from pm25.monitor import score_history, summarize


def history_row(as_of, period, label, target, value, low=None, high=None, method="random_forest"):
    return {
        "as_of": as_of,
        "generated_at": f"{as_of}T07:17:00+07:00",
        "kind": "daily",
        "period": period,
        "label": label,
        "target": target,
        "unit": "ug/m3",
        "value": value,
        "low": low,
        "high": high,
        "method": method,
    }


def daily(values):
    frame = pd.DataFrame({"date": list(values)})
    frame["pm25"] = list(values.values())
    for column in ("pm10", "temp_c", "rh_pct"):
        frame[column] = None
    frame.loc[:, "temp_c"] = 30.0
    return frame


def test_scores_only_dates_with_a_measurement_and_uses_issue_day_persistence():
    history = pd.DataFrame(
        [
            history_row("2026-11-11", "2026-11-12", "tomorrow", "pm25", 20.0, 15.0, 25.0),
            history_row("2026-11-11", "2026-11-11", "today", "pm25", 12.0),
            # Not measured yet, so it must not be scored.
            history_row("2026-11-13", "2026-11-14", "tomorrow", "pm25", 18.0),
            {**history_row("2026-11-11", "2026-12", "1", "pm25", 30.0), "kind": "monthly"},
        ]
    )
    measured = daily({"2026-11-10": 14.0, "2026-11-11": 11.0, "2026-11-12": 16.0})

    scored = score_history(history, measured)

    assert list(scored["period"]) == ["2026-11-11", "2026-11-12"]
    tomorrow = scored[scored["label"] == "tomorrow"].iloc[0]
    # Issued on 11 November, when 10 November was the newest measured day.
    assert tomorrow["persistence"] == 14.0
    assert tomorrow["abs_error"] == pytest.approx(4.0)
    assert tomorrow["persistence_abs_error"] == pytest.approx(2.0)
    assert bool(tomorrow["in_range"]) is True
    assert pd.isna(scored[scored["label"] == "today"].iloc[0]["in_range"])


def test_tmd_forecasts_are_scored_against_the_same_target():
    history = pd.DataFrame(
        [history_row("2026-11-11", "2026-11-12", "tomorrow", "tmd_temp_c", 28.0, method="tmd_forecast")]
    )
    scored = score_history(history, daily({"2026-11-10": 1.0, "2026-11-12": 1.0}))
    assert scored.iloc[0]["target"] == "temp_c"
    assert scored.iloc[0]["source"] == "tmd"
    assert scored.iloc[0]["abs_error"] == pytest.approx(2.0)


def test_summary_flags_a_model_worse_than_persistence():
    days = pd.date_range("2026-10-01", periods=20, freq="D")
    scored = pd.DataFrame(
        {
            "as_of": [(d - pd.Timedelta(days=1)).date().isoformat() for d in days],
            "period": [d.date().isoformat() for d in days],
            "label": "tomorrow",
            "target": "pm25",
            "source": "forecast",
            "method": "random_forest",
            "forecast": 20.0,
            "low": 15.0,
            "high": 25.0,
            "actual": 10.0,
            "persistence": 11.0,
            "abs_error": 10.0,
            "persistence_abs_error": 1.0,
            "in_range": False,
        }
    )
    summary = summarize(scored, "2026-11-13T07:30:00+07:00")

    assert summary["latest_scored"] == "2026-10-20"
    week = next(r for r in summary["rows"] if r["window_days"] == 7)
    assert week["n"] == 7
    assert week["mae"] == 10.0
    assert week["skill_vs_persistence"] == -9.0
    assert week["coverage"] == 0.0
    assert len(summary["alerts"]) == 1
    assert "pm25 tomorrow" in summary["alerts"][0]


def test_summary_of_nothing_scored_is_empty():
    summary = summarize(score_history(pd.DataFrame(columns=["kind", "target"]), daily({})), "now")
    assert summary["rows"] == [] and summary["alerts"] == [] and summary["latest_scored"] is None
