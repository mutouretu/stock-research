#!/usr/bin/env python3
"""Run the M4.2 fixed-lag rolling and regime stability analysis."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from research_data_core.paths import find_stock_research_root, resolve_repo_path

from cycle_equity_research.analysis.frames import prepare_lead_lag_frames
from cycle_equity_research.analysis.stability import run_stability_analysis
from cycle_equity_research.analysis.stability_report import (
    build_stability_report,
    write_stability_report,
)
from cycle_equity_research.quality.audit import stable_frame_hash


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workspace = find_stock_research_root(PROJECT_ROOT)
    config_path = PROJECT_ROOT / "configs/experiments/cf_lead_lag_stability_v1.yaml"
    config = _yaml(config_path)
    lead_lag_config = _yaml(
        resolve_repo_path(config["inputs"]["lead_lag_config"], workspace)
    )
    lead_lag_report = _json(
        resolve_repo_path(config["inputs"]["lead_lag_report"], workspace)
    )
    panel_names = [
        "core_monthly",
        "core_quarterly",
        "quarterly_panel",
        "quarterly_nitrogen",
    ]
    panel_inputs = {
        name: pd.read_parquet(
            resolve_repo_path(config["inputs"][name], workspace)
        )
        for name in panel_names
    }
    frames = prepare_lead_lag_frames(panel_inputs)
    best_lags = pd.DataFrame(lead_lag_report["best_lags"])
    result = run_stability_analysis(
        frames, lead_lag_config, best_lags, config
    )
    repeated = run_stability_analysis(
        frames, lead_lag_config, best_lags, config
    )
    deterministic = all(
        stable_frame_hash(left) == stable_frame_hash(right)
        for left, right in [
            (result.rolling_windows, repeated.rolling_windows),
            (result.slices, repeated.slices),
            (result.decisions, repeated.decisions),
        ]
    )
    report = build_stability_report(
        result.rolling_windows,
        result.slices,
        result.decisions,
        config,
        deterministic=deterministic,
    )

    for output_name, frame in [
        ("rolling_windows", result.rolling_windows),
        ("slices", result.slices),
        ("decisions", result.decisions),
    ]:
        _write_parquet(
            frame,
            resolve_repo_path(config["outputs"][output_name], workspace),
        )
    write_stability_report(
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
        "fixed_lag_source": lead_lag_report["analysis_id"],
        "outputs": {
            name: {
                "path": config["outputs"][name],
                "rows": len(frame),
                "content_hash": stable_frame_hash(frame),
            }
            for name, frame in [
                ("rolling_windows", result.rolling_windows),
                ("slices", result.slices),
                ("decisions", result.decisions),
            ]
        },
        "deterministic_repeat": deterministic,
        "status": report["status"],
    }
    _write_json(
        manifest, resolve_repo_path(config["outputs"]["manifest"], workspace)
    )
    print(
        f"relationships={report['relationship_count']} "
        f"rolling_rows={len(result.rolling_windows)} slices={len(result.slices)} "
        f"deterministic={deterministic} status={report['status']}"
    )
    return 0 if report["status"] == "PASS" else 1


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
