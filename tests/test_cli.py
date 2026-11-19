import pandas as pd
import pytest

from pm25.__main__ import main
from pm25.ingest import AIR_QUALITY, WEATHER


@pytest.fixture
def calls(monkeypatch, tmp_path):
    recorded = {"open_meteo": [], "openaq": [], "nwp": []}

    def nwp(data_dir, latitude, longitude, start, now):
        recorded["nwp"].append({"start": start})
        return 0

    def open_meteo(source, data_dir, latitude, longitude, start, end):
        recorded["open_meteo"].append({"source": source, "data_dir": data_dir, "start": start, "end": end})
        return 0

    def openaq(data_dir, api_key, start, end, lookback_days):
        recorded["openaq"].append({"start": start, "end": end, "lookback": lookback_days})
        return 0

    monkeypatch.setattr("pm25.__main__.backfill_open_meteo", open_meteo)
    monkeypatch.setattr("pm25.__main__.backfill_openaq", openaq)
    monkeypatch.setattr("pm25.__main__.backfill_nwp", nwp)
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    monkeypatch.setenv("PM25_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PM25_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("PM25_ENV_FILE", str(tmp_path / "no.env"))
    monkeypatch.setenv("REFERENCE_START", "2024-01-01")
    monkeypatch.setenv("OPENAQ_START", "2021-05-01")
    monkeypatch.setenv("OPENAQ_API_KEY", "test-key")
    return recorded


def test_backfill_covers_every_source_from_its_own_start(calls, tmp_path):
    assert main(["backfill"]) == 0
    assert [call["source"] for call in calls["open_meteo"]] == [AIR_QUALITY, WEATHER]
    assert calls["open_meteo"][0]["data_dir"] == tmp_path / "bronze"
    assert calls["open_meteo"][0]["start"] == pd.Timestamp("2024-01-01", tz="UTC")
    assert calls["open_meteo"][1]["start"] == pd.Timestamp("2021-01-01", tz="UTC")
    assert calls["openaq"][0]["start"] == pd.Timestamp("2021-05-01", tz="UTC")
    assert calls["nwp"][0]["start"] == pd.Timestamp("2021-01-01", tz="UTC")


def test_backfill_ends_on_a_whole_hour(calls):
    main(["backfill"])
    assert calls["openaq"][0]["end"] == calls["openaq"][0]["end"].floor("h")


def test_start_can_be_overridden(calls):
    main(["backfill", "--start", "2025-06-01"])
    assert calls["open_meteo"][0]["start"] == pd.Timestamp("2025-06-01", tz="UTC")
    assert calls["openaq"][0]["start"] == pd.Timestamp("2025-06-01", tz="UTC")


def test_open_meteo_alone_needs_no_key(calls, monkeypatch):
    monkeypatch.delenv("OPENAQ_API_KEY")
    assert main(["backfill", "--source", "open-meteo"]) == 0
    assert calls["openaq"] == []


@pytest.mark.parametrize("command", ["check", "train", "predict", "report"])
def test_commands_explain_when_input_data_is_missing(calls, command):
    assert main([command]) == 2


def test_publish_needs_firebase_credentials(calls, monkeypatch):
    monkeypatch.delenv("FIREBASE_DB_URL", raising=False)
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    assert main(["publish"]) == 2


@pytest.mark.parametrize("source", ["all", "openaq"])
def test_missing_key_fails_before_any_download(calls, monkeypatch, source):
    monkeypatch.delenv("OPENAQ_API_KEY")
    assert main(["backfill", "--source", source]) == 2
    assert calls["open_meteo"] == [] and calls["openaq"] == []


def _saved_training(models_dir, as_of, slots=None, hourly_keys=None):
    import json

    from pm25.features import ALL_TARGETS
    from pm25.hourly import HOURLY_TARGETS, KNOWN_HOURS, registry_key
    from pm25.train import DAILY_HORIZONS

    models_dir.mkdir(parents=True, exist_ok=True)
    if slots is None:
        slots = [f"{target}_h{horizon}" for target in ALL_TARGETS for horizon in DAILY_HORIZONS]
    (models_dir / "metrics.json").write_text(json.dumps({"as_of": as_of}))
    if hourly_keys is None:
        hourly_keys = [registry_key(target, hour) for target in HOURLY_TARGETS for hour in KNOWN_HOURS]
    registry = {"daily": {slot: {} for slot in slots}, "monthly": {}, **{key: {} for key in hourly_keys}}
    (models_dir / "registry.json").write_text(json.dumps(registry))


def _no_training(monkeypatch):
    ran = []
    monkeypatch.setattr("pm25.__main__._load_inputs", lambda config, as_of: ran.append(as_of))
    monkeypatch.setattr("pm25.__main__._as_of", lambda: pd.Timestamp("2026-11-18"))
    return ran


def test_train_reuses_models_younger_than_the_limit(calls, monkeypatch, tmp_path):
    ran = _no_training(monkeypatch)
    _saved_training(tmp_path / "models", "2026-11-15")
    assert main(["train", "--max-age-days", "7"]) == 0
    assert ran == []


@pytest.mark.parametrize(
    "as_of, slots, hourly_keys",
    [("2026-11-11", None, None), ("2026-11-17", ["pm25_h1"], None), ("2026-11-17", None, ["hourly"])],
    ids=["too old", "slot missing", "hourly model missing"],
)
def test_train_runs_when_models_are_old_or_incomplete(calls, monkeypatch, tmp_path, as_of, slots, hourly_keys):
    ran = _no_training(monkeypatch)
    _saved_training(tmp_path / "models", as_of, slots, hourly_keys)
    assert main(["train", "--max-age-days", "7"]) == 2  # The stubbed inputs are missing, so training stops early
    assert len(ran) == 1


def test_train_always_runs_without_a_limit(calls, monkeypatch, tmp_path):
    ran = _no_training(monkeypatch)
    _saved_training(tmp_path / "models", "2026-11-17")
    main(["train"])
    assert len(ran) == 1


def test_tmd_refresh_fills_tomorrow_and_records_it(calls, monkeypatch, tmp_path):
    import json

    monkeypatch.setattr("pm25.__main__._as_of", lambda: pd.Timestamp("2026-11-18"))
    monkeypatch.setenv("TMD_API_TOKEN", "t")
    monkeypatch.setattr(
        "pm25.__main__.fetch_tmd_daily",
        lambda token, lat, lon, as_of: {
            "2026-11-19": {"temp_c": 30.1, "temp_c_min": 26.0, "temp_c_max": 34.0, "rh_pct": 70.0}
        },
    )
    forecast = {
        "as_of": "2026-11-18",
        "generated_at": "2026-11-18T07:31:19+07:00",
        "daily": [
            {"date": "2026-11-18", "label": "today", "horizon_days": 1, "tmd_temp_c": 29.7},
            {"date": "2026-11-19", "label": "tomorrow", "horizon_days": 2},
        ],
        "monthly": [],
    }
    (tmp_path / "gold").mkdir()
    (tmp_path / "models").mkdir()
    (tmp_path / "gold" / "forecast.json").write_text(json.dumps(forecast))
    assert main(["tmd-refresh"]) == 0
    saved = json.loads((tmp_path / "gold" / "forecast.json").read_text())
    assert saved["daily"][1]["tmd_temp_c"] == 30.1
    assert json.loads((tmp_path / "models" / "forecast.json").read_text()) == saved
    history = pd.read_csv(tmp_path / "gold" / "forecast_history.csv")
    assert set(history["period"]) == {"2026-11-19"}
    assert set(history["target"]) == {"tmd_temp_c", "tmd_temp_c_min", "tmd_temp_c_max", "tmd_rh_pct"}
