#!/usr/bin/env python3
"""Build the M5.2 CF mid-cycle EBITDA scenario bridge."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from research_data_core.paths import find_stock_research_root, resolve_repo_path

from cycle_equity_research.quality.audit import stable_frame_hash
from cycle_equity_research.valuation.midcycle import (
    build_midcycle_ebitda_scenarios,
    scenario_sensitivities,
)
from cycle_equity_research.valuation.midcycle_report import (
    build_midcycle_report,
    write_midcycle_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workspace = find_stock_research_root(PROJECT_ROOT)
    config_path = PROJECT_ROOT / "configs/valuation/cf_midcycle_ebitda_v1.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    quarterly = pd.read_parquet(
        resolve_repo_path(config["inputs"]["quarterly_panel"], workspace)
    )
    nitrogen = pd.read_parquet(
        resolve_repo_path(config["inputs"]["quarterly_nitrogen"], workspace)
    )
    bridge_report = json.loads(
        resolve_repo_path(config["inputs"]["operating_bridge_report"], workspace).read_text(
            encoding="utf-8"
        )
    )
    result = build_midcycle_ebitda_scenarios(quarterly, nitrogen, bridge_report, config)
    repeated = build_midcycle_ebitda_scenarios(quarterly, nitrogen, bridge_report, config)
    deterministic = (
        stable_frame_hash(result.scenarios) == stable_frame_hash(repeated.scenarios)
        and stable_frame_hash(result.product_bridge)
        == stable_frame_hash(repeated.product_bridge)
    )
    sensitivities = scenario_sensitivities(result, bridge_report, config)
    report = build_midcycle_report(
        result.scenarios,
        result.product_bridge,
        result.calibration,
        result.diagnostics,
        sensitivities,
        config,
        deterministic=deterministic,
    )
    for output, frame in [
        ("scenarios", result.scenarios),
        ("product_bridge", result.product_bridge),
    ]:
        path = resolve_repo_path(config["outputs"][output], workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
        frame.to_parquet(temporary, index=False)
        temporary.replace(path)
    write_midcycle_report(
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
                ("scenarios", result.scenarios),
                ("product_bridge", result.product_bridge),
            ]
        },
        "diagnostics": result.diagnostics,
        "deterministic_repeat": deterministic,
        "status": report["status"],
    }
    _write_json(manifest, resolve_repo_path(config["outputs"]["manifest"], workspace))
    values = result.scenarios.set_index("scenario")["scenario_ebitda_usd_million"]
    print(
        f"downside={values['downside']:.0f} base={values['base']:.0f} "
        f"upside={values['upside']:.0f} deterministic={deterministic} "
        f"status={report['status']}"
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
