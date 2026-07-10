"""Command line interface for market-data-hub."""

from __future__ import annotations

import argparse
import logging

from market_data_hub.exceptions import MarketDataHubError
from market_data_hub.jobs.daily_update import run_us_daily_update
from market_data_hub.jobs.full_refresh import run_us_full_refresh
from market_data_hub.logging import configure_logging
from market_data_hub.markets.us.pipelines import (
    download_corporate_actions,
    download_instruments,
    download_prices,
    export_daily_by_symbol,
    validate_prices,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="market-data-hub")
    parser.add_argument("--log-level", default="INFO", help="Python logging level. Default: INFO")

    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in (
        "download-us-prices",
        "download-us-instruments",
        "download-us-corporate-actions",
        "us-full-refresh",
    ):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--config", default="configs/us.yaml")

    daily = subparsers.add_parser("us-daily-update")
    daily.add_argument("--config", default="configs/us.yaml")
    daily.add_argument("--lookback-days", type=int, default=10)

    validate = subparsers.add_parser("validate-us-prices")
    validate.add_argument("--input", default=str(validate_prices.DEFAULT_INPUT_PATH))
    validate.add_argument("--report", default=str(validate_prices.DEFAULT_REPORT_PATH))

    export = subparsers.add_parser("export-us-daily-by-symbol")
    export.add_argument("--input", default=str(export_daily_by_symbol.DEFAULT_INPUT_PATH))
    export.add_argument("--output", default=str(export_daily_by_symbol.DEFAULT_OUTPUT_DIR))
    export.add_argument("--min-rows", type=int, default=export_daily_by_symbol.DEFAULT_MIN_ROWS)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(getattr(logging, str(args.log_level).upper(), logging.INFO))

    try:
        if args.command == "download-us-prices":
            download_prices.run(args.config)
        elif args.command == "download-us-instruments":
            download_instruments.run(args.config)
        elif args.command == "download-us-corporate-actions":
            download_corporate_actions.run(args.config)
        elif args.command == "us-full-refresh":
            run_us_full_refresh(args.config)
        elif args.command == "us-daily-update":
            run_us_daily_update(args.config, args.lookback_days)
        elif args.command == "validate-us-prices":
            report = validate_prices.validate_us_prices(args.input, args.report)
            print(report.summary_text())
            print(f"report: {args.report}")
        elif args.command == "export-us-daily-by-symbol":
            summary = export_daily_by_symbol.export_us_daily_by_symbol(
                args.input,
                args.output,
                args.min_rows,
            )
            print(summary.summary_text())
        else:
            parser.error(f"Unknown command: {args.command}")
    except MarketDataHubError as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
