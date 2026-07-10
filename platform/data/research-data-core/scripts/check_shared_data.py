#!/usr/bin/env python3
"""Inspect the shared-data root without recursively listing its contents."""

import argparse
import subprocess

from research_data_core.paths import get_shared_data_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-entries", type=int, default=10)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    shared = get_shared_data_dir()
    if not shared.is_dir():
        raise SystemExit(f"shared-data directory does not exist: {shared}")
    size = subprocess.run(
        ["du", "-sh", str(shared)], capture_output=True, check=True, text=True
    ).stdout.split()[0]
    entries = sorted(shared.iterdir(), key=lambda value: value.name)
    print(f"path: {shared}")
    print(f"size: {size}")
    print("top-level entries:")
    for entry in entries[: args.max_entries]:
        print(f"  {entry}")
    print("sample paths:")
    for directory in (entry for entry in entries if entry.is_dir()):
        for sample in sorted(directory.iterdir(), key=lambda value: value.name)[:2]:
            print(f"  {sample}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
