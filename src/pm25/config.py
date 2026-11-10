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
    """Pipeline settings. Credentials are excluded from repr so they cannot reach logs."""

    data_dir: Path = Path("data")
    models_dir: Path = Path("models")
    latitude: float = 13.7563
    longitude: float = 100.5018
    reference_start: pd.Timestamp = field(default_factory=lambda: _utc_date("2022-08-01"))
    openaq_start: pd.Timestamp = field(default_factory=lambda: _utc_date("2021-04-29"))
    openaq_lookback_days: int = 14
    openaq_api_key: str = field(default="", repr=False)
    firebase_db_url: str = field(default="", repr=False)
    firebase_service_account_json: str = field(default="", repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        defaults = cls()
        return cls(
            data_dir=Path(env.get("PM25_DATA_DIR", str(defaults.data_dir))),
            models_dir=Path(env.get("PM25_MODELS_DIR", str(defaults.models_dir))),
            latitude=float(env.get("PM25_LATITUDE", defaults.latitude)),
            longitude=float(env.get("PM25_LONGITUDE", defaults.longitude)),
            reference_start=_utc_date(env.get("REFERENCE_START", "2022-08-01")),
            openaq_start=_utc_date(env.get("OPENAQ_START", "2021-04-29")),
            openaq_lookback_days=int(
                env.get("OPENAQ_LOOKBACK_DAYS", defaults.openaq_lookback_days)
            ),
            openaq_api_key=env.get("OPENAQ_API_KEY", "").strip(),
            firebase_db_url=env.get("FIREBASE_DB_URL", "").strip(),
            firebase_service_account_json=env.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip(),
        )
