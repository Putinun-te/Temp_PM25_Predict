from pathlib import Path

import pandas as pd

from pm25.config import Config, load_env_file


def test_env_file_is_loaded_without_overriding_existing_values(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n\nPM25_TEST_A=from-file\nPM25_TEST_B=\"quoted value\"\n"
        "PM25_TEST_C={\"a\": \"b=c\"}\nPM25_TEST_KEEP=from-file\nnot a setting\n",
        encoding="utf-8",
    )
    for name in ("PM25_TEST_A", "PM25_TEST_B", "PM25_TEST_C"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PM25_TEST_KEEP", "from-shell")
    load_env_file(path)
    import os

    assert os.environ["PM25_TEST_A"] == "from-file"
    assert os.environ["PM25_TEST_B"] == "quoted value"
    assert os.environ["PM25_TEST_C"] == '{"a": "b=c"}'
    assert os.environ["PM25_TEST_KEEP"] == "from-shell"
    for name in ("PM25_TEST_A", "PM25_TEST_B", "PM25_TEST_C"):
        monkeypatch.delenv(name)


def test_missing_env_file_is_ignored(tmp_path):
    load_env_file(tmp_path / "missing.env")


def test_reads_values_from_environment():
    config = Config.from_env(
        {
            "PM25_DATA_DIR": "elsewhere",
            "PM25_LATITUDE": "14.0",
            "PM25_LONGITUDE": "101.0",
            "REFERENCE_START": "2024-02-01",
            "OPENAQ_START": "2023-01-01",
            "OPENAQ_LOOKBACK_DAYS": "7",
        }
    )
    assert config.data_dir == Path("elsewhere")
    assert (config.latitude, config.longitude) == (14.0, 101.0)
    assert config.reference_start == pd.Timestamp("2024-02-01", tz="UTC")
    assert config.openaq_start == pd.Timestamp("2023-01-01", tz="UTC")
    assert config.openaq_lookback_days == 7


def test_defaults_point_at_bangkok():
    config = Config.from_env({})
    assert (config.latitude, config.longitude) == (13.7563, 100.5018)
    assert config.reference_start == pd.Timestamp("2022-08-01", tz="UTC")


def test_repr_never_contains_the_api_key():
    assert "hidden-key" not in repr(Config.from_env({"OPENAQ_API_KEY": "hidden-key"}))
