"""Bangkok PM2.5 estimate from GISTDA, shown next to our forecast as a reference.

GISTDA estimates hourly PM2.5 for every province from satellite data and a
model (https://pm25.gistda.or.th). It is an estimate, not a station
measurement, so it is never used as a target or a model feature. The endpoint
is the one the GISTDA website itself uses and has no published contract, so any
failure only drops the reference from the forecast.
"""

from __future__ import annotations

import time as time_module
from collections.abc import Callable
from typing import Any

import pandas as pd
import requests

from pm25.features import TIMEZONE
from pm25.ingest import get_with_retry

GISTDA_URL = "https://pm25.gistda.or.th/rest/getPm25byProvincePred3"
BANGKOK_PROVINCE_ID = 10


def fetch_gistda_bangkok(
    http_get: Callable[..., Any] = requests.get,
    sleep: Callable[[float], None] = time_module.sleep,
) -> dict[str, Any] | None:
    """Return the latest hourly and 24-hour average estimate for Bangkok, or None."""
    response = get_with_retry(http_get, GISTDA_URL, {}, sleep, pause=0, attempts=3, timeout=30)
    rows = response.json().get("data") or []
    row = next((r for r in rows if r.get("pv_idn") == BANGKOK_PROVINCE_ID), None)
    if row is None or row.get("pm25Avg24hr") is None:
        return None
    observed = pd.Timestamp(row["dt"]).tz_convert(TIMEZONE)
    return {
        "source": "GISTDA satellite estimate",
        "observed_at": observed.isoformat(timespec="minutes"),
        "pm25_hourly": round(float(row["pm25"]), 1),
        "pm25_24h_mean": round(float(row["pm25Avg24hr"]), 1),
    }
