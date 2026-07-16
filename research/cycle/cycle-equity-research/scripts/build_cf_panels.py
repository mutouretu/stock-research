#!/usr/bin/env python3
"""Build CF daily and quarterly research panels with quality and lineage artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from research_data_core.paths import find_stock_research_root, resolve_repo_path

from cycle_equity_research.panels import (
    attach_quarterly_features,
    build_daily_panel,
    build_quarterly_panel,
)
from cycle_equity_research.quality.panels import assess_panel, write_panel_quality_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workspace = find_stock_research_root(PROJECT_ROOT)
    dataset_dir = PROJECT_ROOT / "configs/datasets"
    daily_config = PROJECT_ROOT / "configs/panels/cf_daily.yaml"
    quarterly_config = PROJECT_ROOT / "configs/panels/cf_quarterly.yaml"
    quality_config = PROJECT_ROOT / "configs/quality/cf_m2.yaml"
    daily_spec = _yaml(daily_config)
    quarterly_spec = _yaml(quarterly_config)
    quarterly = build_quarterly_panel(quarterly_config, dataset_dir, root=workspace)
    daily = build_daily_panel(daily_config, dataset_dir, root=workspace)
    daily = attach_quarterly_features(
        daily, quarterly, list(daily_spec.get("quarterly_features") or [])
    )
    outputs = [
        (daily, resolve_repo_path(daily_spec["output"], workspace)),
        (quarterly, resolve_repo_path(quarterly_spec["output"], workspace)),
    ]
    for frame, path in outputs:
        _write_parquet(frame, path)

    quality = _yaml(quality_config)
    results = [
        assess_panel(daily, quality["panels"][0]),
        assess_panel(quarterly, quality["panels"][1]),
    ]
    report_dir = PROJECT_ROOT / "reports/panel_quality"
    write_panel_quality_report(
        results, report_dir / "cf_panel_quality.md", report_dir / "cf_panel_quality.json"
    )
    lineage = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "panels": [
            _lineage(daily_spec, daily_config, outputs[0][1], daily),
            _lineage(quarterly_spec, quarterly_config, outputs[1][1], quarterly),
        ],
    }
    lineage_path = outputs[0][1].parent / "panel_lineage.json"
    lineage_path.write_text(json.dumps(lineage, indent=2) + "\n", encoding="utf-8")
    print(
        f"daily={len(daily)} quarterly={len(quarterly)} "
        f"errors={sum(item['status'] == 'ERROR' for item in results)}"
    )
    return 1 if any(item["status"] == "ERROR" for item in results) else 0


def _lineage(spec: dict, config_path: Path, output_path: Path, frame) -> dict:
    content = config_path.read_bytes()
    inputs = [spec["base"]["dataset_id"]]
    inputs.extend(item["dataset_id"] for item in spec.get("inputs", []))
    inputs.extend(item["dataset_id"] for item in spec.get("market_inputs", []))
    if spec.get("financials"):
        inputs.append(spec["financials"]["dataset_id"])
    return {
        "panel_id": spec["panel_id"],
        "config": str(config_path.relative_to(PROJECT_ROOT)),
        "config_sha256": hashlib.sha256(content).hexdigest(),
        "input_datasets": sorted(set(inputs)),
        "output": str(output_path),
        "rows": len(frame),
        "columns": list(frame.columns),
    }


def _write_parquet(frame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
