from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DistributionMetricSpec:
    name: str
    description: str
    healthy_interpretation: str
    distribution_risk_interpretation: str


DISTRIBUTION_METRICS: tuple[DistributionMetricSpec, ...] = (
    DistributionMetricSpec(
        name="pullback_volume_contraction",
        description="回踩阶段成交量是否相对突破阶段缩小。",
        healthy_interpretation="缩量回踩更像浮筹交换或二次吸筹。",
        distribution_risk_interpretation="回踩不缩量甚至放量，可能说明抛压正在释放。",
    ),
    DistributionMetricSpec(
        name="down_volume_pressure",
        description="回踩阶段阴线成交量相对阳线成交量是否偏大。",
        healthy_interpretation="阴线量能可控，说明下跌时抛压没有失控。",
        distribution_risk_interpretation="阴线显著放量、阳线缩量，更像资金边拉边撤。",
    ),
    DistributionMetricSpec(
        name="upper_shadow_pressure",
        description="高位或反抽日是否反复出现放量长上影。",
        healthy_interpretation="上影不密集，且出现后能快速修复。",
        distribution_risk_interpretation="放量长上影密集，可能是冲高派发或承接不足。",
    ),
    DistributionMetricSpec(
        name="breakout_reclaim_quality",
        description="跌破突破位或箱体上沿后是否能快速收回。",
        healthy_interpretation="短暂跌破后快速收回，说明关键位置仍有承接。",
        distribution_risk_interpretation="跌破后长时间站不回，形态可能已经失败。",
    ),
)


__all__ = ["DISTRIBUTION_METRICS", "DistributionMetricSpec"]
