import json

import pandas as pd
import pytest

from pm25.firms import (
    COVERAGE_FILENAME,
    HOTSPOTS_FILENAME,
    FirmsError,
    backfill_firms,
    daily_fires,
    fetch_hotspots,
    load_daily_fires,
)
from pm25.ingest import load_series

KEY = "secret-key-123"
HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"


class TextResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


def no_sleep(_seconds):
    pass


def test_fetch_hotspots_sums_detections_per_utc_hour():
    text = HEADER + (
        "14.1,100.2,330,0.4,0.4,2026-02-01,618,N,VIIRS,n,2.0NRT,290,5.5,D\n"
        "14.2,100.3,330,0.4,0.4,2026-02-01,640,N,VIIRS,h,2.0NRT,290,4.5,D\n"
        "14.3,100.4,330,0.4,0.4,2026-02-01,1836,N,VIIRS,n,2.0NRT,290,2.0,N\n"
    )
    calls = []

    def http_get(url, timeout):
        calls.append(url)
        return TextResponse(text)

    rows = fetch_hotspots(KEY, "VIIRS_NOAA20_NRT", pd.Timestamp("2026-02-01"), 1, http_get, no_sleep)

    assert calls == [
        f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{KEY}/VIIRS_NOAA20_NRT/97.5,11.5,105.5,17.5/1/2026-02-01"
    ]
    assert list(rows["time"]) == [
        pd.Timestamp("2026-02-01 06:00", tz="UTC"),
        pd.Timestamp("2026-02-01 18:00", tz="UTC"),
    ]
    assert list(rows["fire_count"]) == [2, 1]
    assert list(rows["fire_frp"]) == [10.0, 2.0]


def test_errors_never_contain_the_key():
    def refused(url, timeout):
        return TextResponse(f"Invalid MAP_KEY {KEY}.")

    with pytest.raises(FirmsError) as error:
        fetch_hotspots(KEY, "VIIRS_NOAA20_NRT", pd.Timestamp("2026-02-01"), 1, refused, no_sleep)
    assert KEY not in str(error.value)

    with pytest.raises(FirmsError) as error:
        fetch_hotspots(KEY, "VIIRS_NOAA20_NRT", pd.Timestamp("2026-02-01"), 1, lambda url, timeout: TextResponse("", 403), no_sleep)
    assert KEY not in str(error.value)


def test_backfill_switches_from_archive_to_near_real_time_and_resumes(tmp_path):
    requested = []

    def http_get(url, timeout):
        if "data_availability" in url:
            return TextResponse("data_id,min_date,max_date\nVIIRS_NOAA20_SP,2012-01-20,2026-01-07\n")
        parts = url.split("/")
        requested.append((parts[-4], parts[-1], int(parts[-2])))
        day = parts[-1]
        return TextResponse(HEADER + f"14.1,100.2,330,0.4,0.4,{day},600,N,VIIRS,n,2,290,1.0,D\n")

    added = backfill_firms(
        tmp_path, KEY, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-12 03:00", tz="UTC"), http_get, no_sleep
    )

    assert requested == [
        ("VIIRS_NOAA20_SP", "2026-01-01", 5),
        ("VIIRS_NOAA20_SP", "2026-01-06", 2),
        ("VIIRS_NOAA20_NRT", "2026-01-08", 5),
    ]
    assert added == 3
    assert json.loads((tmp_path / COVERAGE_FILENAME).read_text()) == {"start": "2026-01-01", "through": "2026-01-11"}

    # The next day only the recent lookback is fetched again.
    requested.clear()
    backfill_firms(tmp_path, KEY, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-13 03:00", tz="UTC"), http_get, no_sleep)
    assert requested == [("VIIRS_NOAA20_NRT", "2026-01-09", 5)]
    assert len(load_series(tmp_path / HOTSPOTS_FILENAME)) == 4


def test_daily_fires_uses_bangkok_days_and_zero_fills_only_covered_days(tmp_path):
    hotspots = pd.DataFrame(
        {
            # 18:00 UTC on 1 February is 01:00 on 2 February in Bangkok.
            "time": pd.to_datetime(["2026-02-01 06:00", "2026-02-01 18:00"], utc=True),
            "fire_count": [3, 2],
            "fire_frp": [10.0, 4.0],
            "product": "VIIRS_NOAA20_NRT",
        }
    )
    daily = daily_fires(hotspots, {"start": "2026-01-31", "through": "2026-02-03"})
    assert list(daily.index.strftime("%Y-%m-%d")) == ["2026-02-01", "2026-02-02", "2026-02-03"]
    assert list(daily["fire_count"]) == [3.0, 2.0, 0.0]
    assert list(daily["fire_frp"]) == [10.0, 4.0, 0.0]

    assert load_daily_fires(tmp_path).empty
