import pandas as pd
import pytest

from pm25.__main__ import main
from pm25.ingest import AIR_QUALITY, WEATHER


@pytest.fixture
def calls(monkeypatch, tmp_path):
    recorded = {"open_meteo": [], "openaq": []}

    def open_meteo(source, data_dir, latitude, longitude, start, end):
        recorded["open_meteo"].append({"source": source, "data_dir": data_dir, "start": start, "end": end})
        return 0

    def openaq(data_dir, api_key, start, end, lookback_days):
        recorded["openaq"].append({"start": start, "end": end, "lookback": lookback_days})
        return 0

    monkeypatch.setattr("pm25.__main__.backfill_open_meteo", open_meteo)
    monkeypatch.setattr("pm25.__main__.backfill_openaq", openaq)
    monkeypatch.setenv("PM25_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REFERENCE_START", "2024-01-01")
    monkeypatch.setenv("OPENAQ_START", "2021-05-01")
    monkeypatch.setenv("OPENAQ_API_KEY", "test-key")
    return recorded


def test_backfill_covers_every_source_from_its_own_start(calls, tmp_path):
    assert main(["backfill"]) == 0
    assert [call["source"] for call in calls["open_meteo"]] == [AIR_QUALITY, WEATHER]
    assert calls["open_meteo"][0]["data_dir"] == tmp_path
    assert calls["open_meteo"][0]["start"] == pd.Timestamp("2024-01-01", tz="UTC")
    assert calls["openaq"][0]["start"] == pd.Timestamp("2021-05-01", tz="UTC")


def test_backfill_ends_on_a_whole_hour(calls):
    main(["backfill"])
    assert calls["openaq"][0]["end"] == calls["openaq"][0]["end"].floor("h")


def test_start_can_be_overridden(calls):
    main(["backfill", "--start", "2025-06-01"])
    assert calls["open_meteo"][0]["start"] == pd.Timestamp("2025-06-01", tz="UTC")
    assert calls["openaq"][0]["start"] == pd.Timestamp("2025-06-01", tz="UTC")


def test_open_meteo_alone_needs_no_key(calls, monkeypatch):
    monkeypatch.delenv("OPENAQ_API_KEY")
    assert main(["backfill", "--source", "open-meteo"]) == 0
    assert calls["openaq"] == []


@pytest.mark.parametrize("source", ["all", "openaq"])
def test_missing_key_fails_before_any_download(calls, monkeypatch, source):
    monkeypatch.delenv("OPENAQ_API_KEY")
    assert main(["backfill", "--source", source]) == 2
    assert calls["open_meteo"] == [] and calls["openaq"] == []
