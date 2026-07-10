#!/usr/bin/env python3
"""Validate a bounded dataset sample against its YAML contract."""

import argparse

from research_data_core.data import DatasetConfig, DatasetLoader
from research_data_core.schema import require_columns


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--max-files", type=int, default=5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = DatasetConfig.from_yaml(args.config)
    frame = DatasetLoader(config).load(max_files=args.max_files)
    mapped_entity = next(
        (canonical for canonical, source in config.columns.items() if source == config.entity_col),
        config.entity_col,
    )
    mapped_time = next(
        (canonical for canonical, source in config.columns.items() if source == config.time_col),
        config.time_col,
    )
    require_columns(frame, (mapped_entity, mapped_time))
    print(f"OK: {config.dataset_id}")
    print(f"rows: {len(frame)}")
    print(f"columns: {list(frame.columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
