"""Command line entry point: python -m pm25 <command>."""

from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

from pm25.config import Config
from pm25.ingest import (
    AIR_QUALITY,
    OPENAQ_FILENAME,
    WEATHER,
    backfill_open_meteo,
    backfill_openaq,
)

log = logging.getLogger("pm25")


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pm25", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    backfill = commands.add_parser("backfill", help="fetch only the data missing locally")
    backfill.add_argument("--source", choices=("all", "open-meteo", "openaq"), default="all")
    backfill.add_argument("--start", help="override the start date, as YYYY-MM-DD (UTC)")
    backfill.set_defaults(handler=_backfill)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return args.handler(args, Config.from_env())


if __name__ == "__main__":
    sys.exit(main())
