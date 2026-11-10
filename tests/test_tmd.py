import pandas as pd

from pm25.tmd import fetch_tmd_daily

AS_OF = pd.Timestamp("2026-11-11")


def hours(start, count, tc=25.0, rh=60.0):
    times = pd.date_range(start, periods=count, freq="h", tz="Asia/Bangkok")
    return [
        {"time": t.isoformat(), "data": {"tc": tc + (i % 24) / 10, "rh": rh}}
        for i, t in enumerate(times)
    ]


def test_daily_summary_per_bangkok_date(fake_response):
    calls = []

    def api(url, params, timeout, headers):
        calls.append({"params": params, "headers": headers})
        return fake_response({"WeatherForecasts": [{"forecasts": hours("2026-11-11", 48)}]})

    summary = fetch_tmd_daily("tok3n", 13.75, 100.5, AS_OF, http_get=api, sleep=lambda _: None)
    assert set(summary) == {"2026-11-11", "2026-11-12"}
    day = summary["2026-11-11"]
    assert (day["temp_c_min"], day["temp_c_max"], day["rh_pct"]) == (25.0, 27.3, 60.0)
    assert calls[0]["params"]["date"] == "2026-11-11"
    assert calls[0]["headers"]["authorization"] == "Bearer tok3n"
    assert "tok3n" not in str(calls[0]["params"])


def test_days_with_too_few_hours_are_left_out(fake_response):
    def api(url, params, timeout, headers):
        return fake_response({"WeatherForecasts": [{"forecasts": hours("2026-11-11", 30)}]})

    summary = fetch_tmd_daily("t", 13.75, 100.5, AS_OF, http_get=api, sleep=lambda _: None)
    assert set(summary) == {"2026-11-11"}
