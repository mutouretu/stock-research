"""Classification, regression, and cross-sectional rank metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)


def classification_metrics(y_true: object, y_score: object, *, threshold: float = 0.5) -> dict[str, float]:
    truth = np.asarray(y_true).reshape(-1)
    score = np.asarray(y_score, dtype=float).reshape(-1)
    if len(truth) != len(score):
        raise ValueError("y_true and y_score must have the same length")
    prediction = (score >= threshold).astype(int)
    auc = float(roc_auc_score(truth, score)) if np.unique(truth).size > 1 else float("nan")
    return {
        "accuracy": float(accuracy_score(truth, prediction)),
        "precision": float(precision_score(truth, prediction, zero_division=0)),
        "recall": float(recall_score(truth, prediction, zero_division=0)),
        "f1": float(f1_score(truth, prediction, zero_division=0)),
        "auc": auc,
    }


def regression_metrics(y_true: object, y_pred: object) -> dict[str, float]:
    truth = np.asarray(y_true, dtype=float).reshape(-1)
    prediction = np.asarray(y_pred, dtype=float).reshape(-1)
    return {
        "mae": float(mean_absolute_error(truth, prediction)),
        "rmse": float(mean_squared_error(truth, prediction) ** 0.5),
        "r2": float(r2_score(truth, prediction)),
    }


def information_coefficient(y_true: object, y_score: object, *, rank: bool = False) -> float:
    frame = pd.DataFrame({"truth": np.asarray(y_true), "score": np.asarray(y_score)}).dropna()
    method = "spearman" if rank else "pearson"
    return float(frame["truth"].corr(frame["score"], method=method))
