#!/usr/bin/env python3
"""Build the M5.3 CF valuation matrix and implied operating assumptions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from research_data_core.paths import find_stock_research_root, resolve_repo_path

from cycle_equity_research.quality.audit import stable_frame_hash
from cycle_equity_research.valuation.range import build_valuation_range
from cycle_equity_research.valuation.range_report import (
    build_valuation_range_report,
    write_valuation_range_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workspace = find_stock_research_root(PROJECT_ROOT)
    config_path = PROJECT_ROOT / "configs/valuation/cf_valuation_range_v1.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    monthly = pd.read_parquet(
        resolve_repo_path(config["inputs"]["monthly_valuation"], workspace)
    )
    scenarios = pd.read_parquet(
        resolve_repo_path(config["inputs"]["midcycle_scenarios"], workspace)
    )
    midcycle_report = _json(
        resolve_repo_path(config["inputs"]["midcycle_report"], workspace)
    )
    cycle_state = _json(
        resolve_repo_path(config["inputs"]["cycle_state_current"], workspace)
    )
    result = build_valuation_range(
        monthly, scenarios, midcycle_report, cycle_state, config
    )
    repeated = build_valuation_range(
        monthly, scenarios, midcycle_report, cycle_state, config
    )
    deterministic = (
        stable_frame_hash(result.valuation_matrix)
        == stable_frame_hash(repeated.valuation_matrix)
        and stable_frame_hash(result.implied_assumptions)
        == stable_frame_hash(repeated.implied_assumptions)
        and result.snapshot == repeated.snapshot
    )
    report = build_valuation_range_report(
        result.valuation_matrix,
        result.implied_assumptions,
        result.snapshot,
        result.diagnostics,
        config,
        deterministic=deterministic,
    )
    for output, frame in [
        ("valuation_matrix", result.valuation_matrix),
        ("implied_assumptions", result.implied_assumptions),
    ]:
        path = resolve_repo_path(config["outputs"][output], workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
        frame.to_parquet(temporary, index=False)
        temporary.replace(path)
    _write_json(
        result.snapshot,
        resolve_repo_path(config["outputs"]["current_snapshot"], workspace),
    )
    write_valuation_range_report(
        report,
        resolve_repo_path(config["outputs"]["report_markdown"], workspace),
        resolve_repo_path(config["outputs"]["report_json"], workspace),
    )
    manifest = {
        "valuation_id": config["valuation_id"],
        "version": str(config["version"]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_as_of": str(config["analysis_as_of"]),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "inputs": config["inputs"],
        "outputs": {
            name: {
                "path": config["outputs"][name],
                "rows": len(frame),
                "content_hash": stable_frame_hash(frame),
            }
            for name, frame in [
                ("valuation_matrix", result.valuation_matrix),
                ("implied_assumptions", result.implied_assumptions),
            ]
        },
        "diagnostics": result.diagnostics,
        "deterministic_repeat": deterministic,
        "status": report["status"],
    }
    _write_json(manifest, resolve_repo_path(config["outputs"]["manifest"], workspace))
    print(
        f"base_range={result.snapshot['base_per_share_low_usd']:.0f}-"
        f"{result.snapshot['base_per_share_high_usd']:.0f} "
        f"base_median={result.snapshot['base_per_share_median_usd']:.0f} "
        f"status={report['status']}"
    )
    return 0 if report["status"] == "PASS" else 1


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
