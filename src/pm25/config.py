"""Runtime configuration, read only from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


def _utc_date(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


@dataclass(frozen=True)
class Config:
    data_dir: Path = Path("data")
    latitude: float = 13.7563
    longitude: float = 100.5018
    reference_start: pd.Timestamp = field(default_factory=lambda: _utc_date("2022-08-01"))

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        defaults = cls()
        return cls(
            data_dir=Path(env.get("PM25_DATA_DIR", str(defaults.data_dir))),
            latitude=float(env.get("PM25_LATITUDE", defaults.latitude)),
            longitude=float(env.get("PM25_LONGITUDE", defaults.longitude)),
            reference_start=_utc_date(env.get("REFERENCE_START", "2022-08-01")),
        )
