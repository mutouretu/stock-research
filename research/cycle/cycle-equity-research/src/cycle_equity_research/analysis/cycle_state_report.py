"""Report construction for the M4.3 CF cycle-state timeline."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def build_cycle_state_report(
    monthly: pd.DataFrame,
    episodes: pd.DataFrame,
    config: dict,
    *,
    deterministic: bool,
    point_in_time_violations: int,
    validation_decisions: list[dict],
) -> dict:
    """Summarize the locked rules, current state and historical episodes."""
    current = monthly.iloc[-1]
    state_counts = monthly["state"].value_counts().reindex(
        ["RECOVERY", "EXPANSION", "PEAK_RISK", "CONTRACTION", "TROUGH", "MIXED"],
        fill_value=0,
    )
    status = "PASS" if deterministic and point_in_time_violations == 0 else "ERROR"
    return {
        "analysis_id": config["analysis_id"],
        "version": str(config["version"]),
        "status": status,
        "analysis_end_date": str(config["analysis_end_date"]),
        "monthly_rows": len(monthly),
        "point_in_time_violations": point_in_time_violations,
        "deterministic_repeat": deterministic,
        "core_signal_contract": {
            "column": config["core_signal"]["column"],
            "economic_dimensions": ["trailing_level_z", "three_month_momentum_z"],
            "score_weights": config["core_signal"]["score_weights"],
            "double_counting_rule": (
                "Urea, Henry Hub, realized spread, gross margin and EBITDA validate or "
                "attribute the same chain; none receives a second state weight."
            ),
            "validation_relationships": validation_decisions,
        },
        "thresholds": config["state_thresholds"],
        "hysteresis": config["hysteresis"],
        "confirmation_contract": (
            "Company disclosure and CF momentum are overlays and never alter economic state."
        ),
        "state_counts": {str(key): int(value) for key, value in state_counts.items()},
        "transition_count": int(monthly["state_changed"].sum()),
        "current": _record(current),
        "episodes": [_record(row) for _, row in episodes.iterrows()],
        "monthly": [_record(row) for _, row in monthly.iterrows()],
    }


def write_cycle_state_report(report: dict, markdown_path: Path, json_path: Path) -> None:
    """Write human-readable and complete machine-readable reports."""
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    current = report["current"]
    lines = [
        "# CF M4.3 规则型周期状态",
        "",
        f"- 状态：**{report['status']}**",
        f"- 分析截止日：`{report['analysis_end_date']}`",
        f"- 月度记录：{report['monthly_rows']}",
        f"- 状态切换：{report['transition_count']}",
        f"- Point-in-time 违规：{report['point_in_time_violations']}",
        f"- 重复运行一致：{report['deterministic_repeat']}",
        "",
        "## 当前快照",
        "",
        f"- 月份：`{current['month_end'][:10]}`",
        f"- 经营周期状态：`{current['state']}`",
        f"- 原始状态原因：`{current['raw_state_reason']}`",
        f"- 周期分数：{_number(current['cycle_score'])}",
        f"- 公司确认：`{current['company_confirmation']}`",
        f"- 股票确认：`{current['market_confirmation']}`",
        f"- 确认叠加：`{current['confirmation_overlay']}`",
        "",
    ]
    if current["raw_state_reason"] == "DATA_GAP":
        lines.extend(
            [
                "> 当前核心价差不可用，状态按安全规则立即降级为 MIXED。公司披露和股价"
                "只展示背离或确认，不能替代缺失的外部周期信号。",
                "",
            ]
        )
    lines.extend(
        [
            "## 状态定义",
            "",
            "状态只使用同一个全球尿素气价差的两个维度：相对过去 60 个月的位置和三个月"
            "变化方向。两者均采用当时可得的滚动标准分，最低需要 36 个月历史。分数为两者"
            "截尾后等权平均，用于画图；离散状态由二维阈值直接判断，不按分数切档。",
            "",
            "| 状态 | 进入条件 |",
            "|---|---|",
            "| `RECOVERY` | 价差位置不高、动量明显转正 |",
            "| `EXPANSION` | 价差位置与动量同时偏强 |",
            "| `PEAK_RISK` | 价差仍高，但动量明显转负 |",
            "| `CONTRACTION` | 价差位置与动量同时偏弱 |",
            "| `TROUGH` | 价差仍低，但动量明显转正 |",
            "| `MIXED` | 信号冲突、历史不足或核心数据缺失 |",
            "",
            "进入新状态需要连续两个月确认；非 MIXED 状态至少保持三个月，并使用较宽的"
            "退出阈值形成滞回。核心数据缺失不参与滞回，会立即进入 MIXED，避免沿用陈旧值。",
            "",
            "## 不重复计分",
            "",
            "M4.2 已验证全球尿素气价差会传导到 CF 实现价差、毛利率变化和 EBITDA 变化。"
            "尿素价格、Henry Hub 和这些公司结果属于同一条传导链，首版只让合成后的外部"
            "价差获得一次核心权重。公司披露与 CF 六个月动量仅作为确认层，不改变周期状态。",
            "",
            "## 历史状态段",
            "",
            "| 状态 | 开始 | 结束 | 月数 | 结束分数 | 结束确认 |",
            "|---|---|---|---:|---:|---|",
        ]
    )
    for episode in report["episodes"]:
        lines.append(
            f"| `{episode['state']}` | {episode['start_month'][:10]} | "
            f"{episode['end_month'][:10]} | {episode['months']} | "
            f"{_number(episode['end_score'])} | `{episode['end_confirmation']}` |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "这是一套经营周期分类，不是买入评分。`PEAK_RISK` 不使用估值，避免提前引入 M5；"
            "`TROUGH` 也不使用低估值定义。阈值是预先声明的可复算规则，不是从股票收益反推"
            "出的最优切点。当前历史状态用于描述与后续回测基准，不构成因果或收益保证。",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=True) + "\n",
        encoding="utf-8",
    )


def _record(row: pd.Series) -> dict:
    record = {}
    for key, value in row.items():
        if value is pd.NaT or value is None:
            record[key] = None
        elif isinstance(value, pd.Timestamp):
            record[key] = value.isoformat()
        elif isinstance(value, np.generic):
            scalar = value.item()
            record[key] = None if isinstance(scalar, float) and np.isnan(scalar) else scalar
        elif isinstance(value, float) and np.isnan(value):
            record[key] = None
        else:
            record[key] = value
    return record


def _number(value) -> str:
    if value is None or not np.isfinite(float(value)):
        return "—"
    return f"{float(value):.3f}"
