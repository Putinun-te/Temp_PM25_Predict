import pandas as pd
import pytest
import requests

from pm25.ingest import (
    OPENAQ_FILENAME,
    PARAMETER,
    SENSOR,
    TIME,
    VALUE,
    OpenAQSensor,
    backfill_openaq,
    fetch_openaq_hours,
    load_series,
    upsert,
)

PM25 = OpenAQSensor(1, "pm25", 100)
PM10 = OpenAQSensor(2, "pm10", 100)
START = pd.Timestamp("2024-01-01 00:00", tz="UTC")
END = pd.Timestamp("2024-01-03 23:00", tz="UTC")


def item(moment, value):
    stamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"value": value, "period": {"datetimeFrom": {"utc": stamp}}}


@pytest.fixture
def api(fake_response):
    class FakeOpenAQ:
        def __init__(self):
            self.rows = {}
            self.calls = []
            self.queue = []
            self.waits = []

        def fill(self, sensor, start=START, end=END, value=10.0):
            times = pd.date_range(start, end, freq="h")
            self.rows.setdefault(sensor.sensor_id, {}).update({t: value for t in times})

        def sleep(self, seconds):
            self.waits.append(seconds)

        def __call__(self, url, params, headers, timeout):
            self.calls.append({"url": url, "params": dict(params), "headers": headers})
            if self.queue:
                return self.queue.pop(0)
            sensor_id = int(url.split("/sensors/")[1].split("/")[0])
            low = pd.Timestamp(params["datetime_from"])
            high = pd.Timestamp(params["datetime_to"])
            times = sorted(t for t in self.rows.get(sensor_id, {}) if low <= t <= high)
            size = params["limit"]
            chosen = times[(params["page"] - 1) * size : params["page"] * size]
            return fake_response({"results": [item(t, self.rows[sensor_id][t]) for t in chosen]})

    return FakeOpenAQ()


def run(api, tmp_path, sensors=(PM25,), start=START, end=END):
    return backfill_openaq(
        tmp_path, "s3cret", start, end, 14, sensors, http_get=api, sleep=api.sleep
    )


def test_key_is_sent_in_a_header_and_never_in_the_url(api, tmp_path):
    api.fill(PM25)
    run(api, tmp_path)
    call = api.calls[0]
    assert call["headers"] == {"X-API-Key": "s3cret"}
    assert "s3cret" not in call["url"]
    assert "s3cret" not in str(call["params"])


def test_rows_use_the_start_of_each_hour_in_utc(api, tmp_path):
    api.fill(PM25)
    assert run(api, tmp_path) == 72
    stored = load_series(tmp_path / OPENAQ_FILENAME)
    assert stored[TIME].min() == START
    assert stored[PARAMETER].unique().tolist() == ["pm25"]


def test_second_run_makes_no_requests_when_nothing_is_missing(api, tmp_path):
    api.fill(PM25)
    run(api, tmp_path)
    api.calls.clear()
    assert run(api, tmp_path) == 0
    assert api.calls == []


def test_two_sensors_in_the_same_hour_stay_separate(api, tmp_path):
    api.fill(PM25)
    api.fill(PM10)
    assert run(api, tmp_path, sensors=(PM25, PM10)) == 144
    assert load_series(tmp_path / OPENAQ_FILENAME)[SENSOR].nunique() == 2


def test_late_report_inside_the_lookback_window_is_recovered(api, tmp_path):
    api.fill(PM25, end=pd.Timestamp("2024-01-01 23:00", tz="UTC"))
    api.fill(PM25, start=pd.Timestamp("2024-01-03 00:00", tz="UTC"))
    assert run(api, tmp_path) == 48
    api.fill(PM25, start=pd.Timestamp("2024-01-02 00:00", tz="UTC"), end=pd.Timestamp("2024-01-02 23:00", tz="UTC"))
    api.calls.clear()
    assert run(api, tmp_path) == 24
    assert len(api.calls) == 1
    assert api.calls[0]["params"]["datetime_from"] == "2024-01-02T00:00:00Z"


def test_old_permanent_outage_is_not_searched_again(api, tmp_path):
    start = pd.Timestamp("2024-01-01 00:00", tz="UTC")
    end = pd.Timestamp("2024-06-01 00:00", tz="UTC")
    recent = pd.Timestamp("2024-05-01 00:00", tz="UTC")
    api.fill(PM25, start=start, end=pd.Timestamp("2024-01-31 23:00", tz="UTC"))
    api.fill(PM25, start=recent, end=end)
    run(api, tmp_path, start=start, end=end)
    api.calls.clear()
    assert run(api, tmp_path, start=start, end=end) == 0
    assert api.calls == []


def test_interrupted_first_load_resumes_from_the_last_stored_hour(api, tmp_path):
    start = pd.Timestamp("2024-01-01 00:00", tz="UTC")
    end = pd.Timestamp("2024-06-01 00:00", tz="UTC")
    resume = pd.Timestamp("2024-02-01 00:00", tz="UTC")
    times = pd.date_range(start, resume, freq="h")
    upsert(
        tmp_path / OPENAQ_FILENAME,
        pd.DataFrame({TIME: times, SENSOR: 1, PARAMETER: "pm25", VALUE: 5.0}),
        keys=(TIME, SENSOR),
    )
    api.fill(PM25, start=start, end=end)
    run(api, tmp_path, start=start, end=end)
    assert api.calls[0]["params"]["datetime_from"] == "2024-02-01T00:00:00Z"
    assert len(load_series(tmp_path / OPENAQ_FILENAME)) == len(pd.date_range(start, end, freq="h"))


@pytest.mark.parametrize("bad", [-3.0, 5000.0, None], ids=["negative", "huge", "missing"])
def test_invalid_values_are_dropped(api, bad):
    api.fill(PM25, end=START, value=bad)
    frame = fetch_openaq_hours(PM25, START.date(), START.date(), "k", api, api.sleep)
    assert frame.empty


def test_pagination_collects_every_page(api):
    api.fill(PM25)
    frame = fetch_openaq_hours(
        PM25, START.date(), END.date(), "k", api, api.sleep, page_size=30
    )
    assert len(frame) == 72
    assert [call["params"]["page"] for call in api.calls] == [1, 2, 3]


def test_rate_limit_waits_then_retries(api, fake_response):
    api.fill(PM25, end=START)
    api.queue = [fake_response({}, status_code=429, headers={"x-ratelimit-reset": "20"})]
    frame = fetch_openaq_hours(PM25, START.date(), START.date(), "k", api, api.sleep)
    assert len(frame) == 1
    assert 21 in api.waits


def test_network_errors_are_retried(api):
    api.fill(PM25, end=START)
    real_call = api.__call__
    failures = [requests.ConnectionError("reset"), requests.Timeout("slow")]

    def flaky(url, params, headers, timeout):
        if failures:
            raise failures.pop(0)
        return real_call(url, params, headers, timeout)

    frame = fetch_openaq_hours(PM25, START.date(), START.date(), "k", flaky, api.sleep)
    assert len(frame) == 1


def test_persistent_network_errors_are_raised(api):
    def down(url, params, headers, timeout):
        raise requests.ConnectionError("down")

    with pytest.raises(requests.ConnectionError):
        fetch_openaq_hours(PM25, START.date(), START.date(), "k", down, api.sleep)


def test_client_errors_are_raised(api, fake_response):
    api.queue = [fake_response({}, status_code=401)]
    with pytest.raises(requests.HTTPError):
        fetch_openaq_hours(PM25, START.date(), START.date(), "k", api, api.sleep)


def test_requests_are_paced_for_the_free_tier(api):
    api.fill(PM25, end=START)
    fetch_openaq_hours(PM25, START.date(), START.date(), "k", api, api.sleep)
    assert api.waits and api.waits[0] >= 1.0
