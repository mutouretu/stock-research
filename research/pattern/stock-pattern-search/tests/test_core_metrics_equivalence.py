from __future__ import annotations

import math

import numpy as np
import pytest

from research_ml_core.evaluation import classification_metrics
from src.training.metrics import compute_binary_metrics


@pytest.mark.parametrize(
    ("truth", "score", "threshold"),
    [
        ([0, 1, 0, 1], [0.1, 0.9, 0.4, 0.8], 0.5),
        ([0, 1, 1, 0], [0.2, 0.6, 0.7, 0.1], 0.65),
        ([0, 1], [0.5, 0.5], 0.5),
    ],
)
def test_binary_metrics_match_ml_core(
    truth: list[int], score: list[float], threshold: float
) -> None:
    expected = compute_binary_metrics(np.asarray(truth), np.asarray(score), threshold)
    actual = classification_metrics(truth, score, threshold=threshold)
    assert actual == pytest.approx(expected)


def test_single_class_auc_behavior_matches_ml_core() -> None:
    expected = compute_binary_metrics(np.ones(3), np.asarray([0.2, 0.6, 0.9]))
    actual = classification_metrics([1, 1, 1], [0.2, 0.6, 0.9])
    assert math.isnan(expected["auc"])
    assert math.isnan(actual["auc"])
    for name in ("accuracy", "precision", "recall", "f1"):
        assert actual[name] == pytest.approx(expected[name])


def test_length_validation_matches_ml_core() -> None:
    with pytest.raises(ValueError, match="same length"):
        compute_binary_metrics(np.asarray([0, 1]), np.asarray([0.5]))
    with pytest.raises(ValueError, match="same length"):
        classification_metrics([0, 1], [0.5])
