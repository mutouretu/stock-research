#!/usr/bin/env python3
"""Parse archived USDA AMS 3195 PDFs into normalized fertilizer prices."""

from __future__ import annotations

import argparse
from pathlib import Path

from market_data_hub.domains.commodities.fertilizer_ams import parse_ams_3195_archive


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ARCHIVE = WORKSPACE_ROOT / "storage/shared_data/commodities/ams_3195/raw"
DEFAULT_OUTPUT = WORKSPACE_ROOT / "storage/shared_data/commodities/ams_3195/fertilizer_prices.parquet"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", default=str(DEFAULT_ARCHIVE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    summary = parse_ams_3195_archive(args.archive, args.output)
    print(summary.summary_text())
    for error in summary.errors:
        print(f"warning: {error}")
    return 0 if summary.rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
