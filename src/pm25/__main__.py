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
from pm25.features import TIMEZONE, daily_exogenous, daily_targets
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
from pm25.predict import FORECAST_FILENAME, build_forecast, write_forecast
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
from pm25.train import METRICS_FILENAME, PLOT_FILENAME, load_registry, run_training

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
    return daily_targets(openaq, as_of), daily_exogenous(air_quality, weather, as_of)


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
    return 0


def _check(args: argparse.Namespace, config: Config) -> int:
    """Gate between bronze and silver: write silver only when the data passes."""
    frames = _load_bronze(config)
    if frames is None:
        return 2
    now = pd.Timestamp.now(tz="UTC")
    daily = build_silver(*frames, _as_of())
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


def _train(args: argparse.Namespace, config: Config) -> int:
    as_of = _as_of()
    inputs = _load_inputs(config, as_of)
    if inputs is None:
        return 2
    report = run_training(*inputs, config.models_dir, _generated_at(), as_of)
    for slot, entry in {**report["daily"], **report["monthly"]}.items():
        log.info("%s: %s", slot, entry["published_method"])
    return 0


def _predict(args: argparse.Namespace, config: Config) -> int:
    as_of = _as_of()
    inputs = _load_inputs(config, as_of)
    if inputs is None:
        return 2
    registry = load_registry(config.models_dir)
    if not registry["daily"]:
        log.error("No trained methods found, run the train command first")
        return 2
    tmd = {}
    if config.tmd_api_token:
        try:
            tmd = fetch_tmd_daily(config.tmd_api_token, config.latitude, config.longitude, as_of)
        except requests.RequestException as error:
            # The TMD reference is optional, so its outage must not stop the forecast.
            log.warning("TMD forecast unavailable: %s", type(error).__name__)
    else:
        log.info("TMD_API_TOKEN is not set, skipping the TMD weather forecast")
    forecast = build_forecast(*inputs, registry, config.models_dir, as_of, _generated_at(), tmd)
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
    log.info("Wrote the report to %s, %s and %s", config.models_dir, reports, gold)
    return 0


def _load_sql(args: argparse.Namespace, config: Config) -> int:
    """Copy bronze, silver and gold into Azure SQL. Skipped when Azure is not configured."""
    if not config.azure_sql_server:
        log.info("AZURE_SQL_SERVER is not set, skipping the warehouse load")
        return 0
    import mssql_python

    from pm25.warehouse import (
        BRONZE_TABLES,
        GOLD_HISTORY,
        GOLD_METRICS,
        SILVER_DAILY,
        Warehouse,
        connection_string,
        metrics_frame,
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
        if metrics_path.exists():
            metrics = metrics_frame(json.loads(metrics_path.read_text(encoding="utf-8")))
            log.info("%s: wrote %d rows", GOLD_METRICS.name, warehouse.replace(GOLD_METRICS, metrics))
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
    backfill.add_argument("--source", choices=("all", "open-meteo", "openaq"), default="all")
    backfill.add_argument("--start", help="override the start date, as YYYY-MM-DD (UTC)")
    backfill.set_defaults(handler=_backfill)

    commands.add_parser("check", help="run data quality checks and build silver").set_defaults(
        handler=_check
    )
    commands.add_parser("train", help="evaluate, then promote methods").set_defaults(handler=_train)
    commands.add_parser("predict", help="write forecast.json").set_defaults(handler=_predict)
    commands.add_parser("report", help="write the daily report").set_defaults(handler=_report)
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
