#!/usr/bin/env python3
"""Describe the planned CF dataset build without reading or writing data."""

import argparse
from pathlib import Path

from cycle_equity_research.pipelines import describe_cf_dataset_build

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", default=str(PROJECT_ROOT / "configs/datasets"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dataset_ids = describe_cf_dataset_build(args.config_dir)
    print("planned CF dataset inputs:")
    for dataset_id in dataset_ids:
        print(f"  - {dataset_id}")
    print("no physical data was read, merged, or written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
