#!/usr/bin/env python3
"""List CF dataset contracts without reading physical data."""

import argparse
from pathlib import Path

from cycle_equity_research.data import load_dataset_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", default=str(PROJECT_ROOT / "configs/datasets"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    catalog = load_dataset_catalog(args.config_dir)
    for dataset_id in catalog.list_dataset_ids():
        config = catalog.get(dataset_id)
        print(
            f"{config.dataset_id}: path={config.path} "
            f"entity_col={config.entity_col} time_col={config.time_col}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
