#!/usr/bin/env python3
"""Describe the planned CF analysis; no model or report is run."""

import argparse
from pathlib import Path

from cycle_equity_research.data import load_instrument_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "configs/instruments/CF.yaml"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_instrument_config(args.config)
    print(f"analysis subject: {config.instrument} ({config.domain})")
    print(f"declared targets: {list(config.targets)}")
    print("analysis execution is intentionally deferred")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
