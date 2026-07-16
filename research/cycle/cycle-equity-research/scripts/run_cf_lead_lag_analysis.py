#!/usr/bin/env python3
"""Run the M4.1 CF lead/lag analysis with fixed timing conventions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from research_data_core.paths import find_stock_research_root, resolve_repo_path

from cycle_equity_research.analysis.lead_lag import run_lead_lag_analysis
from cycle_equity_research.analysis.report import (
    build_lead_lag_report,
    write_lead_lag_report,
)
from cycle_equity_research.quality.audit import stable_frame_hash


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workspace = find_stock_research_root(PROJECT_ROOT)
    config_path = PROJECT_ROOT / "configs/experiments/cf_lead_lag_v1.yaml"
    config = _yaml(config_path)
    inputs = {
        name: pd.read_parquet(resolve_repo_path(path, workspace))
        for name, path in config["inputs"].items()
    }
    frames = _prepare_frames(inputs)
    result = run_lead_lag_analysis(frames, config)
    repeated = run_lead_lag_analysis(frames, config)
    deterministic = (
        stable_frame_hash(result.lag_grid) == stable_frame_hash(repeated.lag_grid)
        and stable_frame_hash(result.best_lags)
        == stable_frame_hash(repeated.best_lags)
    )
    report = build_lead_lag_report(
        result.lag_grid, result.best_lags, config, deterministic=deterministic
    )

    lag_grid_path = resolve_repo_path(config["outputs"]["lag_grid"], workspace)
    best_lags_path = resolve_repo_path(config["outputs"]["best_lags"], workspace)
    _write_parquet(result.lag_grid, lag_grid_path)
    _write_parquet(result.best_lags, best_lags_path)
    write_lead_lag_report(
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
            "lag_grid": {
                "path": config["outputs"]["lag_grid"],
                "rows": len(result.lag_grid),
                "content_hash": stable_frame_hash(result.lag_grid),
            },
            "best_lags": {
                "path": config["outputs"]["best_lags"],
                "rows": len(result.best_lags),
                "content_hash": stable_frame_hash(result.best_lags),
            },
        },
        "lag_convention": report["lag_convention"],
        "point_in_time_violations": report["point_in_time_violations"],
        "deterministic_repeat": deterministic,
        "status": report["status"],
    }
    _write_json(
        manifest, resolve_repo_path(config["outputs"]["manifest"], workspace)
    )
    print(
        f"relationships={report['relationship_count']} grid_rows={len(result.lag_grid)} "
        f"pit_violations={report['point_in_time_violations']} "
        f"deterministic={deterministic} status={report['status']}"
    )
    return 0 if report["status"] == "PASS" else 1


def _prepare_frames(inputs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    keys = ["instrument", "period_end", "panel_available_time"]
    market_columns = [
        *keys,
        "world_bank_urea_quarter_mean",
        "henry_hub_quarter_mean",
        "corn_quarter_mean",
    ]
    product_price_columns = [
        *keys,
        "cf_ammonia_realized_price",
        "cf_granular_urea_realized_price",
        "cf_uan_realized_price",
        "cf_ammonium_nitrate_realized_price",
    ]
    quarterly = inputs["core_quarterly"].merge(
        inputs["quarterly_panel"][market_columns],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    quarterly = quarterly.merge(
        inputs["quarterly_nitrogen"][product_price_columns],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    return {
        "monthly": inputs["core_monthly"].copy(),
        "quarterly": quarterly,
    }


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
