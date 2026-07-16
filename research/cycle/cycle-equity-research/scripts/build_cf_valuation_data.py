#!/usr/bin/env python3
"""Build and audit the M5.1 point-in-time CF valuation data layer."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from research_data_core.paths import find_stock_research_root, resolve_repo_path

from cycle_equity_research.quality.audit import stable_frame_hash
from cycle_equity_research.valuation.panel import build_monthly_valuation_panel
from cycle_equity_research.valuation.report import (
    build_valuation_data_report,
    write_valuation_data_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workspace = find_stock_research_root(PROJECT_ROOT)
    config_path = PROJECT_ROOT / "configs/valuation/cf_valuation_data_v1.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    daily = pd.read_parquet(resolve_repo_path(config["inputs"]["daily_panel"], workspace))
    quarterly = pd.read_parquet(
        resolve_repo_path(config["inputs"]["quarterly_panel"], workspace)
    )
    result = build_monthly_valuation_panel(daily, quarterly, config)
    repeated = build_monthly_valuation_panel(daily, quarterly, config)
    deterministic = stable_frame_hash(result.monthly) == stable_frame_hash(repeated.monthly)
    report = build_valuation_data_report(
        result.monthly, result.diagnostics, config, deterministic=deterministic
    )

    panel_path = resolve_repo_path(config["outputs"]["monthly_panel"], workspace)
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = panel_path.with_name(f"{panel_path.stem}.tmp{panel_path.suffix}")
    result.monthly.to_parquet(temporary, index=False)
    temporary.replace(panel_path)
    _write_json(
        report["current"],
        resolve_repo_path(config["outputs"]["current_snapshot"], workspace),
    )
    write_valuation_data_report(
        report,
        resolve_repo_path(config["outputs"]["report_markdown"], workspace),
        resolve_repo_path(config["outputs"]["report_json"], workspace),
    )
    manifest = {
        "valuation_id": config["valuation_id"],
        "version": str(config["version"]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_end_date": str(config["analysis_end_date"]),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "inputs": config["inputs"],
        "outputs": {
            "monthly_panel": {
                "path": config["outputs"]["monthly_panel"],
                "rows": len(result.monthly),
                "content_hash": stable_frame_hash(result.monthly),
            },
            "current_snapshot": {"path": config["outputs"]["current_snapshot"]},
        },
        "diagnostics": result.diagnostics,
        "deterministic_repeat": deterministic,
        "status": report["status"],
    }
    _write_json(manifest, resolve_repo_path(config["outputs"]["manifest"], workspace))
    print(
        f"months={len(result.monthly)} valid={report['valid_multiple_months']} "
        f"current_multiple={report['current']['ev_to_reported_ttm_ebitda']:.3f} "
        f"pit={report['point_in_time_violations']} status={report['status']}"
    )
    return 0 if report["status"] == "PASS" else 1


def _write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
