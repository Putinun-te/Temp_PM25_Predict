from pm25.gistda import GISTDA_URL, fetch_gistda_bangkok

PAYLOAD = {
    "status": 200,
    "data": [
        {"pv_idn": 12, "pv_en": "Nonthaburi", "pm25": 30.0, "pm25Avg24hr": 27.0, "dt": "2026-11-13T14:00:00.000Z"},
        {"pv_idn": 10, "pv_en": "Bangkok", "pm25": 23.04, "pm25Avg24hr": 27.96, "dt": "2026-11-13T15:00:00.000Z"},
    ],
}


def test_returns_the_bangkok_estimate_in_local_time(fake_response):
    calls = []

    def http_get(url, **options):
        calls.append(url)
        return fake_response(PAYLOAD)

    result = fetch_gistda_bangkok(http_get, lambda _: None)

    assert calls == [GISTDA_URL]
    assert result == {
        "source": "GISTDA satellite estimate",
        "observed_at": "2026-11-13T22:00+07:00",
        "pm25_hourly": 23.0,
        "pm25_24h_mean": 28.0,
    }


def test_missing_bangkok_row_gives_none(fake_response):
    payload = {"data": [PAYLOAD["data"][0]]}
    assert fetch_gistda_bangkok(lambda url, **options: fake_response(payload), lambda _: None) is None
