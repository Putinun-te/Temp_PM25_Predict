import datetime as dt

import numpy as np
import pandas as pd

from pm25.__main__ import main
from pm25.warehouse import (
    BRONZE_TABLES,
    SILVER_DAILY,
    Warehouse,
    connection_string,
    incremental_cutoff,
    metrics_frame,
    rows,
)


class FakeCursor:
    def __init__(self, log, latest):
        self.log, self.latest = log, latest

    def execute(self, sql, *params):
        self.log.append(("sql", " ".join(sql.split()), params))
        self.result = (self.latest,)

    def fetchone(self):
        return self.result

    def bulkcopy(self, table, data, batch_size, column_mappings):
        self.log.append(("bulk", table, list(data), column_mappings))


class FakeConnection:
    def __init__(self, latest=None):
        self.log, self.latest, self.commits = [], latest, 0

    def cursor(self):
        return FakeCursor(self.log, self.latest)

    def commit(self):
        self.commits += 1


def hourly(start, hours):
    times = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"time": times, "sensor_id": 1, "parameter": "pm25", "value": 10.0})


def test_connection_string_uses_entra_login_and_encryption():
    text = connection_string("sqlpm25", "pm25")
    assert "Server=tcp:sqlpm25.database.windows.net,1433" in text
    assert "Authentication=ActiveDirectoryDefault" in text
    assert "Encrypt=yes" in text
    assert "Password" not in text


def test_rows_turn_missing_values_into_null_and_times_into_naive_utc():
    frame = pd.DataFrame({"time_utc": [pd.Timestamp("2026-01-01 07:00", tz="Asia/Bangkok")], "value": [np.nan]})
    assert rows(frame, ["time_utc", "value", "absent"]) == [(dt.datetime(2026, 1, 1, 0, 0), None, None)]


def test_cutoff_replays_the_last_two_weeks():
    assert incremental_cutoff(None) is None
    assert incremental_cutoff(pd.Timestamp("2026-11-15")) == pd.Timestamp("2026-11-01")


def test_first_bronze_load_inserts_everything():
    connection = FakeConnection(latest=None)
    count = Warehouse(connection).load_bronze(BRONZE_TABLES["openaq_hourly.csv"], hourly("2026-11-01", 48))
    assert count == 48
    assert not any(entry[0] == "sql" and entry[1].startswith("DELETE") for entry in connection.log)
    assert connection.commits == 1


def test_later_bronze_load_replaces_only_the_recent_window():
    connection = FakeConnection(latest=dt.datetime(2026, 11, 20))
    frame = hourly("2026-10-01", 24 * 60)
    count = Warehouse(connection).load_bronze(BRONZE_TABLES["openaq_hourly.csv"], frame)
    delete = next(entry for entry in connection.log if entry[0] == "sql" and entry[1].startswith("DELETE"))
    assert delete[2] == (dt.datetime(2026, 11, 6),)
    bulk = next(entry for entry in connection.log if entry[0] == "bulk")
    assert min(row[0] for row in bulk[2]) == dt.datetime(2026, 11, 6)
    assert count == len(bulk[2])


def test_replace_clears_then_inserts_small_tables():
    connection = FakeConnection()
    frame = pd.DataFrame({"date": ["2026-11-10"], "pm25": [20.0]})
    assert Warehouse(connection).replace(SILVER_DAILY, frame) == 1
    assert connection.log[0][1] == "DELETE FROM silver.daily_city"
    assert connection.log[1][2][0][:3] == ("2026-11-10", 20.0, None)


def test_metrics_are_flattened_per_slot():
    metrics = {
        "as_of": "2026-11-12",
        "daily": {
            "pm25_h2": {
                "published_method": "random_forest",
                "best_candidate": "random_forest",
                "overall": {"random_forest": {"mae": 4.6, "n": 1143}, "persistence": {"mae": 5.3}},
                "skill_vs_persistence": 0.12,
            }
        },
    }
    frame = metrics_frame(metrics)
    assert frame.iloc[0].to_dict() == {
        "as_of": "2026-11-12",
        "slot": "pm25_h2",
        "published_method": "random_forest",
        "best_candidate": "random_forest",
        "best_mae": 4.6,
        "persistence_mae": 5.3,
        "skill": 0.12,
        "evaluated_days": 1143,
    }


def test_load_is_skipped_without_azure(monkeypatch, tmp_path):
    monkeypatch.delenv("AZURE_SQL_SERVER", raising=False)
    monkeypatch.setenv("PM25_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PM25_ENV_FILE", str(tmp_path / "no.env"))
    assert main(["load-sql"]) == 0
