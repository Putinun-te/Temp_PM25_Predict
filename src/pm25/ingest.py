"""Idempotent ingestion of Open-Meteo air quality and weather data.

Every series is stored as CSV with UTC timestamps. A run finds the hours that
are missing locally, fetches only those, and upserts by timestamp, so repeating
a run never creates duplicates.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

TIME = "time"
HOUR = pd.Timedelta(hours=1)


def load_series(path: Path) -> pd.DataFrame:
    """Read a stored series, or return an empty frame if it does not exist yet."""
    if not path.exists():
        return pd.DataFrame({TIME: pd.DatetimeIndex([], tz="UTC")})
    frame = pd.read_csv(path)
    frame[TIME] = pd.to_datetime(frame[TIME], utc=True)
    return frame


def upsert(path: Path, new: pd.DataFrame) -> int:
    """Merge rows into a stored series and return how many new timestamps were added.

    The file is replaced atomically, so a crash cannot leave it half written.
    On a timestamp conflict the incoming row wins.
    """
    if new.empty:
        return 0
    old = load_series(path)
    combined = pd.concat([old, new], ignore_index=True) if not old.empty else new
    combined = (
        combined.drop_duplicates(TIME, keep="last").sort_values(TIME).reset_index(drop=True)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(descriptor)
    try:
        combined.to_csv(temporary, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return len(combined) - len(old)


def find_gaps(
    times: Iterable[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    step: pd.Timedelta,
    tolerance: float = 1.5,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Return missing ranges in [start, end] as (low, high) pairs, both exclusive.

    A gap is any distance between neighbouring points above step * tolerance.
    Virtual points one step outside the window make the head and tail of the
    window behave like any other gap.
    """
    if start > end:
        return []
    index = pd.to_datetime(list(times), utc=True).unique().sort_values()
    inside = index[(index >= start) & (index <= end)]
    points = [start - step, *inside, end + step]
    return [(low, high) for low, high in zip(points, points[1:]) if high - low > step * tolerance]
