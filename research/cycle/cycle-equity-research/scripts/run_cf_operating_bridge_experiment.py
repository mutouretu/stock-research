#!/usr/bin/env python3
"""Run the leakage-safe CF quarterly operating-bridge baseline experiment."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from research_data_core.paths import find_stock_research_root, resolve_repo_path

from cycle_equity_research.experiments.operating_bridge import (
    run_operating_bridge_experiment,
)
from cycle_equity_research.experiments.report import (
    build_experiment_report,
    write_experiment_report,
)
from cycle_equity_research.quality.audit import stable_frame_hash


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workspace = find_stock_research_root(PROJECT_ROOT)
    config_path = PROJECT_ROOT / "configs/experiments/cf_operating_bridge_v1.yaml"
    config = _yaml(config_path)
    quarterly = pd.read_parquet(
        resolve_repo_path(config["inputs"]["quarterly_panel"], workspace)
    )
    nitrogen = pd.read_parquet(
        resolve_repo_path(config["inputs"]["quarterly_nitrogen"], workspace)
    )
    result = run_operating_bridge_experiment(quarterly, nitrogen, config)
    repeated = run_operating_bridge_experiment(quarterly, nitrogen, config)
    deterministic = (
        stable_frame_hash(result.predictions) == stable_frame_hash(repeated.predictions)
        and stable_frame_hash(result.metrics) == stable_frame_hash(repeated.metrics)
    )
    report = build_experiment_report(
        result.predictions,
        result.metrics,
        result.final_parameters,
        config,
        deterministic=deterministic,
    )

    prediction_path = resolve_repo_path(config["outputs"]["predictions"], workspace)
    metrics_path = resolve_repo_path(config["outputs"]["metrics"], workspace)
    _write_parquet(result.predictions, prediction_path)
    _write_parquet(result.metrics, metrics_path)
    markdown_path = resolve_repo_path(config["outputs"]["report_markdown"], workspace)
    json_path = resolve_repo_path(config["outputs"]["report_json"], workspace)
    write_experiment_report(report, markdown_path, json_path)

    manifest = {
        "experiment_id": config["experiment_id"],
        "version": str(config["version"]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "inputs": config["inputs"],
        "outputs": {
            "predictions": {
                "path": config["outputs"]["predictions"],
                "rows": len(result.predictions),
                "content_hash": stable_frame_hash(result.predictions),
            },
            "metrics": {
                "path": config["outputs"]["metrics"],
                "rows": len(result.metrics),
                "content_hash": stable_frame_hash(result.metrics),
            },
        },
        "prediction_contract": report["comparison_contract"],
        "status": report["status"],
    }
    _write_json(manifest, resolve_repo_path(config["outputs"]["manifest"], workspace))
    print(
        f"periods={report['prediction_periods']} predictions={len(result.predictions)} "
        f"metrics={len(result.metrics)} pit_violations={report['point_in_time_violations']} "
        f"status={report['status']}"
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
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
