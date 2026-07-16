"""Validation and reporting for CF nitrogen-economics proxies."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def validate_nitrogen_features(
    daily: pd.DataFrame,
    quarterly: pd.DataFrame,
    quarterly_panel: pd.DataFrame,
    config: dict,
) -> dict:
    errors: list[str] = []
    ordering_violations = 0
    for prefix in config["daily_market_products"]:
        low = daily[f"{prefix}_theoretical_cash_spread_low"]
        base = daily[f"{prefix}_theoretical_cash_spread_base"]
        high = daily[f"{prefix}_theoretical_cash_spread_high"]
        ordering_violations += int((~((low >= base) & (base >= high)) & low.notna()).sum())
    for product in config["quarterly_cf_products"]:
        low = quarterly[f"cf_{product}_realized_gas_spread_low"]
        base = quarterly[f"cf_{product}_realized_gas_spread_base"]
        high = quarterly[f"cf_{product}_realized_gas_spread_high"]
        ordering_violations += int((~((low >= base) & (base >= high)) & low.notna()).sum())
    if ordering_violations:
        errors.append(f"scenario ordering violations: {ordering_violations}")

    product_validation = {}
    for product in config["quarterly_cf_products"]:
        product_validation[product] = _relationship(
            quarterly[f"cf_{product}_realized_gas_spread_base"],
            quarterly[f"cf_{product}_actual_gross_margin_per_ton"],
        )
    market_validation = {
        "ams_urea_spread_vs_cf_urea_gross_margin": _relationship(
            quarterly["ams_urea_theoretical_cash_spread_base_quarter_mean"],
            quarterly["cf_granular_urea_actual_gross_margin_per_ton"],
        ),
        "global_urea_spread_vs_cf_urea_realized_price": _relationship(
            quarterly["global_urea_theoretical_cash_spread_base_quarter_mean"],
            quarterly["cf_granular_urea_realized_price"],
        ),
    }
    combined = quarterly.merge(
        quarterly_panel[["period_end", "cf_gross_margin", "cf_ebitda_proxy"]],
        on="period_end",
        how="left",
    )
    company_validation = {
        "basket_spread_vs_gross_margin": _relationship(
            combined["cf_realized_basket_gas_spread_base"], combined["cf_gross_margin"]
        ),
        "basket_spread_vs_ebitda_proxy": _relationship(
            combined["cf_realized_basket_gas_spread_base"], combined["cf_ebitda_proxy"]
        ),
    }
    thresholds = config["validation_thresholds"]
    for product, metrics in product_validation.items():
        if (metrics["level_correlation"] or -1) < float(
            thresholds["minimum_product_level_correlation"]
        ):
            errors.append(f"{product} level correlation below threshold")
        if (metrics["direction_accuracy"] or -1) < float(
            thresholds["minimum_product_direction_accuracy"]
        ):
            errors.append(f"{product} direction accuracy below threshold")
    for name, metrics in company_validation.items():
        if (metrics["level_correlation"] or -1) < float(
            thresholds["minimum_company_level_correlation"]
        ):
            errors.append(f"{name} level correlation below threshold")
        if (metrics["direction_accuracy"] or -1) < float(
            thresholds["minimum_company_direction_accuracy"]
        ):
            errors.append(f"{name} direction accuracy below threshold")
    return {
        "model_id": config["model_id"],
        "version": str(config["version"]),
        "status": "ERROR" if errors else "PASS",
        "errors": errors,
        "daily_rows": len(daily),
        "quarterly_rows": len(quarterly),
        "scenario_ordering_violations": ordering_violations,
        "product_validation": product_validation,
        "market_validation": market_validation,
        "company_validation": company_validation,
        "calibration": config["calibration"],
        "validation_thresholds": thresholds,
        "sources": config["sources"],
        "limitations": config["limitations"],
    }


def write_nitrogen_report(report: dict, markdown_path: Path, json_path: Path) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CF Milestone 3 氮肥利润代理报告",
        "",
        f"- 模型：`{report['model_id']}` v{report['version']}",
        f"- 状态：{report['status']}",
        f"- 日频：{report['daily_rows']} 行",
        f"- 季度：{report['quarterly_rows']} 行",
        f"- 情景顺序违规：{report['scenario_ordering_violations']}",
        "- 重复构建一致："
        + str(
            all(
                report.get("determinism", {}).get(key, False)
                for key in ("daily_repeat_match", "quarterly_repeat_match")
            )
        ),
        "",
        "## 公式层级",
        "",
        "1. 相对状态：标准化产品价格 ÷ Henry Hub。",
        "2. 理论现金价差：标准化产品价格 − Henry Hub × 情景气耗。",
        "3. CF 实现气价差：CF 实现售价 − CF 实际气价 × 情景气耗 − 已识别变动成本。",
        "",
        "第三层仍不是会计毛利；实现气价差与披露毛利/吨之间的差额作为其他成本、地区基差和时点残差保留。",
        "",
        "## 分产品校准",
        "",
        "| 产品 | 水平相关 | 变化相关 | 方向命中率 | 残差均值 | MAE |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for product, metrics in report["product_validation"].items():
        lines.append(
            f"| {product} | {_fmt(metrics['level_correlation'])} | "
            f"{_fmt(metrics['change_correlation'])} | {_fmt(metrics['direction_accuracy'])} | "
            f"{_fmt(metrics['residual_mean'])} | {_fmt(metrics['mae'])} |"
        )
    lines.extend(["", "## 市场代理和公司结果", ""])
    for group in ("market_validation", "company_validation"):
        for name, metrics in report[group].items():
            lines.append(
                f"- `{name}`：水平相关 {_fmt(metrics['level_correlation'])}，"
                f"变化相关 {_fmt(metrics['change_correlation'])}，"
                f"方向命中率 {_fmt(metrics['direction_accuracy'])}。"
            )
    lines.extend(["", "## 已知失效场景", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend(["", "## 参数来源", ""])
    lines.extend(f"- {item}" for item in report["sources"])
    lines.append("")
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _relationship(proxy: pd.Series, actual: pd.Series) -> dict:
    values = pd.DataFrame({"proxy": proxy, "actual": actual}).dropna()
    if len(values) < 4:
        return _empty_relationship(len(values))
    level_corr = values["proxy"].corr(values["actual"])
    changes = values.diff().dropna()
    change_corr = changes["proxy"].corr(changes["actual"]) if len(changes) >= 3 else np.nan
    direction = (np.sign(changes["proxy"]) == np.sign(changes["actual"])).mean()
    x = values["proxy"].to_numpy(dtype=float)
    y = values["actual"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(x)), x])
    intercept, slope = np.linalg.lstsq(design, y, rcond=None)[0]
    predicted = intercept + slope * x
    residual = x - y
    denominator = ((y - y.mean()) ** 2).sum()
    r_squared = 1 - ((y - predicted) ** 2).sum() / denominator if denominator else np.nan
    return {
        "observations": len(values),
        "level_correlation": _number(level_corr),
        "change_correlation": _number(change_corr),
        "direction_accuracy": _number(direction),
        "ols_intercept": _number(intercept),
        "ols_slope": _number(slope),
        "ols_r_squared": _number(r_squared),
        "residual_mean": _number(residual.mean()),
        "mae": _number(np.abs(residual).mean()),
    }


def _empty_relationship(observations: int) -> dict:
    return {
        "observations": observations,
        "level_correlation": None,
        "change_correlation": None,
        "direction_accuracy": None,
        "ols_intercept": None,
        "ols_slope": None,
        "ols_r_squared": None,
        "residual_mean": None,
        "mae": None,
    }


def _number(value) -> float | None:
    return None if pd.isna(value) else float(value)


def _fmt(value) -> str:
    return "NA" if value is None else f"{value:.3f}"
