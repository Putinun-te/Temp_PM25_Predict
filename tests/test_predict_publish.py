import numpy as np
import pandas as pd
import pytest
import requests

from pm25.features import EXOGENOUS_COLUMNS, TARGETS
from pm25.predict import build_forecast
from pm25.publish import publish_forecast

AS_OF = pd.Timestamp("2024-11-11")
NOW = "2024-11-11T02:30:00+07:00"


def inputs():
    index = pd.date_range("2021-01-01", AS_OF - pd.Timedelta(days=1), freq="D", name="date")
    targets = pd.DataFrame({"pm25": 20.0, "pm10": 30.0}, index=index)
    exogenous = pd.DataFrame({name: 1.0 for name in EXOGENOUS_COLUMNS}, index=index)
    return targets, exogenous


def registry():
    daily = {
        f"{target}_h{horizon}": {"method": "persistence", "residual_q80": 5.0}
        for target in TARGETS
        for horizon in (1, 2)
    }
    monthly = {
        f"{target}_m{horizon}": {"method": "climatology", "residual_q80": 4.0}
        for target in TARGETS
        for horizon in (2, 3, 4)
    }
    return {"daily": daily, "monthly": monthly}


def forecast(targets=None, exogenous=None, tmp_path="unused"):
    default_targets, default_exogenous = inputs()
    return build_forecast(
        default_targets if targets is None else targets,
        default_exogenous if exogenous is None else exogenous,
        registry(),
        tmp_path,
        AS_OF,
        NOW,
    )


def test_daily_forecast_labels_seven_days_from_today():
    result = forecast()
    assert [(row["date"], row["label"]) for row in result["daily"]] == [
        ("2024-11-11", "today"),
        ("2024-11-12", "tomorrow"),
        ("2024-11-13", "day2"),
        ("2024-11-14", "day3"),
        ("2024-11-15", "day4"),
        ("2024-11-16", "day5"),
        ("2024-11-17", "day6"),
    ]
    assert [row["horizon_days"] for row in result["daily"]] == list(range(1, 8))


def test_monthly_forecast_covers_the_next_three_calendar_months():
    result = forecast()
    assert [row["month"] for row in result["monthly"]] == ["2024-12", "2025-01", "2025-02"]


def test_values_and_ranges():
    row = forecast()["daily"][0]
    assert (row["pm25"], row["pm25_low"], row["pm25_high"]) == (20.0, 15.0, 25.0)
    assert row["pm25_method"] == "persistence"


def test_low_bound_is_never_negative():
    targets, exogenous = inputs()
    targets[:] = 2.0
    assert forecast(targets, exogenous)["daily"][0]["pm25_low"] == 0.0


def test_fresh_data_is_ok():
    result = forecast()
    assert result["status"] == "ok"
    assert result["data_age_days"] == 0


def test_stale_data_is_reported_and_values_stay_null():
    targets, exogenous = inputs()
    targets.iloc[-3:] = np.nan
    result = forecast(targets, exogenous)
    assert result["status"] == "stale"
    assert result["data_age_days"] == 3
    assert result["daily"][0]["pm25"] is None
    assert result["daily"][0]["pm25_low"] is None


class Recorder:
    def __init__(self, fake_response, status=200):
        self.calls = []
        self.response = fake_response({}, status_code=status)

    def __call__(self, url, json, headers, timeout):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.response


def document():
    return {
        "schema_version": 1,
        "generated_at": NOW,
        "as_of": "2024-11-11",
        "status": "ok",
        "daily": [],
        "monthly": [],
    }


def test_publish_writes_latest_and_history_only_under_predictions(fake_response):
    recorder = Recorder(fake_response)
    publish_forecast("https://db.test/", "tok3n", document(), recorder)
    call = recorder.calls[0]
    assert call["url"] == "https://db.test/predictions.json"
    assert set(call["json"]) == {"latest", "history/2024-11-11"}


def test_publish_token_is_only_in_the_header(fake_response):
    recorder = Recorder(fake_response)
    publish_forecast("https://db.test", "tok3n", document(), recorder)
    call = recorder.calls[0]
    assert call["headers"] == {"Authorization": "Bearer tok3n"}
    assert "tok3n" not in call["url"]
    assert "tok3n" not in str(call["json"])


def test_publish_refuses_an_incomplete_document(fake_response):
    recorder = Recorder(fake_response)
    broken = document()
    del broken["daily"]
    with pytest.raises(ValueError, match="daily"):
        publish_forecast("https://db.test", "t", broken, recorder)
    assert recorder.calls == []


def test_publish_raises_on_http_error(fake_response):
    with pytest.raises(requests.HTTPError):
        publish_forecast("https://db.test", "t", document(), Recorder(fake_response, 401))


def test_missing_tmd_values_are_filled_without_rewriting_published_ones():
    from pm25.predict import fill_missing_tmd

    forecast = {
        "daily": [
            {"date": "2026-11-18", "tmd_temp_c": 29.7},
            {"date": "2026-11-19"},
            {"date": "2026-11-20"},
        ]
    }
    tmd = {
        "2026-11-18": {"temp_c": 30.5},
        "2026-11-19": {"temp_c": 30.1, "rh_pct": 70.0},
    }
    assert fill_missing_tmd(forecast, tmd) == ["2026-11-19"]
    assert forecast["daily"][0]["tmd_temp_c"] == 29.7
    assert forecast["daily"][1] == {"date": "2026-11-19", "tmd_temp_c": 30.1, "tmd_rh_pct": 70.0}
    assert "tmd_temp_c" not in forecast["daily"][2]


def test_chance_above_the_standard_is_published_only_for_slots_that_earned_it():
    reg = registry()
    # Past errors of -10 to +10 around the forecast: 20 + error stays below 37.5.
    reg["daily"]["pm25_h1"]["exceedance"] = {"threshold": 37.5, "edges": [], "quantiles": [list(np.linspace(-10, 10, 50))]}
    targets, exogenous = inputs()
    result = build_forecast(targets, exogenous, reg, "unused", AS_OF, NOW)
    today, tomorrow = result["daily"][0], result["daily"][1]
    assert today["pm25_p_above_standard"] == 0.0
    assert "pm25_p_above_standard" not in tomorrow and "pm10_p_above_standard" not in today
