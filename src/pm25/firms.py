"""Satellite fire detections from NASA FIRMS, as a smoke-season feature.

Burning in central Thailand and its neighbours drives the worst Bangkok PM2.5
days from November to March. FIRMS gives every VIIRS hotspot with its fire
radiative power (FRP). The daily count and total FRP inside a box around the
region become model features; the promotion gate decides whether they help.

Archive (standard processing, SP) data is used where it exists, and near real
time (NRT) data after that. A free MAP_KEY is required:
https://firms.modaps.eosdis.nasa.gov/api/map_key/
"""

from __future__ import annotations

import io
import json
import logging
import time as time_module
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from pm25.features import TIMEZONE
from pm25.ingest import TIME, load_series, upsert

log = logging.getLogger(__name__)

API = "https://firms.modaps.eosdis.nasa.gov/api"
HOTSPOTS_FILENAME = "firms_hotspots.csv"
COVERAGE_FILENAME = "firms_coverage.json"
# VIIRS on NOAA-20: archive from 2018 and current near real time. Suomi-NPP near
# real time data stopped on 2 November 2026, so it cannot feed a daily forecast.
SATELLITE = "VIIRS_NOAA20"
# west,south,east,north: central and eastern Thailand, western Cambodia and the
# Myanmar border, the burning areas upwind of Bangkok in the dry season.
AREA = "97.5,11.5,105.5,17.5"
MAX_DAYS_PER_REQUEST = 5  # The API limit
LOOKBACK_DAYS = 3  # Near real time files fill in late, so recent days are fetched again
SECONDS_BETWEEN_REQUESTS = 0.5
# Raw detections would grow to millions of rows, so bronze keeps hourly totals.
# A satellite passes a few times a day, so that is only a handful of rows per day.
COLUMNS = [TIME, "fire_count", "fire_frp", "product"]
FIRE_COLUMNS = ("fire_count", "fire_frp")


class FirmsError(RuntimeError):
    """A FIRMS request failed. The message never contains the MAP_KEY."""


def _get(http_get: Callable[..., Any], url: str, key: str, sleep: Callable[[float], None]) -> str:
    """Return the response text. The key is part of the URL path, so errors are rewritten."""
    for attempt in range(4):
        sleep(SECONDS_BETWEEN_REQUESTS)
        try:
            response = http_get(url, timeout=120)
        except (requests.ConnectionError, requests.Timeout) as error:
            if attempt == 3:
                raise FirmsError(f"FIRMS unreachable: {type(error).__name__}") from None
            sleep(10 * (attempt + 1))
            continue
        if response.status_code == 429 or response.status_code >= 500:
            sleep(30 * (attempt + 1))
            continue
        if response.status_code >= 400:
            raise FirmsError(f"FIRMS returned HTTP {response.status_code}")
        text = response.text
        # An invalid key or a bad request still returns 200 with a one-line message.
        if text and "," not in text.splitlines()[0]:
            raise FirmsError(f"FIRMS refused the request: {text.strip()[:80].replace(key, '***')}")
        return text
    raise FirmsError("FIRMS kept failing after retries")


def archive_end(key: str, http_get: Callable[..., Any] = requests.get, sleep: Callable[[float], None] = time_module.sleep) -> pd.Timestamp | None:
    """Return the last date that standard processing (archive) data covers."""
    text = _get(http_get, f"{API}/data_availability/csv/{key}/{SATELLITE}_SP", key, sleep)
    table = pd.read_csv(io.StringIO(text))
    if table.empty:
        return None
    return pd.Timestamp(table["max_date"].iloc[0])


def fetch_hotspots(
    key: str,
    product: str,
    first: pd.Timestamp,
    days: int,
    http_get: Callable[..., Any] = requests.get,
    sleep: Callable[[float], None] = time_module.sleep,
) -> pd.DataFrame:
    """Return hourly detection counts and total FRP for `days` UTC days from `first`."""
    url = f"{API}/area/csv/{key}/{product}/{AREA}/{days}/{first.date().isoformat()}"
    text = _get(http_get, url, key, sleep)
    raw = pd.read_csv(io.StringIO(text)) if text.strip() else pd.DataFrame()
    if raw.empty:
        return pd.DataFrame(columns=COLUMNS)
    clock = raw["acq_time"].astype(int).astype(str).str.zfill(4)
    times = pd.to_datetime(raw["acq_date"] + " " + clock, format="%Y-%m-%d %H%M", utc=True)
    hourly = raw.assign(hour=times.dt.floor("h")).groupby("hour")
    return pd.DataFrame(
        {
            TIME: hourly.size().index,
            "fire_count": hourly.size().to_numpy(),
            "fire_frp": hourly["frp"].sum().round(1).to_numpy(),
            "product": product,
        }
    )


def read_coverage(data_dir: Path) -> dict[str, str] | None:
    path = data_dir / COVERAGE_FILENAME
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def backfill_firms(
    data_dir: Path,
    key: str,
    start: pd.Timestamp,
    today: pd.Timestamp,
    http_get: Callable[..., Any] = requests.get,
    sleep: Callable[[float], None] = time_module.sleep,
) -> int:
    """Fetch days not yet covered, oldest first, and return how many hourly rows were added.

    Coverage is saved after every request, so an interrupted first load resumes.
    `through` is the last complete UTC day; today is fetched but not counted as covered.
    """
    coverage = read_coverage(data_dir) or {"start": start.date().isoformat(), "through": None}
    first = (
        pd.Timestamp(coverage["through"]) - pd.Timedelta(days=LOOKBACK_DAYS - 1)
        if coverage["through"]
        else pd.Timestamp(coverage["start"])
    )
    first = max(first, pd.Timestamp(coverage["start"]))
    today = pd.Timestamp(today.date())
    sp_end = archive_end(key, http_get, sleep)
    path = data_dir / HOTSPOTS_FILENAME
    added = 0
    while first <= today:
        archive = sp_end is not None and first <= sp_end
        # A request must not straddle the archive end, or the NRT days would be missed.
        last = min(
            first + pd.Timedelta(days=MAX_DAYS_PER_REQUEST - 1),
            sp_end if archive else today,
            today,
        )
        days = (last - first).days + 1
        product = f"{SATELLITE}_SP" if archive else f"{SATELLITE}_NRT"
        rows = fetch_hotspots(key, product, first, days, http_get, sleep)
        added += upsert(path, rows)
        through = min(last, today - pd.Timedelta(days=1))
        if coverage["through"] is None or through > pd.Timestamp(coverage["through"]):
            coverage["through"] = through.date().isoformat()
        (data_dir / COVERAGE_FILENAME).write_text(json.dumps(coverage) + "\n", encoding="utf-8")
        first = last + pd.Timedelta(days=1)
    log.info("FIRMS covers %s to %s", coverage["start"], coverage["through"])
    return added


def daily_fires(hotspots: pd.DataFrame, coverage: dict[str, str] | None) -> pd.DataFrame:
    """Return the detection count and total FRP per Bangkok day.

    Days inside the fetched coverage with no detections are real zeros. Days
    outside it are missing, so a model never mistakes "not fetched" for "no fire".
    """
    if not coverage or not coverage.get("through"):
        return pd.DataFrame(columns=list(FIRE_COLUMNS), index=pd.DatetimeIndex([], name="date"))
    # A Bangkok day ends at 17:00 UTC, so the first UTC day is only partly covered.
    first = pd.Timestamp(coverage["start"]) + pd.Timedelta(days=1)
    calendar = pd.date_range(first, pd.Timestamp(coverage["through"]), freq="D", name="date")
    if hotspots.empty:
        return pd.DataFrame(0.0, index=calendar, columns=list(FIRE_COLUMNS))
    local = hotspots[TIME].dt.tz_convert(TIMEZONE).dt.tz_localize(None).dt.normalize()
    daily = hotspots.assign(date=local).groupby("date")[list(FIRE_COLUMNS)].sum().astype(float)
    return daily.reindex(calendar, fill_value=0.0)


def load_daily_fires(data_dir: Path) -> pd.DataFrame:
    return daily_fires(load_series(data_dir / HOTSPOTS_FILENAME), read_coverage(data_dir))
