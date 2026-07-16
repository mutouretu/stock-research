"""Reports for the CF quarterly operating-bridge experiment."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def build_experiment_report(
    predictions: pd.DataFrame,
    metrics: pd.DataFrame,
    final_parameters: dict,
    config: dict,
    *,
    deterministic: bool,
) -> dict:
    """Create serializable experiment evidence without judging economic usefulness."""
    pit_violations = int(
        (pd.to_datetime(predictions["train_last_available_time"]) > predictions["prediction_time"]).sum()
        + (pd.to_datetime(predictions["target_available_time"]) <= predictions["prediction_time"]).sum()
    )
    periods = predictions["period_end"].drop_duplicates().sort_values()
    return {
        "experiment_id": config["experiment_id"],
        "version": str(config["version"]),
        "status": "PASS" if pit_violations == 0 and deterministic else "ERROR",
        "prediction_timing": (
            f"period_end + {config['evaluation']['prediction_lag_days_after_period_end']} days"
        ),
        "minimum_training_quarters": int(
            config["evaluation"]["minimum_training_quarters"]
        ),
        "prediction_periods": len(periods),
        "first_prediction_period": periods.iloc[0].date().isoformat(),
        "last_prediction_period": periods.iloc[-1].date().isoformat(),
        "prediction_rows": len(predictions),
        "point_in_time_violations": pit_violations,
        "deterministic_repeat": deterministic,
        "metrics": metrics.to_dict(orient="records"),
        "final_parameters": final_parameters,
        "comparison_contract": {
            "keys": ["period_end", "task_group", "target", "product"],
            "required_metadata": [
                "prediction_time",
                "train_start_period",
                "train_end_period",
                "train_rows",
                "train_last_available_time",
            ],
            "rule": (
                "Later methods must predict every locked row for selected targets and are "
                "compared against theoretical_operating_bridge on the same observations."
            ),
        },
    }


def write_experiment_report(report: dict, markdown_path: Path, json_path: Path) -> None:
    """Write a concise human report plus complete JSON metrics."""
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CF 季度经营桥基准实验",
        "",
        f"- 状态：**{report['status']}**",
        f"- 预测时点：`{report['prediction_timing']}`",
        f"- 最少训练季度：{report['minimum_training_quarters']}",
        f"- 样本外季度：{report['prediction_periods']}（{report['first_prediction_period']} 至 "
        f"{report['last_prediction_period']}）",
        f"- 预测记录：{report['prediction_rows']}",
        f"- Point-in-time 违规：{report['point_in_time_violations']}",
        f"- 重复运行一致：{report['deterministic_repeat']}",
        "",
        "## 方法",
        "",
        "- 实现售价：历史扩展窗口一元线性回归，解释变量为当季全球尿素价格。",
        "- 实际气价：当季与上季 Henry Hub 等权平均，再用历史扩展窗口估计。",
        "- 单位毛利：预测售价减气耗乘预测气价，再减历史其他成本残差均值。",
        "- 销量：相同日历季度的历史扩展均值。",
        "- 毛利润：各产品预测销量乘预测单位毛利后加总。",
        "- 朴素对照：截至预测日最新已披露的上一期实际值。",
        "",
        "## 样本外结果",
        "",
        "正的改善率表示经营桥优于上一期实际值；负值表示经营桥暂未增加预测价值。",
        "",
        "| 任务 | 产品 | N | MAE | 朴素 MAE | 改善率 | 方向准确率 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in report["metrics"]:
        lines.append(
            f"| {item['task_group']} | {item['product']} | {item['observations']} | "
            f"{item['mae']:.3f} | {item['naive_mae']:.3f} | "
            f"{item['improvement_vs_naive']:.1%} | {item['direction_accuracy']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## 如何评价后续方法",
            "",
            "后续方法必须复用相同的季度、预测时点、训练窗口和目标。对于选择的每个目标，"
            "不得遗漏经营桥中较难预测的季度。只有样本外 MAE/RMSE、方向准确率和相对经营桥"
            "改善同时稳定，才能认为新方法提供了增量价值。",
            "",
            "当前基准用于锁定比较尺度，不要求所有子任务都优于朴素对照。负改善的子任务"
            "恰好指出简单传导关系尚未捕捉的基差、产品结构或离散事件。",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=True) + "\n",
        encoding="utf-8",
    )
