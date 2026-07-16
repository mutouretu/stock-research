"""Human-readable and machine-readable reports for lead/lag analysis."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def build_lead_lag_report(
    lag_grid: pd.DataFrame,
    best_lags: pd.DataFrame,
    config: dict,
    *,
    deterministic: bool,
) -> dict:
    """Build report evidence while keeping statistical caveats explicit."""
    violations = int(lag_grid["point_in_time_violations"].sum())
    evidence_counts = {
        str(key): int(value)
        for key, value in best_lags["evidence_status"].value_counts().items()
    }
    return {
        "analysis_id": config["analysis_id"],
        "version": str(config["version"]),
        "status": "PASS" if deterministic and violations == 0 else "ERROR",
        "analysis_end_date": str(config["analysis_end_date"]),
        "lag_convention": "signal x(t) is paired with target y(t+k); k>0 means signal leads",
        "relationship_count": int(best_lags["relationship_id"].nunique()),
        "lag_grid_rows": len(lag_grid),
        "economic_clock_relationships": int(
            (best_lags["clock"] == "economic_period").sum()
        ),
        "availability_clock_relationships": int(
            (best_lags["clock"] == "availability_time").sum()
        ),
        "point_in_time_violations": violations,
        "deterministic_repeat": deterministic,
        "evidence_counts": evidence_counts,
        "inference": config["inference"],
        "best_lags": _records(best_lags),
        "lag_grid": _records(lag_grid),
        "interpretation_contract": {
            "economic_period": (
                "Describes physical/accounting transmission by observation period; it is not "
                "a tradable information set."
            ),
            "availability_time": (
                "Uses only signals whose source available time is no later than the signal date."
            ),
            "best_lag": (
                "Largest absolute correlation in the predeclared lag grid; it remains exploratory."
            ),
            "multiple_testing": (
                "Benjamini-Hochberg q-values are reported within each relationship and globally."
            ),
            "causality": "Correlation and HAC inference do not establish causality.",
        },
    }


def write_lead_lag_report(report: dict, markdown_path: Path, json_path: Path) -> None:
    """Write concise Markdown plus complete JSON evidence."""
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CF M4.1 领先滞后分析",
        "",
        f"- 状态：**{report['status']}**",
        f"- 分析截止日：`{report['analysis_end_date']}`",
        f"- 关系数量：{report['relationship_count']}",
        f"- 滞后网格记录：{report['lag_grid_rows']}",
        f"- 经济期关系：{report['economic_clock_relationships']}",
        f"- 可用期关系：{report['availability_clock_relationships']}",
        f"- Point-in-time 违规：{report['point_in_time_violations']}",
        f"- 重复运行一致：{report['deterministic_repeat']}",
        "",
        "## 时间和统计口径",
        "",
        "- 滞后 `k` 固定表示信号 `x(t)` 与目标 `y(t+k)` 配对；`k>0` 表示信号领先。",
        "- `economic_period` 回答经营变量按统计期如何传导，不代表该时点可交易。",
        "- `availability_time` 只使用信号日之前已经公开的数据，可用于研究后续市场反应。",
        "- 相关系数对应标准化一元回归斜率；标准误使用 Newey--West HAC 修正。",
        "- `q` 值使用 Benjamini--Hochberg 方法校正同一关系内搜索多个滞后造成的多重比较。",
        "- 最佳滞后是预设网格中绝对相关系数最大者，只是探索性摘要，不是因果结论。",
        "",
        "## 各关系的最佳滞后",
        "",
        "| 关系 | 时钟 | 最佳领先期 | N | 相关系数 | HAC p | 关系内 q | 全局 q | 前半段 | 后半段 | 证据 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["best_lags"]:
        lines.append(
            f"| `{row['relationship_id']}` | `{row['clock']}` | "
            f"{row['lead_periods']} { _period_unit(row['frequency']) } | "
            f"{row['observations']} | {_number(row['correlation'])} | "
            f"{_probability(row['p_value_hac'])} | "
            f"{_probability(row['q_value_within_relationship'])} | "
            f"{_probability(row['q_value_global'])} | "
            f"{_number(row['first_half_correlation'])} | "
            f"{_number(row['second_half_correlation'])} | "
            f"`{row['evidence_status']}` |"
        )
    lines.extend(
        [
            "",
            "## 证据标签",
            "",
            "- `STRONG`：前后子样本方向一致、符合经济预期，且关系内和全局多重检验校正后仍显著。",
            "- `DIRECTIONAL`：方向和子样本稳定，但校正后统计证据不足。",
            "- `CONTRADICTORY`：方向稳定但与事前经济预期相反。",
            "- `UNSTABLE`：前后子样本方向不一致或其中一段关系过弱。",
            "- `INSUFFICIENT`：有效观察数低于配置门槛。",
            "- `DIAGNOSTIC`：变量之间存在公式包含关系，只用于核对计算方向，不作为独立证据。",
            "",
            "## 使用边界",
            "",
            "本报告用于筛选值得进入周期状态机的候选关系。季度样本只有约 40 个，"
            "HAC 的正态近似和子样本结果都应视为描述性证据。M4.2 还需要加入滚动窗口、"
            "季节和冲击场景检验；未通过稳定性检查的关系和公式诊断关系都不能直接成为周期状态规则。",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=True) + "\n",
        encoding="utf-8",
    )


def _records(frame: pd.DataFrame) -> list[dict]:
    records: list[dict] = []
    for raw in frame.to_dict(orient="records"):
        record: dict = {}
        for key, value in raw.items():
            if value is pd.NaT:
                record[key] = None
            elif isinstance(value, (pd.Timestamp,)):
                record[key] = value.isoformat()
            elif isinstance(value, np.generic):
                record[key] = value.item()
            else:
                record[key] = value
        records.append(record)
    return records


def _period_unit(frequency: str) -> str:
    return "个月" if frequency == "monthly" else "个季度"


def _number(value) -> str:
    if value is None or not np.isfinite(float(value)):
        return "—"
    return f"{float(value):.3f}"


def _probability(value) -> str:
    if value is None or not np.isfinite(float(value)):
        return "—"
    return "<0.001" if float(value) < 0.001 else f"{float(value):.3f}"
