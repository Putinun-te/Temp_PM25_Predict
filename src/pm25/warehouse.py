"""Optional load of the medallion layers into Azure SQL Database.

The warehouse is an extra copy for SQL and Power BI. The pipeline never depends
on it: without AZURE_SQL_SERVER the load is skipped, so the project keeps
working after the Azure subscription ends.

Login uses Microsoft Entra ID through azure-identity (the Azure CLI locally,
federated GitHub credentials in CI), so no database password exists.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

BRONZE_LOOKBACK_DAYS = 14

DDL = [
    "IF SCHEMA_ID('bronze') IS NULL EXEC('CREATE SCHEMA bronze')",
    "IF SCHEMA_ID('silver') IS NULL EXEC('CREATE SCHEMA silver')",
    "IF SCHEMA_ID('gold') IS NULL EXEC('CREATE SCHEMA gold')",
    """IF OBJECT_ID('bronze.openaq_hourly') IS NULL CREATE TABLE bronze.openaq_hourly (
        time_utc DATETIME2(0) NOT NULL, sensor_id INT NOT NULL, parameter VARCHAR(8) NOT NULL,
        value FLOAT NOT NULL, CONSTRAINT pk_openaq_hourly PRIMARY KEY (time_utc, sensor_id))""",
    """IF OBJECT_ID('bronze.openmeteo_air_quality') IS NULL CREATE TABLE bronze.openmeteo_air_quality (
        time_utc DATETIME2(0) NOT NULL PRIMARY KEY, om_pm25 FLOAT, om_pm10 FLOAT, om_no2 FLOAT,
        om_o3 FLOAT, om_so2 FLOAT, om_co FLOAT)""",
    """IF OBJECT_ID('bronze.openmeteo_weather') IS NULL CREATE TABLE bronze.openmeteo_weather (
        time_utc DATETIME2(0) NOT NULL PRIMARY KEY, om_temp_c FLOAT, om_rh_pct FLOAT,
        om_precip_mm FLOAT, om_wind_kmh FLOAT, om_wind_deg FLOAT)""",
    """IF OBJECT_ID('silver.daily_city') IS NULL CREATE TABLE silver.daily_city (
        date DATE NOT NULL PRIMARY KEY, pm25 FLOAT, pm10 FLOAT, temp_c FLOAT, rh_pct FLOAT,
        om_pm25 FLOAT, om_no2 FLOAT, om_o3 FLOAT, om_so2 FLOAT, om_co FLOAT, precip_mm FLOAT,
        wind_kmh FLOAT, wind_u FLOAT, wind_v FLOAT)""",
    """IF OBJECT_ID('gold.forecast_history') IS NULL CREATE TABLE gold.forecast_history (
        as_of DATE NOT NULL, generated_at VARCHAR(40) NOT NULL, kind VARCHAR(10) NOT NULL,
        period VARCHAR(10) NOT NULL, label VARCHAR(16) NOT NULL, target VARCHAR(32) NOT NULL,
        unit VARCHAR(8), value FLOAT, low FLOAT, high FLOAT, method VARCHAR(32),
        CONSTRAINT pk_forecast_history PRIMARY KEY (as_of, kind, period, target))""",
    """IF OBJECT_ID('gold.model_metrics') IS NULL CREATE TABLE gold.model_metrics (
        as_of DATE NOT NULL, slot VARCHAR(16) NOT NULL, published_method VARCHAR(32),
        best_candidate VARCHAR(32), best_mae FLOAT, persistence_mae FLOAT, skill FLOAT,
        evaluated_days INT, CONSTRAINT pk_model_metrics PRIMARY KEY (as_of, slot))""",
    """CREATE OR ALTER VIEW gold.v_daily_actual_vs_forecast AS
        SELECT d.date, f.target, d.pm25 AS measured_pm25, d.pm10 AS measured_pm10,
               d.temp_c AS measured_temp_c, d.rh_pct AS measured_rh_pct,
               f.value AS forecast, f.low, f.high, f.method, f.as_of AS issued_on
        FROM gold.forecast_history AS f
        JOIN silver.daily_city AS d ON d.date = TRY_CONVERT(DATE, f.period)
        WHERE f.kind = 'daily' AND f.label = 'tomorrow'""",
    """CREATE OR ALTER VIEW gold.v_latest_forecast AS
        SELECT * FROM gold.forecast_history
        WHERE as_of = (SELECT MAX(as_of) FROM gold.forecast_history)""",
]


@dataclass(frozen=True)
class Table:
    name: str
    columns: Sequence[str]
    time_column: str | None = None  # Set for incremental bronze loads


BRONZE_TABLES = {
    "openaq_hourly.csv": Table(
        "bronze.openaq_hourly", ["time_utc", "sensor_id", "parameter", "value"], "time_utc"
    ),
    "openmeteo_air_quality.csv": Table(
        "bronze.openmeteo_air_quality",
        ["time_utc", "om_pm25", "om_pm10", "om_no2", "om_o3", "om_so2", "om_co"],
        "time_utc",
    ),
    "openmeteo_weather.csv": Table(
        "bronze.openmeteo_weather",
        ["time_utc", "om_temp_c", "om_rh_pct", "om_precip_mm", "om_wind_kmh", "om_wind_deg"],
        "time_utc",
    ),
}
SILVER_DAILY = Table(
    "silver.daily_city",
    ["date", "pm25", "pm10", "temp_c", "rh_pct", "om_pm25", "om_no2", "om_o3", "om_so2",
     "om_co", "precip_mm", "wind_kmh", "wind_u", "wind_v"],
)
GOLD_HISTORY = Table(
    "gold.forecast_history",
    ["as_of", "generated_at", "kind", "period", "label", "target", "unit", "value", "low",
     "high", "method"],
)
GOLD_METRICS = Table(
    "gold.model_metrics",
    ["as_of", "slot", "published_method", "best_candidate", "best_mae", "persistence_mae",
     "skill", "evaluated_days"],
)


def connection_string(server: str, database: str) -> str:
    host = server if "." in server else f"{server}.database.windows.net"
    return (
        f"Server=tcp:{host},1433;Database={database};Encrypt=yes;"
        "TrustServerCertificate=no;Authentication=ActiveDirectoryDefault;Connection Timeout=60"
    )


def _clean(value: Any) -> Any:
    """Convert pandas values to plain Python values the driver accepts."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is not None:
            value = value.tz_convert("UTC").tz_localize(None)
        return value.to_pydatetime()
    if hasattr(value, "item"):
        return value.item()
    return value


def rows(frame: pd.DataFrame, columns: Sequence[str]) -> list[tuple[Any, ...]]:
    """Return rows in column order. Missing columns become NULL."""
    ordered = frame.reindex(columns=list(columns))
    return [tuple(_clean(value) for value in record) for record in ordered.itertuples(index=False)]


def bronze_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns={"time": "time_utc"})


def incremental_cutoff(latest_loaded: pd.Timestamp | None) -> pd.Timestamp | None:
    """Rows from this time on are replaced, so late reports and revisions are picked up."""
    if latest_loaded is None or pd.isna(latest_loaded):
        return None
    return pd.Timestamp(latest_loaded) - pd.Timedelta(days=BRONZE_LOOKBACK_DAYS)


def metrics_frame(metrics: dict[str, Any]) -> pd.DataFrame:
    """Flatten metrics.json into one row per daily slot."""
    records = []
    for slot, entry in metrics.get("daily", {}).items():
        best = entry["best_candidate"]
        records.append(
            {
                "as_of": metrics["as_of"],
                "slot": slot,
                "published_method": entry["published_method"],
                "best_candidate": best,
                "best_mae": entry["overall"][best]["mae"],
                "persistence_mae": entry["overall"]["persistence"]["mae"],
                "skill": entry["skill_vs_persistence"],
                "evaluated_days": entry["overall"][best]["n"],
            }
        )
    return pd.DataFrame(records, columns=list(GOLD_METRICS.columns))


class Warehouse:
    """Thin wrapper over a DB-API connection, so the load logic is testable."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def ensure_schema(self) -> None:
        cursor = self.connection.cursor()
        for statement in DDL:
            cursor.execute(statement)
        self.connection.commit()

    def latest_time(self, table: Table) -> pd.Timestamp | None:
        cursor = self.connection.cursor()
        cursor.execute(f"SELECT MAX({table.time_column}) FROM {table.name}")
        value = cursor.fetchone()[0]
        return None if value is None else pd.Timestamp(value)

    def _insert(self, table: Table, data: Iterable[tuple[Any, ...]]) -> int:
        data = list(data)
        if data:
            cursor = self.connection.cursor()
            cursor.bulkcopy(table.name, data, batch_size=5000, column_mappings=list(table.columns))
        return len(data)

    def load_bronze(self, table: Table, frame: pd.DataFrame) -> int:
        """Replace rows from the cutoff on, then insert. Repeating a run changes nothing."""
        frame = bronze_frame(frame)
        cutoff = incremental_cutoff(self.latest_time(table))
        cursor = self.connection.cursor()
        if cutoff is not None:
            cursor.execute(f"DELETE FROM {table.name} WHERE {table.time_column} >= ?", _clean(cutoff))
            times = pd.to_datetime(frame[table.time_column], utc=True).dt.tz_localize(None)
            frame = frame[times >= cutoff]
        count = self._insert(table, rows(frame, table.columns))
        self.connection.commit()
        return count

    def replace(self, table: Table, frame: pd.DataFrame) -> int:
        """Replace a small table in one transaction."""
        cursor = self.connection.cursor()
        cursor.execute(f"DELETE FROM {table.name}")
        count = self._insert(table, rows(frame, table.columns))
        self.connection.commit()
        return count
