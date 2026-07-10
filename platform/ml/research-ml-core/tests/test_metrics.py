import pytest

from research_ml_core.evaluation import classification_metrics, information_coefficient, regression_metrics


def test_metrics() -> None:
    classification = classification_metrics([0, 1, 1, 0], [0.1, 0.8, 0.7, 0.2])
    regression = regression_metrics([1.0, 2.0], [1.0, 3.0])

    assert classification["accuracy"] == 1.0
    assert regression["mae"] == 0.5
    assert information_coefficient([1, 2, 3], [10, 20, 30], rank=True) == pytest.approx(1.0)
