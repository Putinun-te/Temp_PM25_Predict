"""Command line entry point: python -m pm25 <command>."""

from __future__ import annotations

import argparse
import json
import logging
import sys

import pandas as pd

from pm25.config import Config
from pm25.features import TIMEZONE, daily_exogenous, daily_targets
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
from pm25.train import load_registry, run_training

log = logging.getLogger("pm25")


def _as_of() -> pd.Timestamp:
    """Return today's date in Bangkok. Only days before it are complete."""
    return pd.Timestamp.now(tz=TIMEZONE).normalize().tz_localize(None)


def _generated_at() -> str:
    return pd.Timestamp.now(tz=TIMEZONE).isoformat(timespec="seconds")


def _load_inputs(
    config: Config, as_of: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    openaq = load_series(config.data_dir / OPENAQ_FILENAME)
    air_quality = load_series(config.data_dir / AIR_QUALITY.filename)
    weather = load_series(config.data_dir / WEATHER.filename)
    if openaq.empty or air_quality.empty or weather.empty:
        log.error("Input data is missing, run the backfill command first")
        return None
    return daily_targets(openaq, as_of), daily_exogenous(air_quality, weather, as_of)


def _backfill(args: argparse.Namespace, config: Config) -> int:
    if args.source in ("all", "openaq") and not config.openaq_api_key:
        log.error("OPENAQ_API_KEY is not set, see .env.example")
        return 2

    end = pd.Timestamp.now(tz="UTC").floor("h")
    override = pd.Timestamp(args.start, tz="UTC") if args.start else None

    if args.source in ("all", "open-meteo"):
        start = override if override is not None else config.reference_start
        for source in (AIR_QUALITY, WEATHER):
            added = backfill_open_meteo(
                source, config.data_dir, config.latitude, config.longitude, start, end
            )
            log.info("%s: added %d rows", source.filename, added)

    if args.source in ("all", "openaq"):
        start = override if override is not None else config.openaq_start
        added = backfill_openaq(
            config.data_dir, config.openaq_api_key, start, end, config.openaq_lookback_days
        )
        log.info("%s: added %d rows", OPENAQ_FILENAME, added)
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
    forecast = build_forecast(*inputs, registry, config.models_dir, as_of, _generated_at())
    log.info("Wrote %s", write_forecast(forecast, config.models_dir))
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

    commands.add_parser("train", help="evaluate, then promote methods").set_defaults(handler=_train)
    commands.add_parser("predict", help="write forecast.json").set_defaults(handler=_predict)
    commands.add_parser("publish", help="send forecast.json to Firebase").set_defaults(
        handler=_publish
    )

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    return args.handler(args, Config.from_env())


if __name__ == "__main__":
    sys.exit(main())
