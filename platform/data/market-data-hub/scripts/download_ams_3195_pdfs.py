#!/usr/bin/env python3
"""Download public USDA AMS 3195 PDFs without an API key."""

from __future__ import annotations

import argparse
from pathlib import Path

from market_data_hub.domains.commodities.ams_documents import download_ams_3195_pdfs


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT = WORKSPACE_ROOT / "storage/shared_data/commodities/ams_3195/raw"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--latest-only", action="store_true")
    args = parser.parse_args()
    summary = download_ams_3195_pdfs(
        args.output,
        max_pages=args.max_pages,
        latest_only=args.latest_only,
    )
    print(summary.summary_text())
    for error in summary.errors:
        print(f"warning: {error}")
    return 0 if summary.downloaded + summary.skipped > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
