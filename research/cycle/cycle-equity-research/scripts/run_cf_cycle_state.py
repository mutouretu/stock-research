#!/usr/bin/env python3
"""Run the M4.3 rule-based CF operating-cycle state machine."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from research_data_core.paths import find_stock_research_root, resolve_repo_path

from cycle_equity_research.analysis.cycle_state import (
    build_cycle_states,
    point_in_time_violations,
)
from cycle_equity_research.analysis.cycle_state_report import (
    build_cycle_state_report,
    write_cycle_state_report,
)
from cycle_equity_research.quality.audit import stable_frame_hash


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workspace = find_stock_research_root(PROJECT_ROOT)
    config_path = PROJECT_ROOT / "configs/experiments/cf_cycle_state_v1.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    input_path = resolve_repo_path(config["inputs"]["core_monthly"], workspace)
    monthly_input = pd.read_parquet(input_path)
    stability_report = json.loads(
        resolve_repo_path(config["inputs"]["stability_report"], workspace).read_text(
            encoding="utf-8"
        )
    )
    result = build_cycle_states(monthly_input, config)
    repeated = build_cycle_states(monthly_input, config)
    deterministic = (
        stable_frame_hash(result.monthly) == stable_frame_hash(repeated.monthly)
        and stable_frame_hash(result.episodes) == stable_frame_hash(repeated.episodes)
    )
    pit_violations = point_in_time_violations(
        monthly_input.loc[
            pd.to_datetime(monthly_input["month_end"])
            <= pd.Timestamp(config["analysis_end_date"])
        ],
        config,
    )
    validation_decisions = [
        decision
        for decision in stability_report["decisions"]
        if decision["decision"] == "ACCEPT_CORE_VALIDATION"
    ]
    report = build_cycle_state_report(
        result.monthly,
        result.episodes,
        config,
        deterministic=deterministic,
        point_in_time_violations=pit_violations,
        validation_decisions=validation_decisions,
    )

    monthly_path = resolve_repo_path(config["outputs"]["monthly_states"], workspace)
    monthly_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = monthly_path.with_name(f"{monthly_path.stem}.tmp{monthly_path.suffix}")
    result.monthly.to_parquet(temporary, index=False)
    temporary.replace(monthly_path)
    _write_json(report["current"], resolve_repo_path(config["outputs"]["current_snapshot"], workspace))
    write_cycle_state_report(
        report,
        resolve_repo_path(config["outputs"]["report_markdown"], workspace),
        resolve_repo_path(config["outputs"]["report_json"], workspace),
    )
    manifest = {
        "analysis_id": config["analysis_id"],
        "version": str(config["version"]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_end_date": str(config["analysis_end_date"]),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "inputs": config["inputs"],
        "outputs": {
            "monthly_states": {
                "path": config["outputs"]["monthly_states"],
                "rows": len(result.monthly),
                "content_hash": stable_frame_hash(result.monthly),
            },
            "current_snapshot": {"path": config["outputs"]["current_snapshot"]},
        },
        "point_in_time_violations": pit_violations,
        "deterministic_repeat": deterministic,
        "status": report["status"],
    }
    _write_json(manifest, resolve_repo_path(config["outputs"]["manifest"], workspace))
    print(
        f"months={len(result.monthly)} episodes={len(result.episodes)} "
        f"current={report['current']['state']} "
        f"overlay={report['current']['confirmation_overlay']} "
        f"deterministic={deterministic} status={report['status']}"
    )
    return 0 if report["status"] == "PASS" else 1


def _write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
