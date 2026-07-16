"""Model-readiness checks for compact CF research panels."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def assess_curated_panels(
    monthly: pd.DataFrame,
    quarterly: pd.DataFrame,
    tactical: pd.DataFrame,
    config: dict,
    registry: dict,
    data_roles: dict,
    *,
    deterministic: dict[str, bool] | None = None,
) -> dict:
    """Assess selection, sample size, freshness, PIT safety and redundancy."""
    errors: list[str] = []
    warnings: list[str] = []
    quality = config["quality"]
    monthly_features = list(config["monthly_model_features"])
    quarterly_features = list(config["quarterly_model_features"])

    panels = {
        "core_monthly": _panel_metrics(
            monthly,
            key=["instrument", "month_end"],
            features=monthly_features,
            min_rows=int(quality["monthly_min_rows"]),
            min_complete_rows=int(quality["monthly_min_complete_rows"]),
            max_features=int(quality["monthly_max_features"]),
            max_missing=float(quality["maximum_missing_rate"]),
            max_correlation=float(quality["maximum_pairwise_correlation"]),
        ),
        "core_quarterly": _panel_metrics(
            quarterly,
            key=["instrument", "period_end"],
            features=quarterly_features,
            min_rows=int(quality["quarterly_min_rows"]),
            min_complete_rows=int(quality["quarterly_min_complete_rows"]),
            max_features=int(quality["quarterly_max_features"]),
            max_missing=float(quality["maximum_missing_rate"]),
            max_correlation=float(quality["maximum_pairwise_correlation"]),
        ),
        "tactical_context": {
            "rows": len(tactical),
            "columns": len(tactical.columns),
            "duplicate_keys": int(tactical.duplicated(["instrument", "trade_date"]).sum()),
        },
    }

    for name, metrics in panels.items():
        if metrics["duplicate_keys"]:
            errors.append(f"{name} has {metrics['duplicate_keys']} duplicate keys")
    for name in ("core_monthly", "core_quarterly"):
        metrics = panels[name]
        if metrics["missing_features"]:
            errors.append(f"{name} missing model features: {metrics['missing_features']}")
        if metrics["rows"] < metrics["minimum_rows"]:
            errors.append(f"{name} row count below minimum: {metrics['rows']}")
        if metrics["complete_rows"] < metrics["minimum_complete_rows"]:
            errors.append(
                f"{name} complete rows below minimum: {metrics['complete_rows']}"
            )
        if metrics["feature_count"] > metrics["maximum_features"]:
            errors.append(f"{name} carries too many model features: {metrics['feature_count']}")
        if metrics["excessive_missing_rates"]:
            warnings.append(
                f"{name} feature missing rates exceed limit: "
                f"{metrics['excessive_missing_rates']}"
            )
        if metrics["high_correlations"]:
            warnings.append(
                f"{name} economically distinct features exceed correlation limit; "
                "do not use together without selection or regularization: "
                f"{metrics['high_correlations']}"
            )

    _check_registry(
        registry,
        data_roles,
        monthly_features,
        quarterly_features,
        errors,
    )
    _check_monthly_freshness(monthly, config["freshness_days"], errors)
    _check_point_in_time(monthly, "month_end", errors)
    _check_point_in_time(quarterly, "panel_available_time", errors)
    _check_point_in_time(tactical, "trade_date", errors)

    tactical_registry = {
        item["name"]
        for item in registry["features"]
        if item["panel"] == "tactical_context"
    }
    leaked = sorted((set(monthly_features) | set(quarterly_features)) & tactical_registry)
    if leaked:
        errors.append(f"tactical/context features leaked into core model inputs: {leaked}")

    deterministic = deterministic or {}
    failed_determinism = sorted(name for name, passed in deterministic.items() if not passed)
    if failed_determinism:
        errors.append(f"non-deterministic panel builds: {failed_determinism}")

    status = "ERROR" if errors else ("WARNING" if warnings else "PASS")
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "panels": panels,
        "selection": {
            "monthly_model_features": monthly_features,
            "quarterly_model_features": quarterly_features,
            "tactical_registry_features": sorted(tactical_registry),
        },
        "determinism": deterministic,
    }


def write_curated_report(report: dict, markdown_path: Path, json_path: Path) -> None:
    """Write the compact human report and full machine-readable evidence."""
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CF M2.1 模型就绪数据报告",
        "",
        f"- 状态：**{report['status']}**",
        f"- ERROR：{len(report['errors'])}",
        f"- WARNING：{len(report['warnings'])}",
        "",
        "| 面板 | 行数 | 核心特征 | 完整样本 | 样本/特征 | 建议用途 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name in ("core_monthly", "core_quarterly"):
        item = report["panels"][name]
        lines.append(
            f"| `{name}` | {item['rows']} | {item['feature_count']} | "
            f"{item['complete_rows']} | {item['complete_rows_per_feature']:.1f} | "
            f"{item['recommended_use']} |"
        )
    tactical = report["panels"]["tactical_context"]
    lines.append(
        f"| `tactical_context` | {tactical['rows']} | 0 | — | — | 场景确认与微观诊断，不进基础模型 |"
    )

    lines.extend(["", "## 核心特征", "", "### 月频", ""])
    lines.extend(f"- `{feature}`" for feature in report["selection"]["monthly_model_features"])
    lines.extend(["", "### 季度", ""])
    lines.extend(f"- `{feature}`" for feature in report["selection"]["quarterly_model_features"])

    lines.extend(["", "## 质量结论", ""])
    if report["errors"]:
        lines.extend(f"- ERROR：{message}" for message in report["errors"])
    if report["warnings"]:
        lines.extend(f"- WARNING：{message}" for message in report["warnings"])
    if not report["errors"] and not report["warnings"]:
        lines.append("- 未发现质量问题。")
    lines.extend(
        [
            "",
            "季度完整样本有限，默认只用于描述分析、关系校准和低自由度估计；复杂时间序列模型仍需在 M7 单独证明增量价值。",
            "战术面板中的 AMS、种植面积和产品成本残差不进入基础训练矩阵。",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _panel_metrics(
    frame: pd.DataFrame,
    *,
    key: list[str],
    features: list[str],
    min_rows: int,
    min_complete_rows: int,
    max_features: int,
    max_missing: float,
    max_correlation: float,
) -> dict:
    missing_features = [feature for feature in features if feature not in frame.columns]
    present = [feature for feature in features if feature in frame.columns]
    missing_rates = {feature: float(frame[feature].isna().mean()) for feature in present}
    complete_rows = int(frame[present].notna().all(axis=1).sum()) if present else 0
    correlations = frame[present].corr().abs() if present else pd.DataFrame()
    high_correlations: list[dict] = []
    for left_index, left in enumerate(present):
        for right in present[left_index + 1 :]:
            value = correlations.loc[left, right]
            if pd.notna(value) and float(value) > max_correlation:
                high_correlations.append(
                    {"left": left, "right": right, "absolute_correlation": float(value)}
                )
    ratio = complete_rows / len(features) if features else 0.0
    if ratio >= 20:
        recommended_use = "简洁统计/低自由度模型"
    elif ratio >= 10:
        recommended_use = "探索性估计，需正则化和稳健性检验"
    else:
        recommended_use = "描述分析/关系校准，不宜独立训练复杂模型"
    return {
        "rows": len(frame),
        "columns": len(frame.columns),
        "feature_count": len(features),
        "missing_features": missing_features,
        "missing_rates": missing_rates,
        "excessive_missing_rates": {
            feature: rate for feature, rate in missing_rates.items() if rate > max_missing
        },
        "complete_rows": complete_rows,
        "complete_rows_per_feature": ratio,
        "recommended_use": recommended_use,
        "duplicate_keys": int(frame.duplicated(key).sum()),
        "minimum_rows": min_rows,
        "minimum_complete_rows": min_complete_rows,
        "maximum_features": max_features,
        "high_correlations": high_correlations,
    }


def _check_registry(
    registry: dict,
    data_roles: dict,
    monthly_features: list[str],
    quarterly_features: list[str],
    errors: list[str],
) -> None:
    entries = registry.get("features") or []
    names = [item["name"] for item in entries]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        errors.append(f"duplicate feature registry entries: {duplicates}")
    expected = set(monthly_features) | set(quarterly_features)
    registered_model = {item["name"] for item in entries if item.get("model_use")}
    if expected != registered_model:
        errors.append(
            "configured and registered model features differ: "
            f"configured_only={sorted(expected - registered_model)}, "
            f"registry_only={sorted(registered_model - expected)}"
        )
    roles = data_roles.get("datasets") or {}
    for item in entries:
        if not item.get("model_use"):
            continue
        if item.get("tier") != "core":
            errors.append(f"model feature is not core tier: {item['name']}")
        source_role = roles.get(item.get("source"), {})
        if not source_role:
            errors.append(
                f"model feature {item['name']} uses unclassified source {item.get('source')}"
            )
        if source_role.get("tier") in {"tactical", "contextual"}:
            errors.append(
                f"model feature {item['name']} uses non-core source {item.get('source')}"
            )


def _check_monthly_freshness(
    monthly: pd.DataFrame, freshness: dict, errors: list[str]
) -> None:
    rules = [
        ("henry_hub_month_mean", "henry_hub_source_age_days", "henry_hub"),
        (
            "global_urea_gas_spread_month_mean",
            "world_bank_urea_source_age_days",
            "world_bank_urea",
        ),
        ("corn_month_mean", "corn_source_age_days", "corn_futures"),
    ]
    for feature, age_column, limit_key in rules:
        if feature not in monthly or age_column not in monthly:
            errors.append(f"missing freshness evidence for {feature}: {age_column}")
            continue
        violations = int(
            (monthly[feature].notna() & (monthly[age_column] > int(freshness[limit_key]))).sum()
        )
        if violations:
            errors.append(f"{feature} has {violations} stale non-null observations")


def _check_point_in_time(frame: pd.DataFrame, cutoff_column: str, errors: list[str]) -> None:
    if cutoff_column not in frame:
        errors.append(f"missing point-in-time cutoff column: {cutoff_column}")
        return
    cutoff = pd.to_datetime(frame[cutoff_column], errors="coerce")
    violations = 0
    for column in frame.columns:
        if column.endswith("available_time") and column != "panel_available_time":
            available = pd.to_datetime(frame[column], errors="coerce")
            violations += int((available > cutoff).sum())
    if violations:
        errors.append(f"{cutoff_column} point-in-time violations: {violations}")
