#!/usr/bin/env python3
"""Load and print a bounded dataset sample."""

import argparse

from research_data_core.data import DatasetConfig, DatasetLoader


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--max-rows", type=int, default=5)
    parser.add_argument("--max-files", type=int, default=5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = DatasetConfig.from_yaml(args.config)
    frame = DatasetLoader(config).load(max_files=args.max_files, max_rows=args.max_rows)
    print(f"dataset_id: {config.dataset_id}")
    print(f"shape: {frame.shape}")
    print(f"columns: {list(frame.columns)}")
    print(frame.head(args.max_rows).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
