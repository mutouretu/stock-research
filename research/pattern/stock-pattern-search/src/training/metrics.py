from __future__ import annotations

import numpy as np
from research_ml_core.evaluation import classification_metrics


def compute_binary_metrics(
    y_true: np.ndarray,
    y_score: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, float]:
    """Compatibility wrapper around research-ml-core classification metrics."""
    return classification_metrics(y_true, y_score, threshold=threshold)
