#!/usr/bin/env python3
"""Build compact CF core panels and a separate tactical context panel."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from research_data_core.paths import find_stock_research_root, resolve_repo_path

from cycle_equity_research.panels.curation import (
    build_core_monthly_panel,
    build_core_quarterly_panel,
    build_tactical_context_panel,
)
from cycle_equity_research.quality.audit import stable_frame_hash
from cycle_equity_research.quality.curated import (
    assess_curated_panels,
    write_curated_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workspace = find_stock_research_root(PROJECT_ROOT)
    config_path = PROJECT_ROOT / "configs/panels/cf_curated.yaml"
    registry_path = PROJECT_ROOT / "configs/features/cf_feature_registry.yaml"
    roles_path = PROJECT_ROOT / "configs/quality/cf_data_roles.yaml"
    config = _yaml(config_path)
    registry = _yaml(registry_path)
    roles = _yaml(roles_path)
    inputs = {
        name: pd.read_parquet(resolve_repo_path(path, workspace))
        for name, path in config["inputs"].items()
    }

    monthly, quarterly, tactical = _build(inputs, config)
    repeat_monthly, repeat_quarterly, repeat_tactical = _build(inputs, config)
    frames = {
        "core_monthly": monthly,
        "core_quarterly": quarterly,
        "tactical_context": tactical,
    }
    repeats = {
        "core_monthly": repeat_monthly,
        "core_quarterly": repeat_quarterly,
        "tactical_context": repeat_tactical,
    }
    hashes = {name: stable_frame_hash(frame) for name, frame in frames.items()}
    deterministic = {
        name: hashes[name] == stable_frame_hash(repeats[name]) for name in frames
    }
    report = assess_curated_panels(
        monthly,
        quarterly,
        tactical,
        config,
        registry,
        roles,
        deterministic=deterministic,
    )

    output_paths = {
        name: resolve_repo_path(config["outputs"][name], workspace) for name in frames
    }
    for name, frame in frames.items():
        _write_parquet(frame, output_paths[name])
    report_dir = PROJECT_ROOT / "reports/model_readiness"
    write_curated_report(
        report,
        report_dir / "cf_model_readiness.md",
        report_dir / "cf_model_readiness.json",
    )

    lineage = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "panel_group_id": config["panel_group_id"],
        "configs": {
            str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (config_path, registry_path, roles_path)
        },
        "inputs": config["inputs"],
        "outputs": {
            name: {
                "path": config["outputs"][name],
                "rows": len(frame),
                "columns": list(frame.columns),
                "content_hash": hashes[name],
            }
            for name, frame in frames.items()
        },
        "model_features": report["selection"],
        "quality_status": report["status"],
    }
    lineage_path = resolve_repo_path(config["outputs"]["lineage"], workspace)
    _write_json(lineage, lineage_path)
    print(
        f"monthly={len(monthly)} quarterly={len(quarterly)} tactical={len(tactical)} "
        f"status={report['status']} errors={len(report['errors'])} "
        f"warnings={len(report['warnings'])}"
    )
    return 1 if report["status"] == "ERROR" else 0


def _build(inputs: dict[str, pd.DataFrame], config: dict) -> tuple[pd.DataFrame, ...]:
    monthly = build_core_monthly_panel(
        inputs["daily_panel"],
        inputs["daily_nitrogen"],
        inputs["quarterly_panel"],
        inputs["quarterly_nitrogen"],
        config,
    )
    quarterly = build_core_quarterly_panel(
        inputs["quarterly_panel"], inputs["quarterly_nitrogen"], config
    )
    tactical = build_tactical_context_panel(
        inputs["daily_panel"],
        inputs["daily_nitrogen"],
        inputs["quarterly_nitrogen"],
        config,
    )
    return monthly, quarterly, tactical


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
