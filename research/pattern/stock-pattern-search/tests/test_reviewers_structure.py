from src.reviewers.common.scoring import sigmoid_decay_factor
from src.reviewers.type_n.phase1_breakout.penalties import apply_post_penalties
from src.reviewers.type_n.phase2_pullback import (
    CHIP_COLUMNS,
    DISTRIBUTION_METRICS,
    load_chip_structure_values,
    load_midlong_trend_values,
)


def test_active_reviewer_imports_are_registered() -> None:
    assert callable(apply_post_penalties)
    assert callable(sigmoid_decay_factor)


def test_phase2_distribution_reviewer_metric_specs_are_registered() -> None:
    metric_names = {metric.name for metric in DISTRIBUTION_METRICS}

    assert metric_names == {
        "pullback_volume_contraction",
        "down_volume_pressure",
        "upper_shadow_pressure",
        "breakout_reclaim_quality",
    }


def test_phase2_chip_structure_reviewer_is_registered() -> None:
    assert "cost_50pct" in CHIP_COLUMNS
    assert callable(load_chip_structure_values)


def test_phase2_midlong_trend_reviewer_is_registered() -> None:
    assert callable(load_midlong_trend_values)
