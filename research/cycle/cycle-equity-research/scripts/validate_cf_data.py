#!/usr/bin/env python3
"""Generate the CF Milestone 1 Markdown and JSON data-quality reports."""

from __future__ import annotations

import argparse
from pathlib import Path

from cycle_equity_research.quality.report import (
    build_data_quality_report,
    write_data_quality_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "configs/quality/cf_m1.yaml"))
    parser.add_argument(
        "--markdown-output",
        default=str(PROJECT_ROOT / "reports/data_quality/cf_data_quality.md"),
    )
    parser.add_argument(
        "--json-output",
        default=str(PROJECT_ROOT / "reports/data_quality/cf_data_quality.json"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = build_data_quality_report(args.config)
    write_data_quality_report(
        report,
        markdown_path=args.markdown_output,
        json_path=args.json_output,
    )
    print(
        f"datasets={len(report.datasets)} errors={report.error_count} "
        f"warnings={report.warning_count}"
    )
    print(f"markdown: {args.markdown_output}")
    print(f"json: {args.json_output}")
    return 1 if report.error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
