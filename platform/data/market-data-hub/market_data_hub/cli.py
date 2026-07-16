"""Command line interface for market-data-hub."""

from __future__ import annotations

import argparse
import logging

from market_data_hub.exceptions import MarketDataHubError
from market_data_hub.pipelines.recipes.cf_m1 import download_cf_m1_data
from market_data_hub.jobs.daily_update import run_us_daily_update
from market_data_hub.jobs.full_refresh import run_us_full_refresh
from market_data_hub.logging import configure_logging
from market_data_hub.markets.cn.pipelines import (
    download_prices as download_cn_prices,
    export_daily_by_symbol as export_cn_daily_by_symbol,
    merge_daily_increment as merge_cn_daily_increment,
)
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

    cn_download = subparsers.add_parser("download-cn-prices")
    cn_download.add_argument("--config", default="configs/cn.yaml")
    cn_download.add_argument("--start-date")
    cn_download.add_argument("--end-date")
    cn_download.add_argument("--output")
    cn_download.add_argument("--failed-dates-output")
    cn_download.add_argument("--retry-from-failed-dates")

    cn_export = subparsers.add_parser("export-cn-daily-by-symbol")
    cn_export.add_argument("--input", default=str(export_cn_daily_by_symbol.DEFAULT_INPUT_PATH))
    cn_export.add_argument("--output", default=str(export_cn_daily_by_symbol.DEFAULT_OUTPUT_DIR))
    cn_export.add_argument("--overwrite", action="store_true")

    cn_merge = subparsers.add_parser("merge-cn-daily-increment")
    cn_merge.add_argument("--base-dir", required=True)
    cn_merge.add_argument("--increment", required=True)
    cn_merge.add_argument("--output-dir", required=True)
    cn_merge.add_argument("--overwrite", action="store_true")

    cn_daily = subparsers.add_parser("cn-daily-update")
    cn_daily.add_argument("--config", default="configs/cn.yaml")
    cn_daily.add_argument("--start-date", required=True)
    cn_daily.add_argument("--end-date")
    cn_daily.add_argument("--base-dir", required=True)
    cn_daily.add_argument("--output-dir", required=True)
    cn_daily.add_argument("--increment-output")
    cn_daily.add_argument("--failed-dates-output")
    cn_daily.add_argument("--overwrite", action="store_true")

    cf_m1 = subparsers.add_parser("download-cf-m1-data")
    cf_m1.add_argument("--config", default="configs/recipes/cf_m1.yaml")
    cf_m1.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="Download one configured source; repeat for multiple sources. Default: all.",
    )

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
        elif args.command == "download-cn-prices":
            result = download_cn_prices.run(
                args.config,
                start_date=args.start_date,
                end_date=args.end_date,
                output_path=args.output,
                failed_dates_output=args.failed_dates_output,
                retry_from_failed_dates=args.retry_from_failed_dates,
            )
            print(result.summary_text())
        elif args.command == "export-cn-daily-by-symbol":
            summary = export_cn_daily_by_symbol.run(
                input_path=args.input,
                output_dir=args.output,
                overwrite=args.overwrite,
            )
            print(summary.summary_text())
        elif args.command == "merge-cn-daily-increment":
            summary = merge_cn_daily_increment.merge_cn_daily_increment(
                base_dir=args.base_dir,
                increment_path=args.increment,
                output_dir=args.output_dir,
                overwrite=args.overwrite,
            )
            print(summary.summary_text())
        elif args.command == "cn-daily-update":
            download_result = download_cn_prices.run(
                args.config,
                start_date=args.start_date,
                end_date=args.end_date,
                output_path=args.increment_output,
                failed_dates_output=args.failed_dates_output,
            )
            print(download_result.summary_text())
            summary = merge_cn_daily_increment.merge_cn_daily_increment(
                base_dir=args.base_dir,
                increment_path=download_result.output_path,
                output_dir=args.output_dir,
                overwrite=args.overwrite,
            )
            print(summary.summary_text())
        elif args.command == "download-cf-m1-data":
            results = download_cf_m1_data(args.config, sources=args.sources)
            for result in results:
                print(result.summary_text())
        else:
            parser.error(f"Unknown command: {args.command}")
    except MarketDataHubError as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
