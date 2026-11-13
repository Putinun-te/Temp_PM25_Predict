import pandas as pd

from pm25.cams import CAMS_FILENAME, archive_cams, fetch_cams_forecast, load_archive


def payload(first_local_day, days, value=20.0):
    start = pd.Timestamp(first_local_day, tz="Asia/Bangkok").tz_convert("UTC")
    times = pd.date_range(start, periods=24 * days, freq="h")
    return {"hourly": {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in times], "pm2_5": [value] * len(times)}}


def test_daily_means_for_today_and_tomorrow_are_archived(tmp_path, fake_response):
    as_of = pd.Timestamp("2026-11-13")

    def http_get(url, params, timeout):
        assert params["forecast_days"] == 3 and params["hourly"] == "pm2_5"
        return fake_response(payload("2026-11-13", 2))

    rows = fetch_cams_forecast(13.7, 100.5, as_of, "2026-11-13T07:20:00+07:00", http_get, lambda _: None)
    assert list(rows["horizon_days"]) == [1, 2]
    assert list(rows["cams_pm25"]) == [20.0, 20.0]
    assert rows["time"].iloc[1] == pd.Timestamp("2026-11-13 17:00", tz="UTC")  # 14 November in Bangkok

    assert archive_cams(tmp_path, rows) == 2
    # A rerun the same morning replaces the rows instead of adding more.
    assert archive_cams(tmp_path, rows.assign(cams_pm25=21.0)) == 0
    stored = load_archive(tmp_path)
    assert len(stored) == 2 and list(stored["cams_pm25"]) == [21.0, 21.0]
    assert (tmp_path / CAMS_FILENAME).exists()


def test_incomplete_days_are_skipped(fake_response):
    def http_get(url, params, timeout):
        return fake_response(payload("2026-11-13", 1))

    rows = fetch_cams_forecast(13.7, 100.5, pd.Timestamp("2026-11-13"), "x", http_get, lambda _: None)
    assert list(rows["horizon_days"]) == [1]
