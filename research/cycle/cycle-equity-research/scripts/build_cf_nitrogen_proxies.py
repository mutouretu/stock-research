#!/usr/bin/env python3
"""Build and validate CF Milestone 3 nitrogen-economics proxies."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research_data_core.paths import find_stock_research_root

from cycle_equity_research.features.nitrogen import (
    build_daily_nitrogen_features,
    build_quarterly_nitrogen_features,
    load_nitrogen_config,
)
from cycle_equity_research.features.nitrogen_validation import (
    validate_nitrogen_features,
    write_nitrogen_report,
)
from cycle_equity_research.quality.audit import stable_frame_hash


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workspace = find_stock_research_root(PROJECT_ROOT)
    config_path = PROJECT_ROOT / "configs/features/cf_nitrogen_economics_v1.yaml"
    config = load_nitrogen_config(config_path)
    panel_dir = workspace / "storage/shared_data/research/cycle/CF"
    daily_panel = pd.read_parquet(panel_dir / "daily_panel.parquet")
    quarterly_panel = pd.read_parquet(panel_dir / "quarterly_panel.parquet")
    daily = build_daily_nitrogen_features(daily_panel, config)
    quarterly = build_quarterly_nitrogen_features(quarterly_panel, daily, config)
    daily_repeat = build_daily_nitrogen_features(daily_panel, config)
    quarterly_repeat = build_quarterly_nitrogen_features(quarterly_panel, daily_repeat, config)
    output_dir = panel_dir / "nitrogen_economics"
    _write_parquet(daily, output_dir / "daily_profit_proxies.parquet")
    _write_parquet(quarterly, output_dir / "quarterly_profit_proxies.parquet")
    report = validate_nitrogen_features(daily, quarterly, quarterly_panel, config)
    daily_hash = stable_frame_hash(daily)
    quarterly_hash = stable_frame_hash(quarterly)
    report["determinism"] = {
        "daily_hash": daily_hash,
        "quarterly_hash": quarterly_hash,
        "daily_repeat_match": daily_hash == stable_frame_hash(daily_repeat),
        "quarterly_repeat_match": quarterly_hash == stable_frame_hash(quarterly_repeat),
    }
    if not all(
        [
            report["determinism"]["daily_repeat_match"],
            report["determinism"]["quarterly_repeat_match"],
        ]
    ):
        report["status"] = "ERROR"
        report["errors"].append("nitrogen proxy build is not deterministic")
    report_dir = PROJECT_ROOT / "reports/nitrogen_economics"
    write_nitrogen_report(
        report,
        report_dir / "cf_nitrogen_economics.md",
        report_dir / "cf_nitrogen_economics.json",
    )
    manifest = {
        "model_id": config["model_id"],
        "version": str(config["version"]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "inputs": ["daily_panel.parquet", "quarterly_panel.parquet"],
        "outputs": {
            "daily": {
                "path": "daily_profit_proxies.parquet",
                "rows": len(daily),
                "content_hash": daily_hash,
            },
            "quarterly": {
                "path": "quarterly_profit_proxies.parquet",
                "rows": len(quarterly),
                "content_hash": quarterly_hash,
            },
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"daily={len(daily)} quarterly={len(quarterly)} "
        f"status={report['status']} version={config['version']}"
    )
    return 1 if report["status"] == "ERROR" else 0


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
