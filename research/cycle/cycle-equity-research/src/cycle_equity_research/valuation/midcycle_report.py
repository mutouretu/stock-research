"""Reporting for M5.2 CF mid-cycle EBITDA scenarios."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def build_midcycle_report(
    scenarios: pd.DataFrame,
    product_bridge: pd.DataFrame,
    calibration: dict,
    diagnostics: dict,
    sensitivities: dict,
    config: dict,
    *,
    deterministic: bool,
) -> dict:
    quality = config["quality"]
    status = "PASS"
    if (
        not deterministic
        or diagnostics["point_in_time_violations"]
        or not diagnostics["gross_profit_identity_pass"]
        or not diagnostics["scenario_ordering_pass"]
        or diagnostics["calibration_quarters"] < int(quality["minimum_quarters"])
        or diagnostics["annual_volume_windows"] < int(quality["minimum_annual_windows"])
    ):
        status = "ERROR"
    return {
        "valuation_id": config["valuation_id"],
        "version": str(config["version"]),
        "status": status,
        "analysis_as_of": str(config["analysis_as_of"]),
        "deterministic_repeat": deterministic,
        "diagnostics": diagnostics,
        "method_contract": {
            "realized_prices": "operating-bridge OLS on global urea in USD per short ton",
            "realized_gas": "operating-bridge OLS on current/previous Henry Hub equal-weight lag",
            "unit_margin": "realized price - gas intensity * realized gas - other cost residual",
            "gross_profit": "sum of product annual volume * unit margin",
            "ebitda": "gross profit + historical EBITDA-minus-gross-profit conversion residual",
            "scenario_meaning": (
                "Marginal historical quantiles are combined into coherent stresses; they are not "
                "joint probabilities or fitted stock-price targets."
            ),
        },
        "calibration": calibration,
        "sensitivities_usd_million": sensitivities,
        "scenarios": _records(scenarios),
        "product_bridge": _records(product_bridge),
    }


def write_midcycle_report(report: dict, markdown_path: Path, json_path: Path) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    scenario_by_name = {row["scenario"]: row for row in report["scenarios"]}
    lines = [
        "# CF M5.2 中周期 EBITDA 情景",
        "",
        f"- 状态：**{report['status']}**",
        f"- 校准截止：`{report['analysis_as_of']}`",
        f"- 校准季度：{report['diagnostics']['calibration_quarters']}",
        f"- 年度窗口：{report['diagnostics']['annual_volume_windows']}",
        f"- Point-in-time 违规：{report['diagnostics']['point_in_time_violations']}",
        f"- 毛利润恒等式通过：{report['diagnostics']['gross_profit_identity_pass']}",
        f"- 情景顺序通过：{report['diagnostics']['scenario_ordering_pass']}",
        f"- 重复运行一致：{report['deterministic_repeat']}",
        "",
        "## 情景结果",
        "",
        "| 情景 | 全球尿素 | Henry Hub | CF 实际气价 | 年销量 | 毛利润 | 转换项 | EBITDA | 相对当前 TTM |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {"downside": "下行", "base": "中性", "upside": "上行"}
    for name in ("downside", "base", "upside"):
        row = scenario_by_name[name]
        lines.append(
            f"| {labels[name]} | {row['urea_usd_per_metric_ton']:.1f} 美元/公吨 | "
            f"{row['henry_hub_usd_per_mmbtu']:.2f} | {row['cf_realized_gas_usd_per_mmbtu']:.2f} | "
            f"{row['annual_volume_thousand_short_tons'] / 1000:.2f} 百万短吨 | "
            f"{row['gross_profit_usd_million']:.0f} 百万美元 | "
            f"{row['ebitda_conversion_usd_million']:.0f} 百万美元 | "
            f"**{row['scenario_ebitda_usd_million']:.0f} 百万美元** | "
            f"{row['scenario_vs_reported_ttm']:.0%} |"
        )
    base = scenario_by_name["base"]
    lines.extend(
        [
            "",
            "当前 reported TTM EBITDA 代理为 "
            f"{base['reported_ttm_ebitda_usd_million']:.0f} 百万美元；中性情景约为 "
            f"{base['scenario_ebitda_usd_million']:.0f} 百万美元。差异说明当前盈利高于历史"
            "中位经营条件，不能用 reported TTM 倍数直接代替中周期估值。",
            "",
            "下行情景把尿素和销量放在历史 25 分位、Henry Hub 和其他成本放在不利的 75 "
            "分位，并不是 EBITDA 的 25 分位预测。多个不利边际分位同时发生会产生更严格的"
            "联合压力，因此结果可以低于历史 TTM EBITDA 的 25 分位。",
            "",
            "## 中性情景分产品经营桥",
            "",
            "| 产品 | 实现售价 | 气耗 | 其他成本 | 单位毛利 | 年销量 | 毛利润贡献 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["product_bridge"]:
        if row["scenario"] != "base":
            continue
        price = "—" if row["realized_price_usd_per_short_ton"] is None else f"{row['realized_price_usd_per_short_ton']:.1f}"
        intensity = "—" if row["gas_intensity_mmbtu_per_short_ton"] is None else f"{row['gas_intensity_mmbtu_per_short_ton']:.1f}"
        cost = "—" if row["other_cost_usd_per_short_ton"] is None else f"{row['other_cost_usd_per_short_ton']:.1f}"
        lines.append(
            f"| `{row['product']}` | {price} | {intensity} | {cost} | "
            f"{row['unit_margin_usd_per_short_ton']:.1f} | "
            f"{row['annual_volume_thousand_short_tons'] / 1000:.2f} 百万短吨 | "
            f"{row['gross_profit_usd_million']:.0f} 百万美元 |"
        )
    sensitivity = report["sensitivities_usd_million"]
    lines.extend(
        [
            "",
            "## 中性情景局部敏感性",
            "",
            f"- 全球尿素每上涨 10 美元/公吨，年度 EBITDA 约增加 {sensitivity['ebitda_change_per_10_usd_metric_ton_urea']:.0f} 百万美元。",
            f"- Henry Hub 每上涨 1 美元/MMBtu，年度 EBITDA 约减少 {abs(sensitivity['ebitda_change_per_1_usd_mmbtu_henry_hub']):.0f} 百万美元。",
            f"- 总销量变化 1%，中性情景毛利润约变化 {sensitivity['gross_profit_change_per_1_percent_volume']:.0f} 百万美元。",
            "",
            "这些是保持其他条件不变的局部敏感度，不能解释为价格之间相互独立。全球高气价"
            "可能同时推高尿素，销量变化也可能伴随产品结构变化。",
            "",
            "## 失效条件",
            "",
            "- 全球尿素与 CF 地区、合同和产品基差发生持续结构变化；",
            "- 天然气跨过海外停复产阈值，使价格传导显著非线性；",
            "- CF 出现大型装置停产、收购、剥离或产品组合变化；",
            "- 其他成本残差因低碳项目、检修或会计口径发生永久跃迁；",
            "- 分产品披露范围变化，导致历史销量和毛利/吨不可比。",
            "",
            "M5.2 只给出 EBITDA 情景，不使用当前股价反推参数，也不输出目标价。M5.3 才会将"
            "这些 EBITDA 与估值倍数、净债务、非控股权益和股份数结合为价值区间。",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _records(frame: pd.DataFrame) -> list[dict]:
    records = []
    for raw in frame.to_dict(orient="records"):
        record = {}
        for key, value in raw.items():
            if value is pd.NaT or value is None or (
                isinstance(value, float) and np.isnan(value)
            ):
                record[key] = None
            elif isinstance(value, pd.Timestamp):
                record[key] = value.isoformat()
            elif isinstance(value, np.generic):
                record[key] = value.item()
            else:
                record[key] = value
        records.append(record)
    return records
