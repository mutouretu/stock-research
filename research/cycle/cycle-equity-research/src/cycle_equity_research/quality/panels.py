"""Quality checks for point-in-time research panels."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def assess_panel(frame: pd.DataFrame, spec: dict) -> dict:
    time_col = str(spec["time_col"])
    available_col = str(spec["available_time_col"])
    key_columns = list(spec["key_columns"])
    issues: list[dict] = []
    required = list(spec.get("required_columns") or [])
    missing_columns = [column for column in required if column not in frame.columns]
    if missing_columns:
        issues.append({"severity": "ERROR", "message": f"missing columns: {missing_columns}"})
    duplicates = int(frame.duplicated(key_columns).sum())
    if duplicates:
        issues.append({"severity": "ERROR", "message": f"duplicate keys: {duplicates}"})
    if len(frame) < int(spec.get("min_rows", 1)):
        issues.append({"severity": "ERROR", "message": f"row count below minimum: {len(frame)}"})

    cutoff = pd.to_datetime(frame[available_col], errors="coerce")
    pit_violations = 0
    for column in frame.columns:
        if column.endswith("__available_time"):
            source_time = pd.to_datetime(frame[column], errors="coerce")
            pit_violations += int((source_time > cutoff).sum())
    if pit_violations:
        issues.append(
            {"severity": "ERROR", "message": f"point-in-time violations: {pit_violations}"}
        )

    max_missing = float(spec.get("max_required_missing_pct", 0.05))
    missing_rates = {
        column: float(frame[column].isna().mean())
        for column in required
        if column in frame.columns
    }
    excessive = {column: rate for column, rate in missing_rates.items() if rate > max_missing}
    if excessive:
        issues.append({"severity": "WARNING", "message": f"required-field missing rates: {excessive}"})
    dates = pd.to_datetime(frame[time_col], errors="coerce")
    latest = frame.loc[dates.idxmax()]
    latest_missing = [
        column
        for column in spec.get("latest_required_columns", [])
        if column not in frame.columns or pd.isna(latest.get(column))
    ]
    if latest_missing:
        issues.append(
            {"severity": "WARNING", "message": f"latest row missing fields: {latest_missing}"}
        )
    stale_sources: dict[str, int] = {}
    for column, limit in (spec.get("max_source_age_days") or {}).items():
        if column not in frame.columns or pd.isna(latest.get(column)):
            continue
        age = (pd.Timestamp(latest[available_col]) - pd.Timestamp(latest[column])).days
        if age > int(limit):
            stale_sources[column] = age
    if stale_sources:
        issues.append(
            {"severity": "WARNING", "message": f"latest source ages exceed limits: {stale_sources}"}
        )
    severity = "ERROR" if any(item["severity"] == "ERROR" for item in issues) else (
        "WARNING" if issues else "PASS"
    )
    return {
        "panel_id": spec["panel_id"],
        "status": severity,
        "rows": len(frame),
        "columns": len(frame.columns),
        "first_date": dates.min().date().isoformat(),
        "last_date": dates.max().date().isoformat(),
        "duplicate_keys": duplicates,
        "point_in_time_violations": pit_violations,
        "missing_rates": missing_rates,
        "issues": issues,
    }


def write_panel_quality_report(results: list[dict], markdown_path: Path, json_path: Path) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    errors = sum(result["status"] == "ERROR" for result in results)
    warnings = sum(result["status"] == "WARNING" for result in results)
    lines = [
        "# CF Milestone 2 面板质量报告",
        "",
        f"- ERROR：{errors}",
        f"- WARNING：{warnings}",
        "",
        "| Panel | 状态 | 行数 | 列数 | 起始日期 | 最新日期 | PIT 违规 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| `{result['panel_id']}` | {result['status']} | {result['rows']} | "
            f"{result['columns']} | {result['first_date']} | {result['last_date']} | "
            f"{result['point_in_time_violations']} |"
        )
    for result in results:
        lines.extend(["", f"## {result['panel_id']}", ""])
        if result["issues"]:
            lines.extend(
                f"- {issue['severity']}：{issue['message']}" for issue in result["issues"]
            )
        else:
            lines.append("- 未发现质量问题。")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {"error_count": errors, "warning_count": warnings, "panels": results}
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
