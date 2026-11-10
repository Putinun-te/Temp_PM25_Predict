import pandas as pd
import pytest

from pm25.ingest import AIR_QUALITY, TIME, backfill_open_meteo, load_series, upsert


def utc(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


@pytest.fixture
def api(fake_response):
    class FakeOpenMeteo:
        def __init__(self):
            self.calls = []
            self.null_from = None

        def __call__(self, url, params, timeout):
            self.calls.append((params["start_date"], params["end_date"]))
            assert params["timezone"] == "GMT"
            times = pd.date_range(params["start_date"], f"{params['end_date']} 23:00", freq="h")
            values = [
                None if self.null_from is not None and t >= pd.Timestamp(self.null_from) else 10.0
                for t in times
            ]
            payload = {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in times]}
            payload.update({name: values for name in params["hourly"].split(",")})
            return fake_response({"hourly": payload})

    return FakeOpenMeteo()


def run(api, tmp_path, start="2024-01-01 00:00", end="2024-01-03 23:00"):
    return backfill_open_meteo(AIR_QUALITY, tmp_path, 13.75, 100.5, utc(start), utc(end), api)


def test_first_run_fetches_the_whole_window(api, tmp_path):
    assert run(api, tmp_path) == 72
    assert api.calls == [("2024-01-01", "2024-01-03")]


def test_second_run_makes_no_requests_and_adds_nothing(api, tmp_path):
    run(api, tmp_path)
    api.calls.clear()
    assert run(api, tmp_path) == 0
    assert api.calls == []


def test_only_the_missing_day_is_requested(api, tmp_path):
    run(api, tmp_path)
    path = tmp_path / AIR_QUALITY.filename
    stored = load_series(path)
    kept = stored[stored[TIME].dt.day != 2]
    path.unlink()
    upsert(path, kept)
    api.calls.clear()

    assert run(api, tmp_path) == 24
    assert api.calls == [("2024-01-02", "2024-01-02")]
    assert not load_series(path)[TIME].duplicated().any()


def test_long_windows_are_split_into_small_requests(api, tmp_path):
    run(api, tmp_path, "2024-01-01 00:00", "2024-07-01 23:00")
    assert len(api.calls) > 1
    assert api.calls[0] == ("2024-01-01", "2024-03-30")
    assert api.calls[1][0] == "2024-03-31"


def test_null_hours_are_not_stored_so_they_are_retried(api, tmp_path):
    api.null_from = "2024-01-03 00:00"
    assert run(api, tmp_path) == 48
    api.null_from = None
    api.calls.clear()
    assert run(api, tmp_path) == 24
    assert api.calls == [("2024-01-03", "2024-01-03")]


def test_hours_after_end_are_never_stored(api, tmp_path):
    run(api, tmp_path, "2024-01-01 00:00", "2024-01-01 10:00")
    stored = load_series(tmp_path / AIR_QUALITY.filename)
    assert stored[TIME].max() == utc("2024-01-01 10:00")
