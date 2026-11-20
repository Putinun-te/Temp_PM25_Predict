"""Command line entry point: python -m pm25 <command>."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

from pm25.config import Config, load_env_file
from pm25.tmd import fetch_tmd_daily
from pm25.features import ALL_TARGETS, TIMEZONE, daily_exogenous, daily_targets
from pm25.layers import (
    BRONZE,
    GOLD,
    QUALITY_FILENAME,
    SILVER,
    DAILY_FILENAME,
    build_silver,
    layer,
    migrate_to_medallion,
    run_checks,
    write_quality_report,
    write_silver,
)
from pm25.ingest import (
    AIR_QUALITY,
    OPENAQ_FILENAME,
    WEATHER,
    backfill_open_meteo,
    backfill_openaq,
    load_series,
)
from pm25.alerts import CHANNELS, decide
from pm25.firms import FirmsError, backfill_firms, load_daily_fires
from pm25.cams import archive_cams, fetch_cams_forecast
from pm25.gistda import fetch_gistda_bangkok
from pm25.nwp import backfill_nwp, daily_nwp, load_nwp
from pm25.hourly import (
    AFTERNOON_KNOWN_HOUR,
    KNOWN_HOURS,
    UPDATE_KNOWN_HOURS,
    HOURLY_FILENAME,
    HOURLY_TARGETS,
    LAST_KNOWN_HOUR,
    forecast_hourly,
    has_recent_hours,
    hourly_city,
    registry_key,
    train_hourly,
)
from pm25.hourly import merge_pm10 as merge_hourly_pm10
from pm25.health import check_health, render
from pm25.warehouse import SQL_LOAD_FILENAME
from pm25.monitor import (
    ACCURACY_FILENAME,
    HOURLY_ACCURACY_FILENAME,
    HOURLY_HISTORY_FILENAME,
    HOURLY_KEYS,
    STATION_ACCURACY_FILENAME,
    STATION_HISTORY_FILENAME,
    STATION_KEYS,
    SUMMARY_FILENAME,
    append_rows,
    coverage_alerts,
    hourly_rows,
    read_history,
    score_history,
    score_hourly,
    score_stations,
    station_rows,
    summarize,
    summarize_extra,
)
from pm25.predict import FORECAST_FILENAME, build_forecast, fill_missing_tmd, write_forecast
from pm25.publish import publish_forecast, service_account_token
from pm25.report import (
    CSV_FILENAME,
    HISTORY_FILENAME,
    PDF_FILENAME,
    REPORT_FILENAME,
    append_history,
    build_report,
    forecast_table,
    write_pdf,
)
from pm25.stations import STATIONS_FILENAME, station_days
from pm25.station_model import HORIZONS as STATION_HORIZONS
from pm25.station_model import STATION_TARGETS, forecast_stations, merge_pm10, station_daily, train_stations
from pm25.train import (
    DAILY_HORIZONS,
    METRICS_FILENAME,
    PLOT_FILENAME,
    REGISTRY_FILENAME,
    load_registry,
    run_training,
)

log = logging.getLogger("pm25")


def _as_of() -> pd.Timestamp:
    """Return today's date in Bangkok. Only days before it are complete."""
    return pd.Timestamp.now(tz=TIMEZONE).normalize().tz_localize(None)


def _generated_at() -> str:
    return pd.Timestamp.now(tz=TIMEZONE).isoformat(timespec="seconds")


def _load_inputs(
    config: Config, as_of: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    frames = _load_bronze(config)
    if frames is None:
        return None
    openaq, air_quality, weather = frames
    bronze = layer(config.data_dir, BRONZE)
    fires = load_daily_fires(bronze)
    nwp = daily_nwp(load_nwp(bronze), as_of)
    return daily_targets(openaq, as_of), daily_exogenous(air_quality, weather, as_of, fires, nwp)


def _load_bronze(config: Config) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame] | None:
    bronze = layer(config.data_dir, BRONZE)
    openaq = load_series(bronze / OPENAQ_FILENAME)
    air_quality = load_series(bronze / AIR_QUALITY.filename)
    weather = load_series(bronze / WEATHER.filename)
    if openaq.empty or air_quality.empty or weather.empty:
        log.error("Input data is missing, run the backfill command first")
        return None
    return openaq, air_quality, weather


def _backfill(args: argparse.Namespace, config: Config) -> int:
    if args.source in ("all", "openaq") and not config.openaq_api_key:
        log.error("OPENAQ_API_KEY is not set, see .env.example")
        return 2

    end = pd.Timestamp.now(tz="UTC").floor("h")
    override = pd.Timestamp(args.start, tz="UTC") if args.start else None

    if args.source in ("all", "open-meteo"):
        # Weather history goes back further than modelled air quality, which starts in 2022.
        for source, default_start in (
            (AIR_QUALITY, config.reference_start),
            (WEATHER, config.weather_start),
        ):
            start = override if override is not None else default_start
            added = backfill_open_meteo(
                source, layer(config.data_dir, BRONZE), config.latitude, config.longitude, start, end
            )
            log.info("%s: added %d rows", source.filename, added)
        nwp_start = override if override is not None else config.weather_start
        try:
            added = backfill_nwp(
                layer(config.data_dir, BRONZE), config.latitude, config.longitude, nwp_start, pd.Timestamp.now(tz="UTC")
            )
            log.info("Open-Meteo previous runs: added %d rows", added)
        except requests.RequestException as error:
            # The forecast features are optional, so an outage must not stop the run.
            log.warning("Open-Meteo previous runs unavailable: %s", type(error).__name__)

    if args.source in ("all", "openaq"):
        start = override if override is not None else config.openaq_start
        added = backfill_openaq(
            layer(config.data_dir, BRONZE),
            config.openaq_api_key,
            start,
            end,
            config.openaq_lookback_days,
        )
        log.info("%s: added %d rows", OPENAQ_FILENAME, added)

    if args.source in ("all", "firms"):
        if not config.firms_map_key:
            log.info("FIRMS_MAP_KEY is not set, skipping fire detections")
        else:
            try:
                added = backfill_firms(
                    layer(config.data_dir, BRONZE),
                    config.firms_map_key,
                    override if override is not None else config.firms_start,
                    pd.Timestamp.now(tz="UTC"),
                )
                log.info("FIRMS: added %d hourly rows", added)
            except FirmsError as error:
                # Fire data is an optional feature, so an outage must not stop the forecast.
                log.warning("%s", error)
    return 0


def _check(args: argparse.Namespace, config: Config) -> int:
    """Gate between bronze and silver: write silver only when the data passes."""
    frames = _load_bronze(config)
    if frames is None:
        return 2
    now = pd.Timestamp.now(tz="UTC")
    bronze = layer(config.data_dir, BRONZE)
    daily = build_silver(
        *frames,
        _as_of(),
        load_daily_fires(bronze),
        daily_nwp(load_nwp(bronze), _as_of()),
    )
    checks = run_checks(*frames, daily, now)
    report = write_quality_report(layer(config.data_dir, SILVER) / QUALITY_FILENAME, checks, now)
    for check in checks:
        level = logging.INFO if check.passed else (logging.ERROR if check.severity == "error" else logging.WARNING)
        log.log(level, "%s %s: %s", "PASS" if check.passed else "FAIL", check.name, check.detail)
    if not report["passed"]:
        log.error("Data quality checks failed, silver was not updated")
        return 1
    write_silver(layer(config.data_dir, SILVER) / DAILY_FILENAME, daily)
    return 0


def _training_due(models_dir: Path, as_of: pd.Timestamp, max_age_days: int) -> str | None:
    """Return why the models must be retrained now, or None when the saved ones are fresh enough.

    Predictions always use today's data; only the fitted models and the published
    method per slot are reused. A slot missing from the registry (new code) forces
    training, so new slots never wait for the weekly run.
    """
    try:
        metrics = json.loads((models_dir / METRICS_FILENAME).read_text(encoding="utf-8"))
        trained = pd.Timestamp(metrics["as_of"])
    except (OSError, ValueError, KeyError):
        return "no previous training found"
    registry = load_registry(models_dir)
    expected = [f"{target}_h{horizon}" for target in ALL_TARGETS for horizon in DAILY_HORIZONS]
    missing = [slot for slot in expected if slot not in registry["daily"]]
    missing += [
        registry_key(target, known_hour)
        for target in HOURLY_TARGETS
        for known_hour in KNOWN_HOURS
        if registry_key(target, known_hour) not in registry
    ]
    if missing:
        return f"registry lacks {', '.join(missing)}"
    age = (as_of - trained).days
    if age >= max_age_days:
        return f"models are {age} days old"
    return None


def _train(args: argparse.Namespace, config: Config) -> int:
    as_of = _as_of()
    if args.max_age_days is not None:
        reason = _training_due(config.models_dir, as_of, args.max_age_days)
        if reason is None:
            log.info("Models were trained within %d days, reusing them", args.max_age_days)
            return 0
        log.info("Training: %s", reason)
    inputs = _load_inputs(config, as_of)
    if inputs is None:
        return 2
    published: dict[str, pd.Series] = {}
    report = run_training(*inputs, config.models_dir, _generated_at(), as_of, published)
    for slot, entry in {**report["daily"], **report["monthly"]}.items():
        log.info("%s: %s", slot, entry["published_method"])
    _train_extras(config, inputs, published, as_of)
    return 0


def _train_extras(
    config: Config,
    inputs: tuple[pd.DataFrame, pd.DataFrame],
    published: dict[str, pd.Series],
    as_of: pd.Timestamp,
) -> None:
    """Train the hourly and per-station models and add them to the registry and metrics.

    They build on the city forecast and are extras: an error here is logged and
    leaves the previous hourly and station entries in place, so the daily
    forecast is still published.
    """
    targets, exogenous = inputs
    bronze = layer(config.data_dir, BRONZE)
    openaq = load_series(bronze / OPENAQ_FILENAME)
    registry = load_registry(config.models_dir)
    metrics_path = config.models_dir / METRICS_FILENAME
    report = json.loads(metrics_path.read_text(encoding="utf-8"))
    nwp_hourly = load_nwp(bronze)
    for target in HOURLY_TARGETS:
        city = hourly_city(openaq, target)
        for known_hour in KNOWN_HOURS:
            key = registry_key(target, known_hour)
            try:
                entry, hourly_report = train_hourly(
                    city, nwp_hourly, as_of, config.models_dir, _generated_at(), known_hour, target
                )
                registry[key], report[key] = entry, hourly_report
                log.info("%s: %s", key, entry["method"])
            except Exception:
                log.exception("Training %s failed, keeping its previous method", key)
    registry.setdefault("stations", {})
    report.setdefault("stations", {})
    for target in STATION_TARGETS:
        try:
            stations = station_daily(openaq, as_of, target=target)
            for horizon in STATION_HORIZONS:
                slot = f"{target}_h{horizon}"
                entry, station_report = train_stations(
                    stations, targets, exogenous, horizon, published[slot], config.models_dir, _generated_at(), target
                )
                registry["stations"][slot], report["stations"][slot] = entry, station_report
                log.info("stations %s: %s", slot, entry["method"])
        except Exception:
            log.exception("Station training for %s failed, keeping the previous station methods", target)
    (config.models_dir / REGISTRY_FILENAME).write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    metrics_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _fetch_tmd(config: Config, as_of: pd.Timestamp) -> dict[str, dict[str, float]]:
    """Return the TMD daily summary, or nothing when it is not configured or unavailable."""
    if not config.tmd_api_token:
        log.info("TMD_API_TOKEN is not set, skipping the TMD weather forecast")
        return {}
    try:
        return fetch_tmd_daily(config.tmd_api_token, config.latitude, config.longitude, as_of)
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, AttributeError) as error:
        # The TMD reference is optional, so an outage or a changed response must not stop the forecast.
        log.warning("TMD forecast unavailable: %s", type(error).__name__)
        return {}


def _tmd_refresh(args: argparse.Namespace, config: Config) -> int:
    """Fill TMD values the morning run could not get, usually tomorrow's.

    TMD publishes its new run around 07:45 Bangkok time, after the daily job
    starts, so the morning fetch often lacks tomorrow's later hours.
    """
    as_of = _as_of()
    gold = layer(config.data_dir, GOLD)
    path = gold / FORECAST_FILENAME
    forecast = _read_json(path)
    if forecast is None or forecast["as_of"] != as_of.date().isoformat():
        log.info("No forecast for today, nothing to refresh")
        return 0
    if all("tmd_temp_c" in row for row in forecast["daily"] if row["horizon_days"] <= 2):
        log.info("TMD values are already complete")
        return 0
    filled = fill_missing_tmd(forecast, _fetch_tmd(config, as_of))
    if not filled:
        log.info("TMD still has no complete day to add")
        return 0
    text = json.dumps(forecast, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    (config.models_dir / FORECAST_FILENAME).write_text(text, encoding="utf-8")
    table = forecast_table(forecast)
    added = table["target"].str.startswith("tmd_") & table["period"].isin(filled)
    append_history(gold / HISTORY_FILENAME, table[added])
    log.info("Added TMD values for %s", ", ".join(filled))
    return 0


def _hourly_document(
    openaq: pd.DataFrame,
    nwp_hourly: pd.DataFrame,
    registry: dict,
    models_dir: Path,
    as_of: pd.Timestamp,
    known_hour: int,
) -> dict:
    """Return the hourly PM2.5 forecast, with PM10 added when its model exists and runs."""
    hourly = forecast_hourly(
        hourly_city(openaq), nwp_hourly, registry[registry_key("pm25", known_hour)],
        models_dir, as_of, _generated_at(), known_hour,
    )
    pm10_entry = registry.get(registry_key("pm10", known_hour))
    if pm10_entry is not None:
        try:
            pm10 = forecast_hourly(
                hourly_city(openaq, "pm10"), nwp_hourly, pm10_entry, models_dir, as_of, _generated_at(), known_hour, "pm10"
            )
            merge_hourly_pm10(hourly, pm10)
        except Exception:
            log.exception("Hourly PM10 forecast failed, publishing PM2.5 only")
    return hourly


def _predict(args: argparse.Namespace, config: Config) -> int:
    as_of = _as_of()
    inputs = _load_inputs(config, as_of)
    if inputs is None:
        return 2
    registry = load_registry(config.models_dir)
    if not registry["daily"]:
        log.error("No trained methods found, run the train command first")
        return 2
    tmd = _fetch_tmd(config, as_of)
    forecast = build_forecast(*inputs, registry, config.models_dir, as_of, _generated_at(), tmd)
    try:
        gistda = fetch_gistda_bangkok()
    except (requests.RequestException, ValueError) as error:
        # The GISTDA reference is optional, so its outage must not stop the forecast.
        log.warning("GISTDA estimate unavailable: %s", type(error).__name__)
        gistda = None
    if gistda:
        forecast["gistda"] = gistda
    bronze = layer(config.data_dir, BRONZE)
    openaq = load_series(bronze / OPENAQ_FILENAME)
    if registry.get("stations"):
        try:
            per_target = {}
            for target in STATION_TARGETS:
                city_values = {day["horizon_days"]: day.get(target) for day in forecast["daily"]}
                per_target[target] = forecast_stations(
                    station_daily(openaq, as_of, target=target),
                    *inputs,
                    registry["stations"],
                    config.models_dir,
                    as_of,
                    city_values,
                    target,
                )
            forecast["station_forecasts"] = merge_pm10(per_target["pm25"], per_target["pm10"])
        except Exception:
            log.exception("Station forecast failed, publishing without it")
    if registry.get("hourly"):
        try:
            hourly = _hourly_document(openaq, load_nwp(bronze), registry, config.models_dir, as_of, LAST_KNOWN_HOUR)
            (config.models_dir / HOURLY_FILENAME).write_text(json.dumps(hourly, indent=1) + "\n", encoding="utf-8")
        except Exception:
            log.exception("Hourly forecast failed, publishing without it")
    try:
        cams = fetch_cams_forecast(config.latitude, config.longitude, as_of, _generated_at())
        archive_cams(layer(config.data_dir, BRONZE), cams)
    except (requests.RequestException, KeyError, ValueError) as error:
        # The archive only collects data for later, so a failure is logged and skipped.
        log.warning("CAMS forecast not archived: %s", type(error).__name__)
    log.info("Wrote %s", write_forecast(forecast, config.models_dir))
    return 0


def _report(args: argparse.Namespace, config: Config) -> int:
    forecast_path = config.models_dir / FORECAST_FILENAME
    metrics_path = config.models_dir / METRICS_FILENAME
    if not forecast_path.exists() or not metrics_path.exists():
        log.error("No forecast or metrics found, run train and predict first")
        return 2
    forecast = json.loads(forecast_path.read_text(encoding="utf-8"))
    text = build_report(forecast, json.loads(metrics_path.read_text(encoding="utf-8")))
    table = forecast_table(forecast)
    (config.models_dir / REPORT_FILENAME).write_text(text, encoding="utf-8")
    table.to_csv(config.models_dir / CSV_FILENAME, index=False)
    write_pdf(
        config.models_dir / PDF_FILENAME, forecast, table, config.models_dir / PLOT_FILENAME
    )

    # The data branch survives between runs, so these accumulate. PDFs stay in
    # artifacts only, because a year of them would be far larger than the text.
    reports = config.data_dir.parent / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{forecast['as_of']}.md").write_text(text, encoding="utf-8")
    gold = layer(config.data_dir, GOLD)
    append_history(gold / HISTORY_FILENAME, table)
    (gold / FORECAST_FILENAME).write_text(json.dumps(forecast, indent=2) + "\n", encoding="utf-8")
    hourly_path = config.models_dir / HOURLY_FILENAME
    if hourly_path.exists() and json.loads(hourly_path.read_text(encoding="utf-8"))["as_of"] == forecast["as_of"]:
        # Only today's hourly forecast is published; a stale one would mislead.
        hourly = json.loads(hourly_path.read_text(encoding="utf-8"))
        published = _read_json(gold / HOURLY_FILENAME)
        if not _newer_hourly(published, hourly):
            (gold / HOURLY_FILENAME).write_text(hourly_path.read_text(encoding="utf-8"), encoding="utf-8")
        append_rows(gold / HOURLY_HISTORY_FILENAME, hourly_rows(hourly), HOURLY_KEYS)
    else:
        (gold / HOURLY_FILENAME).unlink(missing_ok=True)
    append_rows(gold / STATION_HISTORY_FILENAME, station_rows(forecast), STATION_KEYS)
    openaq = load_series(layer(config.data_dir, BRONZE) / OPENAQ_FILENAME)
    if not openaq.empty:
        stations = station_days(openaq, pd.Timestamp(forecast["as_of"]), forecast["generated_at"])
        (gold / STATIONS_FILENAME).write_text(json.dumps(stations, indent=1) + "\n", encoding="utf-8")
    log.info("Wrote the report to %s, %s and %s", config.models_dir, reports, gold)
    return 0


def _monitor(args: argparse.Namespace, config: Config) -> int:
    """Score published forecasts against measurements that have arrived since."""
    gold = layer(config.data_dir, GOLD)
    silver_path = layer(config.data_dir, SILVER) / DAILY_FILENAME
    history_path = gold / HISTORY_FILENAME
    if not silver_path.exists() or not history_path.exists():
        log.info("No forecast history or silver data yet, nothing to score")
        return 0
    scored = score_history(pd.read_csv(history_path), pd.read_csv(silver_path))
    scored.to_csv(gold / ACCURACY_FILENAME, index=False)
    summary = summarize(scored, _generated_at())
    openaq = load_series(layer(config.data_dir, BRONZE) / OPENAQ_FILENAME)
    try:
        # These scores are additions; a failure must not hide the main accuracy file.
        extras = _score_extras(gold, openaq)
        summary.update(extras)
        for name, rows in extras.items():
            summary["alerts"].extend(coverage_alerts(name, rows))
    except Exception:
        log.exception("Scoring the hourly and station forecasts failed")
    (gold / SUMMARY_FILENAME).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    log.info("Scored %d published forecasts, latest date %s", len(scored), summary["latest_scored"])
    for alert in summary["alerts"]:
        log.warning("%s", alert)
    return 0


def _score_extras(gold: Path, openaq: pd.DataFrame) -> dict[str, list[dict]]:
    """Score the hourly and station forecasts; return their sections of the summary."""
    sections: dict[str, list[dict]] = {}
    if openaq.empty:
        return sections
    if (gold / HOURLY_HISTORY_FILENAME).exists():
        history = read_history(gold / HOURLY_HISTORY_FILENAME, HOURLY_KEYS)
        parts = []
        for target in HOURLY_TARGETS:
            scored = score_hourly(history[history["target"] == target], hourly_city(openaq, target))
            parts.append(scored)
            for known_hour in KNOWN_HOURS:
                rows = scored[scored["known_hour"] == str(known_hour)]
                if not rows.empty or target == "pm25":
                    sections[registry_key(target, known_hour)] = summarize_extra(rows)
        pd.concat(parts, ignore_index=True).to_csv(gold / HOURLY_ACCURACY_FILENAME, index=False)
    if (gold / STATION_HISTORY_FILENAME).exists():
        history = read_history(gold / STATION_HISTORY_FILENAME, STATION_KEYS)
        parts = [
            score_stations(history[history["target"] == target], station_daily(openaq, _as_of(), target=target))
            for target in STATION_TARGETS
        ]
        pd.concat(parts, ignore_index=True).to_csv(gold / STATION_ACCURACY_FILENAME, index=False)
        sections["stations"] = summarize_extra(parts[0])
        sections["stations_pm10"] = summarize_extra(parts[1])
    return sections


def _hourly_update(args: argparse.Namespace, config: Config) -> int:
    """Repeat the hourly forecast later in the day with the newest measurements."""
    as_of = _as_of()
    known_hour = args.known_hour
    registry = load_registry(config.models_dir)
    if registry.get(registry_key("pm25", known_hour)) is None:
        log.info("No hourly model for hours known up to %02d:00 yet, keeping the current forecast", known_hour)
        return 0
    bronze = layer(config.data_dir, BRONZE)
    openaq = load_series(bronze / OPENAQ_FILENAME)
    if not has_recent_hours(hourly_city(openaq), as_of, known_hour):
        log.warning("Station hours up to %02d:00 have not arrived, keeping the current forecast", known_hour)
        return 0
    hourly = _hourly_document(openaq, load_nwp(bronze), registry, config.models_dir, as_of, known_hour)
    text = json.dumps(hourly, indent=1) + "\n"
    gold = layer(config.data_dir, GOLD)
    (config.models_dir / HOURLY_FILENAME).write_text(text, encoding="utf-8")
    (gold / HOURLY_FILENAME).write_text(text, encoding="utf-8")
    append_rows(gold / HOURLY_HISTORY_FILENAME, hourly_rows(hourly), HOURLY_KEYS)
    log.info("Updated the hourly forecast with measurements through %s", hourly["inputs_through"])
    return 0


def _newer_hourly(published: dict | None, candidate: dict) -> bool:
    """True when the published hourly forecast is for the same day and uses later hours.

    A daily run started by hand in the afternoon or evening must not replace the
    afternoon or evening update with the morning forecast.
    """
    return bool(
        published
        and published.get("as_of") == candidate["as_of"]
        and published.get("inputs_through", "") > candidate["inputs_through"]
    )


def _read_json(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _health(args: argparse.Namespace, config: Config) -> int:
    """Exit 1 when the published outputs are stale or untrustworthy."""
    gold = layer(config.data_dir, GOLD)
    problems = check_health(
        _read_json(gold / FORECAST_FILENAME),
        _read_json(layer(config.data_dir, SILVER) / QUALITY_FILENAME),
        _read_json(gold / SUMMARY_FILENAME),
        _as_of().date(),
        _read_json(gold / HOURLY_FILENAME),
        _read_json(gold / SQL_LOAD_FILENAME),
        pd.Timestamp.now(tz=TIMEZONE).tz_localize(None).to_pydatetime(),
        _read_json(config.models_dir / REGISTRY_FILENAME),
    )
    text = render(problems, _as_of().date())
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    for line in text.splitlines():
        log.log(logging.ERROR if problems else logging.INFO, "%s", line)
    return 1 if problems else 0


def _weekly(args: argparse.Namespace, config: Config) -> int:
    """Write the weekly summary of measurements, live scores and the coming week."""
    from pm25.weekly import build_weekly

    silver_path = layer(config.data_dir, SILVER) / DAILY_FILENAME
    daily = pd.read_csv(silver_path) if silver_path.exists() else pd.DataFrame(columns=["date", *ALL_TARGETS])
    gold = layer(config.data_dir, GOLD)
    text = build_weekly(
        daily, _read_json(gold / SUMMARY_FILENAME), _read_json(gold / FORECAST_FILENAME), _as_of().date()
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0


def _alert(args: argparse.Namespace, config: Config) -> int:
    """Send a public alert when tomorrow's PM2.5 is above the Thai standard (scaffold)."""
    path = config.models_dir / FORECAST_FILENAME
    if not path.exists():
        log.error("No forecast found, run the predict command first")
        return 2
    alert = decide(json.loads(path.read_text(encoding="utf-8")))
    if alert is None:
        log.info("Tomorrow's PM2.5 forecast is within the standard, no alert")
        return 0
    CHANNELS[args.channel]().send(alert)
    return 0


def _load_sql(args: argparse.Namespace, config: Config) -> int:
    """Copy bronze, silver and gold into Azure SQL. Skipped when Azure is not configured."""
    if not config.azure_sql_server:
        log.info("AZURE_SQL_SERVER is not set, skipping the warehouse load")
        return 0
    import mssql_python

    from pm25.warehouse import (
        BRONZE_TABLES,
        GOLD_ACCURACY,
        GOLD_HISTORY,
        GOLD_HOURLY_ACCURACY,
        GOLD_HOURLY_HISTORY,
        GOLD_METRICS,
        GOLD_STATION_ACCURACY,
        GOLD_STATION_HISTORY,
        GOLD_STATIONS,
        SILVER_DAILY,
        Warehouse,
        connection_string,
        extra_frame,
        metrics_frame,
        stations_frame,
    )

    silver_path = layer(config.data_dir, SILVER) / DAILY_FILENAME
    history_path = layer(config.data_dir, GOLD) / HISTORY_FILENAME
    metrics_path = config.models_dir / METRICS_FILENAME
    if not silver_path.exists():
        log.error("Silver data is missing, run the check command first")
        return 2

    # The free tier database pauses when idle and needs up to a minute or two to resume.
    for attempt in range(8):
        try:
            connection = mssql_python.connect(
                connection_string(config.azure_sql_server, config.azure_sql_database)
            )
            break
        except mssql_python.OperationalError:
            if attempt == 7:
                raise
            log.info("Waiting for the database to resume")
            time.sleep(20)
    try:
        warehouse = Warehouse(connection)
        warehouse.ensure_schema()
        bronze = layer(config.data_dir, BRONZE)
        for filename, table in BRONZE_TABLES.items():
            count = warehouse.load_bronze(table, load_series(bronze / filename))
            log.info("%s: wrote %d rows", table.name, count)
        silver = pd.read_csv(silver_path)
        log.info("%s: wrote %d rows", SILVER_DAILY.name, warehouse.replace(SILVER_DAILY, silver))
        if history_path.exists():
            history = pd.read_csv(history_path)
            log.info("%s: wrote %d rows", GOLD_HISTORY.name, warehouse.replace(GOLD_HISTORY, history))
        accuracy_path = layer(config.data_dir, GOLD) / ACCURACY_FILENAME
        if accuracy_path.exists():
            accuracy = pd.read_csv(accuracy_path)
            log.info("%s: wrote %d rows", GOLD_ACCURACY.name, warehouse.replace(GOLD_ACCURACY, accuracy))
        if metrics_path.exists():
            metrics = metrics_frame(json.loads(metrics_path.read_text(encoding="utf-8")))
            log.info("%s: wrote %d rows", GOLD_METRICS.name, warehouse.replace(GOLD_METRICS, metrics))
        gold = layer(config.data_dir, GOLD)
        stations_path = gold / STATIONS_FILENAME
        if stations_path.exists():
            frame = stations_frame(json.loads(stations_path.read_text(encoding="utf-8")))
            log.info("%s: wrote %d rows", GOLD_STATIONS.name, warehouse.replace(GOLD_STATIONS, frame))
        for filename, table in (
            (STATION_HISTORY_FILENAME, GOLD_STATION_HISTORY),
            (STATION_ACCURACY_FILENAME, GOLD_STATION_ACCURACY),
            (HOURLY_HISTORY_FILENAME, GOLD_HOURLY_HISTORY),
            (HOURLY_ACCURACY_FILENAME, GOLD_HOURLY_ACCURACY),
        ):
            if (gold / filename).exists():
                frame = extra_frame(pd.read_csv(gold / filename))
                log.info("%s: wrote %d rows", table.name, warehouse.replace(table, frame))
        # Read back what the database now holds, so the health check can tell a failed load
        # (this step never blocks the forecast) from a good one.
        newest = warehouse.newest_runs()
        record = {"loaded_at": _generated_at(), "newest_as_of": newest}
        (gold / SQL_LOAD_FILENAME).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        log.info("Azure SQL newest runs: %s", newest)
    finally:
        connection.close()
    return 0


def _publish(args: argparse.Namespace, config: Config) -> int:
    if not (config.firebase_db_url and config.firebase_service_account_json):
        log.error("Firebase credentials are not set, see .env.example")
        return 2
    path = config.models_dir / FORECAST_FILENAME
    if not path.exists():
        log.error("No forecast found, run the predict command first")
        return 2
    forecast = json.loads(path.read_text(encoding="utf-8"))
    token = service_account_token(config.firebase_service_account_json)
    publish_forecast(config.firebase_db_url, token, forecast)
    log.info("Published forecast for %s", forecast["as_of"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pm25", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    backfill = commands.add_parser("backfill", help="fetch only the data missing locally")
    backfill.add_argument("--source", choices=("all", "open-meteo", "openaq", "firms"), default="all")
    backfill.add_argument("--start", help="override the start date, as YYYY-MM-DD (UTC)")
    backfill.set_defaults(handler=_backfill)

    commands.add_parser("check", help="run data quality checks and build silver").set_defaults(
        handler=_check
    )
    train = commands.add_parser("train", help="evaluate, then promote methods")
    train.add_argument(
        "--max-age-days",
        type=int,
        help="skip training when the saved models are younger than this and cover every slot",
    )
    train.set_defaults(handler=_train)
    commands.add_parser("predict", help="write forecast.json").set_defaults(handler=_predict)
    commands.add_parser("report", help="write the daily report").set_defaults(handler=_report)
    commands.add_parser("monitor", help="score published forecasts against measurements").set_defaults(
        handler=_monitor
    )
    update = commands.add_parser("hourly-update", help="repeat the hourly forecast with the newest measurements")
    update.add_argument(
        "--known-hour",
        type=int,
        choices=UPDATE_KNOWN_HOURS,
        default=AFTERNOON_KNOWN_HOUR,
        help="last local hour the update may use: 9 for the afternoon run, 16 for the evening run",
    )
    update.set_defaults(
        handler=_hourly_update
    )
    commands.add_parser("tmd-refresh", help="add TMD values the morning run could not get").set_defaults(
        handler=_tmd_refresh
    )
    health = commands.add_parser("health", help="check that today's outputs are fresh")
    health.add_argument("--output", help="also write the result as Markdown to this file")
    health.set_defaults(handler=_health)
    weekly = commands.add_parser("weekly", help="summarise the last seven days as Markdown")
    weekly.add_argument("--output", help="also write the summary to this file")
    weekly.set_defaults(handler=_weekly)
    alert = commands.add_parser("alert", help="alert when tomorrow's PM2.5 is high (scaffold)")
    alert.add_argument("--channel", choices=sorted(CHANNELS), default="console")
    alert.set_defaults(handler=_alert)
    commands.add_parser("load-sql", help="copy the layers into Azure SQL").set_defaults(
        handler=_load_sql
    )
    commands.add_parser("publish", help="send forecast.json to Firebase").set_defaults(
        handler=_publish
    )

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("azure").setLevel(logging.WARNING)
    load_env_file(Path(os.environ.get("PM25_ENV_FILE", ".env")))
    config = Config.from_env()
    moved = migrate_to_medallion(config.data_dir)
    if moved:
        log.info("Moved to the medallion layout: %s", ", ".join(moved))
    return args.handler(args, config)


if __name__ == "__main__":
    sys.exit(main())
