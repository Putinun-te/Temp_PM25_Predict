import pandas as pd
import pytest

from pm25.__main__ import main
from pm25.ingest import AIR_QUALITY, WEATHER


@pytest.fixture
def calls(monkeypatch, tmp_path):
    recorded = []

    def record(source, data_dir, latitude, longitude, start, end):
        recorded.append({"source": source, "data_dir": data_dir, "start": start, "end": end})
        return 0

    monkeypatch.setattr("pm25.__main__.backfill_open_meteo", record)
    monkeypatch.setenv("PM25_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REFERENCE_START", "2024-01-01")
    return recorded


def test_backfill_covers_both_sources_from_the_configured_start(calls, tmp_path):
    assert main(["backfill"]) == 0
    assert [call["source"] for call in calls] == [AIR_QUALITY, WEATHER]
    assert calls[0]["data_dir"] == tmp_path
    assert calls[0]["start"] == pd.Timestamp("2024-01-01", tz="UTC")


def test_backfill_ends_on_a_whole_hour(calls):
    main(["backfill"])
    assert calls[0]["end"] == calls[0]["end"].floor("h")


def test_start_can_be_overridden(calls):
    main(["backfill", "--start", "2025-06-01"])
    assert calls[0]["start"] == pd.Timestamp("2025-06-01", tz="UTC")
