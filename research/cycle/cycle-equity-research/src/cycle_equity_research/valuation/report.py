"""Quality report for the M5.1 point-in-time valuation data layer."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def build_valuation_data_report(
    monthly: pd.DataFrame, diagnostics: dict, config: dict, *, deterministic: bool
) -> dict:
    valid = monthly.loc[monthly["reported_multiple_available"]]
    current = monthly.iloc[-1]
    minimum = int(config["quality"]["minimum_months_with_reported_multiple"])
    status = "PASS"
    if (
        not deterministic
        or diagnostics["point_in_time_violations"]
        or diagnostics["duplicate_months"]
        or len(valid) < minimum
        or not bool(current["reported_multiple_available"])
    ):
        status = "ERROR"
    return {
        "valuation_id": config["valuation_id"],
        "version": str(config["version"]),
        "status": status,
        "analysis_end_date": str(config["analysis_end_date"]),
        "monthly_rows": len(monthly),
        "valid_multiple_months": len(valid),
        "valid_multiple_start": _date(valid["month_end"].min()) if len(valid) else None,
        "point_in_time_violations": diagnostics["point_in_time_violations"],
        "deterministic_repeat": deterministic,
        "diagnostics": diagnostics,
        "contracts": {
            "market_cap": "unadjusted close times point-in-time shares outstanding",
            "standard_enterprise_value": (
                "market cap + total financial debt - cash + noncontrolling interest "
                "+ preferred equity"
            ),
            "lease_adjusted_enterprise_value": (
                "standard enterprise value + current and noncurrent operating leases"
            ),
            "reported_ttm_ebitda": config["earnings"]["definition"],
            "primary_multiple": "standard enterprise value / reported TTM EBITDA proxy",
            "lease_policy": config["enterprise_value"]["lease_treatment"],
        },
        "current": _record(current),
        "historical_multiple": {
            "minimum": float(valid["ev_to_reported_ttm_ebitda"].min()),
            "median": float(valid["ev_to_reported_ttm_ebitda"].median()),
            "maximum": float(valid["ev_to_reported_ttm_ebitda"].max()),
        },
    }


def write_valuation_data_report(report: dict, markdown_path: Path, json_path: Path) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    current = report["current"]
    lines = [
        "# CF M5.1 Point-in-time 估值数据质量报告",
        "",
        f"- 状态：**{report['status']}**",
        f"- 数据截止日：`{report['analysis_end_date']}`",
        f"- 月度记录：{report['monthly_rows']}",
        f"- 有效倍数月份：{report['valid_multiple_months']}（自 {report['valid_multiple_start'][:10]}）",
        f"- Point-in-time 违规：{report['point_in_time_violations']}",
        f"- 重复运行一致：{report['deterministic_repeat']}",
        "",
        "## 当前估值数据快照",
        "",
        f"- 市场价格日期：`{current['month_end'][:10]}`",
        f"- 最新财务期间：`{current['latest_period_end'][:10]}`",
        f"- 财务公开日期：`{current['fundamental_available_time'][:10]}`",
        f"- 未复权收盘价：{_number(current['market_price'], 2)} 美元",
        f"- 股份数：{_billions(current['shares_outstanding'])} 十亿股",
        f"- 市值：{_billions(current['market_cap'])} 十亿美元",
        f"- 金融债务：{_billions(current['financial_debt'])} 十亿美元",
        f"- 现金：{_billions(current['cash'])} 十亿美元",
        f"- 非控股权益：{_billions(current['noncontrolling_interest'])} 十亿美元",
        f"- 标准企业价值：{_billions(current['enterprise_value_standard'])} 十亿美元",
        f"- TTM EBITDA 代理：{_billions(current['reported_ttm_ebitda'])} 十亿美元",
        f"- EV/TTM EBITDA：{_number(current['ev_to_reported_ttm_ebitda'], 2)} 倍",
        f"- 租赁调整后倍数：{_number(current['lease_adjusted_ev_to_reported_ttm_ebitda'], 2)} 倍",
        f"- TTM 股权自由现金流收益率：{_percent(current['equity_fcf_yield_ttm'])}",
        "",
        "## 口径修正",
        "",
        "旧面板的企业价值只计算市值加长期债务减现金，遗漏了与合并 EBITDA 对应的非控股权益。"
        f"当前非控股权益为 {_billions(current['noncontrolling_interest'])} 十亿美元；加上债务范围差异后，"
        f"标准 EV 比旧口径增加 {_billions(current['nci_and_debt_scope_adjustment'])} 十亿美元。",
        "",
        "主口径暂不加入经营租赁负债，因为当前 EBITDA 代理没有做租赁费用调整。租赁负债只输出"
        "敏感性倍数，避免分子加租赁而分母仍保留租金费用的口径错配。",
        "",
        "## 当前边界",
        "",
        "- EBITDA 是经营利润加折旧摊销的统一代理，不等于 CF 公司自定义 Adjusted EBITDA。",
        "- 缺失的短期借款按零处理并显式标记；这适用于未披露通常表示余额为零的当前数据，"
        "但历史异常期仍需回看债务附注。",
        "- 月度市值必须使用未复权收盘价；复权价包含历史分红调整，不能与当时股份数直接相乘。",
        "- M5.1 只建立 reported TTM 数据层，中周期 EBITDA 和估值区间在 M5.2、M5.3 计算。",
        "",
    ]
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _record(row: pd.Series) -> dict:
    record = {}
    for key, value in row.items():
        if value is pd.NaT or value is None or (isinstance(value, float) and np.isnan(value)):
            record[key] = None
        elif isinstance(value, pd.Timestamp):
            record[key] = value.isoformat()
        elif isinstance(value, np.generic):
            scalar = value.item()
            record[key] = None if isinstance(scalar, float) and np.isnan(scalar) else scalar
        else:
            record[key] = value
    return record


def _date(value) -> str:
    return pd.Timestamp(value).isoformat()


def _number(value, digits: int) -> str:
    if value is None or not np.isfinite(float(value)):
        return "—"
    return f"{float(value):.{digits}f}"


def _billions(value) -> str:
    if value is None or not np.isfinite(float(value)):
        return "—"
    return f"{float(value) / 1_000_000_000:.3f}"


def _percent(value) -> str:
    if value is None or not np.isfinite(float(value)):
        return "—"
    return f"{float(value):.1%}"
