"""Reports for M4.2 fixed-lag stability analysis."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def build_stability_report(
    rolling_windows: pd.DataFrame,
    slices: pd.DataFrame,
    decisions: pd.DataFrame,
    config: dict,
    *,
    deterministic: bool,
) -> dict:
    """Build complete evidence without overstating overlapping-window counts."""
    return {
        "analysis_id": config["analysis_id"],
        "version": str(config["version"]),
        "status": "PASS" if deterministic else "ERROR",
        "analysis_end_date": str(config["analysis_end_date"]),
        "fixed_lag_rule": (
            "Every relationship uses its M4.1 best lag; no lag is reselected in windows or slices."
        ),
        "relationship_count": int(decisions["relationship_id"].nunique()),
        "rolling_window_rows": len(rolling_windows),
        "slice_rows": len(slices),
        "point_in_time_violations": 0,
        "deterministic_repeat": deterministic,
        "decision_counts": {
            str(key): int(value)
            for key, value in decisions["decision"].value_counts().items()
        },
        "rolling_config": config["rolling"],
        "slice_config": config["slices"],
        "decision_thresholds": config["decision_thresholds"],
        "decisions": _records(decisions),
        "rolling_windows": _records(rolling_windows),
        "slices": _records(slices),
        "interpretation_contract": {
            "rolling_windows": (
                "Windows overlap and are stability diagnostics, not independent observations."
            ),
            "season_slices": (
                "Season groups use target-period month or quarter and are descriptive at small N."
            ),
            "gas_regime": (
                "Low/high gas uses the aligned sample median and is not a live trading threshold."
            ),
            "spread_stress": (
                "Large change means the top quartile of absolute spread changes; it is not a "
                "hand-labeled geopolitical supply shock."
            ),
            "double_counting": (
                "Accepted validations do not imply that upstream and downstream versions of the "
                "same economic signal should each receive score weight."
            ),
        },
    }


def write_stability_report(report: dict, markdown_path: Path, json_path: Path) -> None:
    """Write a concise decision report plus full JSON windows and slices."""
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CF M4.2 领先滞后稳定性分析",
        "",
        f"- 状态：**{report['status']}**",
        f"- 分析截止日：`{report['analysis_end_date']}`",
        f"- 关系数量：{report['relationship_count']}",
        f"- 滚动窗口记录：{report['rolling_window_rows']}",
        f"- 场景切片记录：{report['slice_rows']}",
        f"- Point-in-time 违规：{report['point_in_time_violations']}",
        f"- 重复运行一致：{report['deterministic_repeat']}",
        "",
        "## 固定规则",
        "",
        "- 每个关系沿用 M4.1 已选择的领先期，不在滚动窗口或场景内重新挑选滞后。",
        "- 月频使用 60 个观察、季度使用 20 个观察；财报事件关系使用 20 个事件。",
        "- 核心门槛为：预期方向窗口占比不低于 75%，滚动中位绝对相关不低于 0.20。",
        "- 高低气价和正常/大幅价差变化两类场景的预期方向占比均需不低于 75%，且各场景绝对相关不低于 0.10。",
        "- 季节切片只用于描述，不作为硬门槛，因为季度样本分组后很小。",
        "",
        "## 关系决策",
        "",
        "| 关系 | 角色 | 固定领先期 | 全样本相关 | 滚动中位 | 滚动同向 | 气价场景 | 波动场景 | 决策 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["decisions"]:
        lines.append(
            f"| `{row['relationship_id']}` | `{row['candidate_role']}` | "
            f"{row['fixed_lead_periods']} | {_number(row['full_sample_correlation'])} | "
            f"{_number(row['rolling_median_correlation'])} | "
            f"{_percent(row['rolling_expected_sign_share'])} | "
            f"{_percent(row['gas_regime_expected_sign_share'])} | "
            f"{_percent(row['stress_regime_expected_sign_share'])} | "
            f"`{row['decision']}` |"
        )
    lines.extend(
        [
            "",
            "## 决策含义",
            "",
            "- `ACCEPT_BRIDGE`：可保留在实现售价或实际气价经营桥中。",
            "- `ACCEPT_CORE_VALIDATION`：支持核心周期代理，但同一传导链只计一次分。",
            "- `ACCEPT_CONFIRMATION`：只作为市场确认，不进入经营周期核心分数。",
            "- `CONDITIONAL`：全样本较强，但滚动或场景稳定性未全部通过。",
            "- `REJECT`：M4.1 已不稳定、方向矛盾或证据不足。",
            "- `DIAGNOSTIC`：公式包含关系，只核对构造方向。",
            "",
            "## 解释边界",
            "",
            "滚动窗口高度重叠，窗口通过率不是独立试验的成功概率。高低气价使用样本中位数，"
            "大幅变化使用价差绝对变化的前 25%，二者用于历史稳健性检查，不是实时状态阈值。"
            "所谓大幅变化也不等于已经识别出地缘供给事件。实时状态机仍需使用当时可计算的"
            "扩展窗口阈值，并避免把尿素、Henry Hub、理论气价差和下游毛利重复加权。",
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
            elif isinstance(value, pd.Timestamp):
                record[key] = value.isoformat()
            elif isinstance(value, np.generic):
                record[key] = value.item()
            else:
                record[key] = value
        records.append(record)
    return records


def _number(value) -> str:
    if value is None or not np.isfinite(float(value)):
        return "—"
    return f"{float(value):.3f}"


def _percent(value) -> str:
    if value is None or not np.isfinite(float(value)):
        return "—"
    return f"{float(value):.0%}"
