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

# Daily labels are today, tomorrow, then day2 to day6 (days after today).
HORIZON_FROM_LABEL = (
    "CASE label WHEN 'today' THEN 1 WHEN 'tomorrow' THEN 2 "
    "ELSE TRY_CAST(SUBSTRING(label, 4, 2) AS INT) + 1 END"
)

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
    """IF OBJECT_ID('gold.live_accuracy') IS NULL CREATE TABLE gold.live_accuracy (
        as_of DATE NOT NULL, period DATE NOT NULL, label VARCHAR(16) NOT NULL,
        target VARCHAR(16) NOT NULL, source VARCHAR(16) NOT NULL, method VARCHAR(32),
        forecast FLOAT, low FLOAT, high FLOAT, actual FLOAT, persistence FLOAT,
        abs_error FLOAT, persistence_abs_error FLOAT, in_range BIT,
        CONSTRAINT pk_live_accuracy PRIMARY KEY (as_of, period, target, source))""",
    """CREATE OR ALTER VIEW gold.v_live_accuracy_30d AS
        SELECT target, label, source, COUNT(*) AS days, AVG(abs_error) AS mae,
               AVG(persistence_abs_error) AS persistence_mae,
               AVG(CAST(in_range AS FLOAT)) AS coverage
        FROM gold.live_accuracy
        WHERE period > DATEADD(DAY, -30, (SELECT MAX(period) FROM gold.live_accuracy))
        GROUP BY target, label, source""",
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
    """IF OBJECT_ID('gold.stations') IS NULL CREATE TABLE gold.stations (
        location_id INT NOT NULL PRIMARY KEY, name NVARCHAR(200), locality NVARCHAR(100),
        latitude FLOAT, longitude FLOAT)""",
    """IF OBJECT_ID('gold.station_forecast_history') IS NULL CREATE TABLE gold.station_forecast_history (
        as_of DATE NOT NULL, period DATE NOT NULL, label VARCHAR(16), location_id INT NOT NULL,
        target VARCHAR(8) NOT NULL, forecast FLOAT, low FLOAT, high FLOAT, method VARCHAR(32),
        CONSTRAINT pk_station_forecast_history PRIMARY KEY (as_of, period, location_id, target))""",
    """IF OBJECT_ID('gold.live_accuracy_stations') IS NULL CREATE TABLE gold.live_accuracy_stations (
        as_of DATE NOT NULL, period DATE NOT NULL, label VARCHAR(16), location_id INT NOT NULL,
        target VARCHAR(8) NOT NULL, method VARCHAR(32), forecast FLOAT, low FLOAT, high FLOAT,
        actual FLOAT, persistence FLOAT, abs_error FLOAT, persistence_abs_error FLOAT, in_range BIT,
        CONSTRAINT pk_live_accuracy_stations PRIMARY KEY (as_of, period, location_id, target))""",
    # Hourly times are Bangkok local time, as in the published forecast.
    """IF OBJECT_ID('gold.hourly_forecast_history') IS NULL CREATE TABLE gold.hourly_forecast_history (
        as_of DATE NOT NULL, time_local DATETIME2(0) NOT NULL, known_hour INT NOT NULL,
        target VARCHAR(8) NOT NULL, label VARCHAR(16), forecast FLOAT, low FLOAT, high FLOAT,
        method VARCHAR(32),
        CONSTRAINT pk_hourly_forecast_history PRIMARY KEY (as_of, time_local, known_hour, target))""",
    """IF OBJECT_ID('gold.live_accuracy_hourly') IS NULL CREATE TABLE gold.live_accuracy_hourly (
        as_of DATE NOT NULL, time_local DATETIME2(0) NOT NULL, known_hour INT NOT NULL,
        target VARCHAR(8) NOT NULL, label VARCHAR(16), method VARCHAR(32), forecast FLOAT, low FLOAT,
        high FLOAT, actual FLOAT, persistence FLOAT, abs_error FLOAT, persistence_abs_error FLOAT,
        in_range BIT,
        CONSTRAINT pk_live_accuracy_hourly PRIMARY KEY (as_of, time_local, known_hour, target))""",
    # Each station's forecast from the newest run, with its name and position for a map.
    """CREATE OR ALTER VIEW gold.v_latest_station_forecast AS
        SELECT f.as_of, f.period, f.label, f.target, f.forecast, f.low, f.high, f.method,
               s.location_id, s.name, s.locality, s.latitude, s.longitude
        FROM gold.station_forecast_history AS f
        JOIN gold.stations AS s ON s.location_id = f.location_id
        WHERE f.as_of = (SELECT MAX(as_of) FROM gold.station_forecast_history)""",
    # The newest hourly forecast: the latest run of the latest day (the afternoon update when it ran).
    """CREATE OR ALTER VIEW gold.v_latest_hourly_forecast AS
        SELECT h.* FROM gold.hourly_forecast_history AS h
        WHERE h.as_of = (SELECT MAX(as_of) FROM gold.hourly_forecast_history)
          AND h.known_hour = (SELECT MAX(known_hour) FROM gold.hourly_forecast_history
                              WHERE as_of = h.as_of)""",
    # The next seven days from the newest run, one row per day and target.
    # horizon is 1 for today and 7 for six days after today.
    f"""CREATE OR ALTER VIEW gold.v_week_forecast AS
        SELECT as_of, TRY_CONVERT(DATE, period) AS date, label, {HORIZON_FROM_LABEL} AS horizon,
               target, unit, value, low, high, method
        FROM gold.forecast_history
        WHERE kind = 'daily' AND as_of = (SELECT MAX(as_of) FROM gold.forecast_history)""",
    # Out-of-sample error per target and horizon from the latest training run.
    """CREATE OR ALTER VIEW gold.v_skill_by_horizon AS
        SELECT as_of, LEFT(slot, CHARINDEX('_h', slot) - 1) AS target,
               TRY_CAST(SUBSTRING(slot, CHARINDEX('_h', slot) + 2, 2) AS INT) AS horizon,
               slot, published_method, best_candidate, best_mae, persistence_mae, skill, evaluated_days
        FROM gold.model_metrics
        WHERE as_of = (SELECT MAX(as_of) FROM gold.model_metrics)""",
    # Live error per target and horizon over the last 30 scored days.
    f"""CREATE OR ALTER VIEW gold.v_live_accuracy_by_horizon AS
        SELECT target, source, label, {HORIZON_FROM_LABEL} AS horizon, COUNT(*) AS days,
               AVG(abs_error) AS mae, AVG(persistence_abs_error) AS persistence_mae,
               AVG(CAST(in_range AS FLOAT)) AS coverage
        FROM gold.live_accuracy
        WHERE period > DATEADD(DAY, -30, (SELECT MAX(period) FROM gold.live_accuracy))
        GROUP BY target, source, label""",
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
GOLD_ACCURACY = Table(
    "gold.live_accuracy",
    ["as_of", "period", "label", "target", "source", "method", "forecast", "low", "high",
     "actual", "persistence", "abs_error", "persistence_abs_error", "in_range"],
)
GOLD_STATIONS = Table("gold.stations", ["location_id", "name", "locality", "latitude", "longitude"])
GOLD_STATION_HISTORY = Table(
    "gold.station_forecast_history",
    ["as_of", "period", "label", "location_id", "target", "forecast", "low", "high", "method"],
)
GOLD_STATION_ACCURACY = Table(
    "gold.live_accuracy_stations",
    ["as_of", "period", "label", "location_id", "target", "method", "forecast", "low", "high",
     "actual", "persistence", "abs_error", "persistence_abs_error", "in_range"],
)
GOLD_HOURLY_HISTORY = Table(
    "gold.hourly_forecast_history",
    ["as_of", "time_local", "known_hour", "target", "label", "forecast", "low", "high", "method"],
)
GOLD_HOURLY_ACCURACY = Table(
    "gold.live_accuracy_hourly",
    ["as_of", "time_local", "known_hour", "target", "label", "method", "forecast", "low", "high",
     "actual", "persistence", "abs_error", "persistence_abs_error", "in_range"],
)
# Files written before these columns existed hold only the morning run and only PM2.5.
EXTRA_DEFAULTS = {"known_hour": 3, "target": "pm25"}

GOLD_METRICS = Table(
    "gold.model_metrics",
    ["as_of", "slot", "published_method", "best_candidate", "best_mae", "persistence_mae",
     "skill", "evaluated_days"],
)


# The health check reads these back to confirm Power BI has today's runs.
SQL_FRESHNESS_TABLES = ("gold.forecast_history", "gold.station_forecast_history", "gold.hourly_forecast_history")
SQL_LOAD_FILENAME = "sql_load.json"


def connection_string(server: str, database: str) -> str:
    host = server if "." in server else f"{server}.database.windows.net"
    return (
        f"Server=tcp:{host},1433;Database={database};Encrypt=yes;"
        "TrustServerCertificate=no;Authentication=ActiveDirectoryDefault"
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


def stations_frame(stations: dict[str, Any]) -> pd.DataFrame:
    """One row per reference station from gold/stations.json."""
    return pd.DataFrame(stations.get("stations", []), columns=list(GOLD_STATIONS.columns))


def extra_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Prepare a station or hourly gold file: fill older rows' defaults and parse local times."""
    frame = frame.copy()
    for column, default in EXTRA_DEFAULTS.items():
        if column in frame:
            frame[column] = frame[column].fillna(default)
    if "time" in frame:
        frame["time_local"] = pd.to_datetime(frame.pop("time"))
    return frame


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

    def newest_runs(self) -> dict[str, str | None]:
        """Return the newest as_of of each forecast table, read back after a load."""
        result: dict[str, str | None] = {}
        cursor = self.connection.cursor()
        for name in SQL_FRESHNESS_TABLES:
            cursor.execute(f"SELECT MAX(as_of) FROM {name}")
            value = cursor.fetchone()[0]
            result[name] = None if value is None else pd.Timestamp(value).date().isoformat()
        return result

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
            # Bulk copy runs on its own session, so the delete must be committed first or
            # its locks block the copy. A failed copy is repaired by the next run's wider replay.
            self.connection.commit()
            times = pd.to_datetime(frame[table.time_column], utc=True).dt.tz_localize(None)
            frame = frame[times >= cutoff]
        count = self._insert(table, rows(frame, table.columns))
        self.connection.commit()
        return count

    def replace(self, table: Table, frame: pd.DataFrame) -> int:
        """Replace a small table. Rerunning repairs any partial replace."""
        cursor = self.connection.cursor()
        cursor.execute(f"DELETE FROM {table.name}")
        self.connection.commit()
        count = self._insert(table, rows(frame, table.columns))
        self.connection.commit()
        return count
