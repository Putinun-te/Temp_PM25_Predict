import pandas as pd
import pytest

from pm25.monitor import coverage_alerts, score_history, score_stations, summarize, summarize_extra


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
    assert week["mape_pct"] == 100.0
    assert week["skill_vs_persistence"] == -9.0
    assert week["coverage"] == 0.0
    assert len(summary["alerts"]) == 2
    assert any("worse than persistence" in alert for alert in summary["alerts"])
    # No forecast fell inside its range, so the range alert fires too.
    assert any("pm25 tomorrow: the 80 % range held only 0%" in alert for alert in summary["alerts"])


def test_summary_of_nothing_scored_is_empty():
    summary = summarize(score_history(pd.DataFrame(columns=["kind", "target"]), daily({})), "now")
    assert summary["rows"] == [] and summary["alerts"] == [] and summary["latest_scored"] is None


def test_hourly_scores_use_the_same_hour_known_at_issue_time(tmp_path):
    from pm25.monitor import HOURLY_KEYS, append_rows, hourly_rows, score_hourly, summarize_extra

    document = {
        "as_of": "2026-11-16",
        "method": "gradient_boosting",
        "inputs_through": "2026-11-16T03:00",
        "hours": [
            {"time": "2026-11-16T04:00", "day": "today", "pm25": 20.0, "low": 15.0, "high": 25.0},
            {"time": "2026-11-17T02:00", "day": "tomorrow", "pm25": 30.0, "low": 28.0, "high": 32.0},
            {"time": "2026-11-17T09:00", "day": "tomorrow", "pm25": 30.0, "low": 20.0, "high": 40.0},
        ],
    }
    path = tmp_path / "hourly.csv"
    append_rows(path, hourly_rows(document), HOURLY_KEYS)
    append_rows(path, hourly_rows(document), HOURLY_KEYS)  # A rerun must not duplicate rows
    history = pd.read_csv(path)
    assert len(history) == 3

    city = pd.Series(
        {
            pd.Timestamp("2026-11-15T04:00"): 10.0,  # Same hour yesterday, for 04:00
            pd.Timestamp("2026-11-16T02:00"): 26.0,  # Already known at 03:00, for 02:00 tomorrow
            pd.Timestamp("2026-11-16T04:00"): 22.0,
            pd.Timestamp("2026-11-17T02:00"): 35.0,
        }
    )
    scored = score_hourly(history, city)
    assert list(scored["time"]) == ["2026-11-16T04:00", "2026-11-17T02:00"]  # 09:00 is not measured yet
    assert list(scored["abs_error"]) == [2.0, 5.0]
    assert list(scored["persistence_abs_error"]) == [12.0, 9.0]
    assert list(scored["in_range"]) == [True, False]
    rows = {row["label"]: row for row in summarize_extra(scored) if row["window_days"] == 30}
    assert rows["today"]["mae"] == 2.0 and rows["tomorrow"]["persistence_mae"] == 9.0


def test_station_scores_compare_each_station_with_its_own_persistence():
    from pm25.monitor import score_stations, station_rows

    forecast = {
        "as_of": "2026-11-16",
        "station_forecasts": [
            {
                "location_id": 701,
                "today": {"pm25": 30.0, "low": 25.0, "high": 35.0, "method": "gradient_boosting"},
                "tomorrow": {"pm25": 20.0, "low": 15.0, "high": 25.0, "method": "gradient_boosting"},
            },
            {"location_id": 906, "today": {"pm25": None, "low": None, "high": None, "method": "gradient_boosting"}},
        ],
    }
    history = station_rows(forecast)
    assert len(history) == 3
    stations = pd.DataFrame(
        {701: [24.0, 33.0], 906: [18.0, 19.0]}, index=pd.to_datetime(["2026-11-15", "2026-11-16"])
    )
    scored = score_stations(history, stations)
    assert len(scored) == 1  # Tomorrow is not measured, and 906 has no forecast
    row = scored.iloc[0]
    assert (row["label"], row["abs_error"], row["persistence_abs_error"], row["in_range"]) == ("today", 3.0, 9.0, True)


def test_afternoon_hourly_rows_are_kept_beside_the_morning_ones_and_use_newer_persistence(tmp_path):
    from pm25.monitor import HOURLY_KEYS, append_rows, hourly_rows, read_history, score_hourly

    def document(inputs_through, value):
        return {
            "as_of": "2026-11-16",
            "method": "gradient_boosting",
            "inputs_through": inputs_through,
            "hours": [{"time": "2026-11-17T08:00", "day": "tomorrow", "pm25": value, "low": 0.0, "high": 99.0}],
        }

    path = tmp_path / "hourly.csv"
    # A file written before the known_hour column existed holds morning rows only.
    hourly_rows(document("2026-11-16T03:00", 20.0)).drop(columns="known_hour").to_csv(path, index=False)
    append_rows(path, hourly_rows(document("2026-11-16T09:00", 24.0)), HOURLY_KEYS)
    history = read_history(path, HOURLY_KEYS)
    assert sorted(history["known_hour"]) == ["3", "9"]

    city = pd.Series(
        {
            pd.Timestamp("2026-11-15T08:00"): 10.0,  # What the morning run knew for 08:00
            pd.Timestamp("2026-11-16T08:00"): 18.0,  # Known to the afternoon run
            pd.Timestamp("2026-11-17T08:00"): 25.0,
        }
    )
    scored = score_hourly(history, city).set_index("known_hour")
    assert scored.loc["3", "persistence_abs_error"] == 15.0
    assert scored.loc["9", "persistence_abs_error"] == 7.0


def test_station_rows_include_pm10_when_it_is_forecast():
    from pm25.monitor import station_rows

    forecast = {
        "as_of": "2026-11-16",
        "station_forecasts": [
            {
                "location_id": 225629,
                "today": {
                    "pm25": 30.0, "low": 25.0, "high": 35.0, "method": "gradient_boosting",
                    "pm10": {"pm10": 50.0, "low": 40.0, "high": 60.0, "method": "persistence"},
                },
            }
        ],
    }
    rows = station_rows(forecast).set_index("target")
    assert list(rows.index) == ["pm25", "pm10"]
    assert rows.loc["pm10", "forecast"] == 50.0 and rows.loc["pm10", "method"] == "persistence"


def test_later_station_days_and_hourly_pm10_become_history_rows():
    from pm25.monitor import hourly_rows, station_rows

    forecast = {
        "as_of": "2026-11-16",
        "station_forecasts": [
            {"location_id": 701, "day3": {"pm25": 30.0, "low": 25.0, "high": 35.0, "method": "gradient_boosting"}}
        ],
    }
    row = station_rows(forecast).iloc[0]
    assert (row["label"], row["period"]) == ("day3", "2026-11-19")  # Three days after the issue date

    hourly = {
        "as_of": "2026-11-16",
        "method": "gradient_boosting",
        "pm10_method": "same_hour",
        "inputs_through": "2026-11-16T03:00",
        "hours": [
            {"time": "2026-11-16T04:00", "day": "today", "pm25": 20.0, "low": 15.0, "high": 25.0,
             "pm10": 40.0, "pm10_low": 30.0, "pm10_high": 50.0}
        ],
    }
    rows = hourly_rows(hourly).set_index("target")
    assert list(rows.index) == ["pm25", "pm10"]
    assert rows.loc["pm10", "forecast"] == 40.0 and rows.loc["pm10", "method"] == "same_hour"


def test_hourly_chances_are_kept_and_scored_live():
    from pm25.monitor import hourly_rows, score_hourly, summarize_extra

    hourly = {
        "as_of": "2026-11-16",
        "method": "gradient_boosting_change",
        "pm10_method": "same_hour",
        "inputs_through": "2026-11-16T03:00",
        "hours": [
            {"time": "2026-11-16T04:00", "day": "today", "pm25": 30.0, "low": 25.0, "high": 35.0,
             "p_above": [{"threshold": 25.0, "p": 0.9}], "pm10": 40.0, "pm10_low": 30.0, "pm10_high": 50.0},
            {"time": "2026-11-16T05:00", "day": "today", "pm25": 20.0, "low": 15.0, "high": 25.0, "p_above": None},
        ],
    }
    rows = hourly_rows(hourly)
    assert rows["p_above"].iloc[0] == '[{"threshold": 25.0, "p": 0.9}]'
    assert rows["p_above"].iloc[1:].isna().all()  # No chance published, and PM10 had none

    city = pd.Series({pd.Timestamp("2026-11-16T04:00"): 28.0, pd.Timestamp("2026-11-16T05:00"): 18.0})
    scored = score_hourly(rows[rows["target"] == "pm25"], city)
    today = next(row for row in summarize_extra(scored) if row["window_days"] == 7)
    assert today["chances"] == [
        {"threshold": 25.0, "chance_n": 1, "chance_events": 1, "brier": 0.01, "base_rate_brier": 0.0}
    ]


def test_published_chances_get_a_live_brier_score():
    history = pd.DataFrame(
        [
            {**history_row("2026-11-11", "2026-11-11", "today", "pm25", 40.0), "p_above_standard": 0.8},
            {**history_row("2026-11-12", "2026-11-12", "today", "pm25", 20.0), "p_above_standard": 0.1},
            # Older rows have no chance and are left out of the score.
            history_row("2026-11-10", "2026-11-10", "today", "pm25", 20.0),
        ]
    )
    measured = daily({"2026-11-09": 20.0, "2026-11-10": 21.0, "2026-11-11": 45.0, "2026-11-12": 18.0})
    scored = score_history(history, measured)
    assert list(scored["above_standard"].fillna(-1)) == [-1.0, 1.0, 0.0]

    row = next(r for r in summarize(scored, "now")["rows"] if r["window_days"] == 7)
    assert row["chance_n"] == 2
    assert row["chance_events"] == 1
    assert row["brier"] == pytest.approx((0.2**2 + 0.1**2) / 2)
    assert row["base_rate_brier"] == pytest.approx(0.25)


def test_station_chances_are_scored_per_target_standard():
    history = pd.DataFrame(
        {
            "as_of": ["2026-11-12", "2026-11-12"],
            "period": ["2026-11-12", "2026-11-12"],
            "label": ["today", "today"],
            "location_id": ["1", "2"],
            "target": ["pm25", "pm25"],
            "forecast": [30.0, 30.0],
            "low": [20.0, 20.0],
            "high": [40.0, 40.0],
            "method": ["gradient_boosting"] * 2,
            "p_above_standard": [0.3, None],
        }
    )
    stations = pd.DataFrame({1: [25.0, 38.0], 2: [25.0, 38.0]}, index=pd.to_datetime(["2026-11-11", "2026-11-12"]))
    scored = score_stations(history, stations)
    assert list(scored["above_standard"].fillna(-1)) == [1.0, -1.0]
    row = next(r for r in summarize_extra(scored) if r["window_days"] == 7)
    assert row["chance_n"] == 1
    assert row["brier"] == pytest.approx(0.49)


def test_coverage_alert_needs_enough_days_and_low_coverage():
    rows = [
        {"label": "today", "window_days": 30, "n": 300, "days": 20, "coverage": 0.6},
        {"label": "tomorrow", "window_days": 30, "n": 300, "days": 20, "coverage": 0.7},
        {"label": "day2", "window_days": 30, "n": 100, "days": 10, "coverage": 0.3},
        {"label": "today", "window_days": 7, "n": 70, "days": 7, "coverage": 0.1},
    ]
    alerts = coverage_alerts("stations", rows)
    assert alerts == ["stations today: the 80 % range held only 60% of outcomes over the last 30 days (20 days scored)"]


def test_every_band_edge_gets_its_own_live_score():
    import json

    chances = [{"threshold": 25.0, "p": 0.9}, {"threshold": 37.5, "p": 0.4}, {"threshold": 75.0, "p": 0.0}]
    history = pd.DataFrame(
        [
            {**history_row("2026-11-11", "2026-11-11", "today", "pm25", 40.0),
             "p_above_standard": 0.4, "p_above": json.dumps(chances)},
            # Older row: only the standard, scored at 37.5.
            {**history_row("2026-11-12", "2026-11-12", "today", "pm25", 20.0), "p_above_standard": 0.1},
        ]
    )
    measured = daily({"2026-11-10": 20.0, "2026-11-11": 30.0, "2026-11-12": 18.0})
    row = next(r for r in summarize(score_history(history, measured), "now")["rows"] if r["window_days"] == 7)
    by_edge = {c["threshold"]: c for c in row["chances"]}
    assert set(by_edge) == {25.0, 37.5, 75.0}
    assert by_edge[25.0]["chance_events"] == 1 and by_edge[25.0]["brier"] == pytest.approx(0.01)
    assert by_edge[37.5]["chance_n"] == 2 and by_edge[37.5]["brier"] == pytest.approx((0.16 + 0.01) / 2)
    # The top level keeps scoring the standard.
    assert row["chance_n"] == 2
