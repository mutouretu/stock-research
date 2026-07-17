"""Reporting for M5.3 CF valuation ranges and implied assumptions."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def build_valuation_range_report(
    matrix: pd.DataFrame,
    implied: pd.DataFrame,
    snapshot: dict,
    diagnostics: dict,
    config: dict,
    *,
    deterministic: bool,
) -> dict:
    status = "PASS"
    if (
        not deterministic
        or diagnostics["point_in_time_violations"]
        or not diagnostics["equity_bridge_pass"]
        or not diagnostics["matrix_values_finite"]
        or diagnostics["multiple_history_months"]
        < int(config["quality"]["minimum_multiple_months"])
        or diagnostics["matrix_rows"] != 9
    ):
        status = "ERROR"
    return {
        "valuation_id": config["valuation_id"],
        "version": str(config["version"]),
        "status": status,
        "analysis_as_of": str(config["analysis_as_of"]),
        "deterministic_repeat": deterministic,
        "diagnostics": diagnostics,
        "contracts": {
            "valuation_matrix": "three EBITDA scenarios crossed with three historical multiple quantiles",
            "equity_bridge": (
                "enterprise value - net financial debt - noncontrolling interest - preferred equity"
            ),
            "limited_liability_floor": (
                "negative raw equity is displayed as zero per share, not as a negative stock price"
            ),
            "implied_urea": (
                "global urea required to support current EV while all other base assumptions stay fixed"
            ),
            "interpretation": "reference range and reverse DCF-style diagnostic, not a price target",
        },
        "snapshot": snapshot,
        "valuation_matrix": _records(matrix),
        "implied_assumptions": _records(implied),
    }


def write_valuation_range_report(report: dict, markdown_path: Path, json_path: Path) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = report["snapshot"]
    matrix = {
        (row["scenario"], row["multiple_case"]): row
        for row in report["valuation_matrix"]
    }
    implied = {row["multiple_case"]: row for row in report["implied_assumptions"]}
    lines = [
        "# CF M5.3 价值区间与隐含经营假设",
        "",
        f"- 状态：**{report['status']}**",
        f"- 分析截止：`{report['analysis_as_of']}`",
        f"- 历史倍数月份：{report['diagnostics']['multiple_history_months']}",
        f"- Point-in-time 违规：{report['diagnostics']['point_in_time_violations']}",
        f"- 股权桥勾稽通过：{report['diagnostics']['equity_bridge_pass']}",
        f"- 重复运行一致：{report['deterministic_repeat']}",
        "",
        "## 当前输入",
        "",
        f"- 股价：{snapshot['market_price_usd']:.2f} 美元（{snapshot['market_price_date'][:10]}）",
        f"- 企业价值：{snapshot['current_enterprise_value_usd'] / 1e9:.2f} 十亿美元",
        f"- 净金融债务：{snapshot['net_financial_debt_usd'] / 1e9:.2f} 十亿美元",
        f"- 非控股权益：{snapshot['noncontrolling_interest_usd'] / 1e9:.2f} 十亿美元",
        f"- 经营周期：`{snapshot['cycle_state']}/{snapshot['cycle_state_reason']}`"
        f"（状态日期 {str(snapshot['cycle_state_as_of'])[:10]}）",
        f"- 确认层：`{snapshot['confirmation_overlay']}`",
        "",
        "历史 reported EV/EBITDA 的 25/50/75 分位分别为 "
        f"{snapshot['multiple_cases']['low']:.2f}、{snapshot['multiple_cases']['median']:.2f}、"
        f"{snapshot['multiple_cases']['high']:.2f} 倍。它们只是估值尺子的历史范围，不代表"
        "每种经营情景应当自动获得某一个特定倍数。",
        "",
        "## 每股价值矩阵",
        "",
        "| EBITDA 情景 | 低倍数 | 中位倍数 | 高倍数 | 当前 EV/情景 EBITDA |",
        "|---|---:|---:|---:|---:|",
    ]
    labels = {"downside": "下行", "base": "中性", "upside": "上行"}
    for scenario in ("downside", "base", "upside"):
        low = matrix[(scenario, "low")]
        median = matrix[(scenario, "median")]
        high = matrix[(scenario, "high")]
        lines.append(
            f"| {labels[scenario]}（EBITDA {low['scenario_ebitda_usd_million']:.0f} 百万美元） | "
            f"{_per_share(low)} | {_per_share(median)} | {_per_share(high)} | "
            f"{low['current_ev_to_scenario_ebitda']:.2f} 倍 |"
        )
    lines.extend(
        [
            "",
            f"中性 EBITDA 对应的每股区间约为 {snapshot['base_per_share_low_usd']:.0f}–"
            f"{snapshot['base_per_share_high_usd']:.0f} 美元，中位参考约 "
            f"{snapshot['base_per_share_median_usd']:.0f} 美元。当前股价高于这一中性区间，"
            "意味着市场要求更高的盈利、较高的估值倍数，或二者的组合。中位参考不是目标价。",
            "",
            "下行情景下原始股权价值为负，因此按有限责任将每股价值显示为 0。这个 0 表示"
            "情景 EBITDA 无法覆盖净债务和非控股权益对应的企业价值要求，不是预测股票必然归零。",
            "",
            "## 当前价格隐含的经营条件",
            "",
            "| 倍数假设 | 隐含 EBITDA | 隐含全球尿素 | 相对历史中位 | 历史四分位位置 |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for name, label in (("low", "低"), ("median", "中位"), ("high", "高")):
        row = implied[name]
        lines.append(
            f"| {label}（{row['ev_to_ebitda_multiple']:.2f} 倍） | "
            f"{row['implied_ebitda_usd_million']:.0f} 百万美元 | "
            f"{row['implied_urea_usd_per_metric_ton']:.0f} 美元/公吨 | "
            f"{row['urea_vs_historical_median']:.0%} | `{row['urea_iqr_position']}` |"
        )
    median_implied = implied["median"]
    lines.extend(
        [
            "",
            f"在历史中位倍数下，当前企业价值隐含 EBITDA 约 "
            f"{median_implied['implied_ebitda_usd_million']:.0f} 百万美元。保持 Henry Hub、销量、"
            f"产品结构、其他成本和转换项为中性假设时，对应全球尿素约 "
            f"{median_implied['implied_urea_usd_per_metric_ton']:.0f} 美元/公吨，位于历史 25–75 "
            "分位区间内但明显高于中位数。",
            "",
            "## 解释边界",
            "",
            "- 倍数来自 reported TTM EBITDA 历史分布，仍会受到周期状态影响；",
            "- 九格矩阵用于展示 EBITDA 与倍数的交互，不能挑选最乐观格子作为结论；",
            "- 隐含尿素是单变量反推，现实中天然气、销量、基差和成本会共同变化；",
            "- 当前周期状态因全球尿素数据过期而为 `MIXED/DATA_GAP`，降低了对实时周期位置的把握；",
            "- 结果未包含股息、回购时点、税务差异或未来资本配置的额外价值。",
            "",
            "M5.3 完成的是估值解释层，不是买入信号。M6 才会预先声明周期、估值、确认和"
            "数据风险如何组合，并受异常闸门约束。",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _per_share(row: dict) -> str:
    if row["raw_equity_value_usd"] < 0:
        return "0 美元（原始为负）"
    return f"{row['per_share_value_usd']:.0f} 美元"


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
