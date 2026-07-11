"""Small trainer extracted from the existing fit/evaluate workflow."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np


class Trainer:
    def __init__(self, model: Any, evaluator: Callable[[Any, Any], dict[str, float]] | None = None):
        self.model = model
        self.evaluator = evaluator

    def fit(self, X: Any, y: Any) -> "Trainer":
        self.model.fit(X, np.asarray(y))
        return self

    def predict_score(self, X: Any) -> np.ndarray:
        try:
            values = np.asarray(self.model.predict_proba(X))
            score = values[:, 1] if values.ndim == 2 and values.shape[1] > 1 else values.squeeze()
        except (AttributeError, NotImplementedError):
            score = np.asarray(self.model.predict(X)).squeeze()
        return np.asarray(score, dtype=float).reshape(-1)

    def evaluate(self, X: Any, y: Any) -> dict[str, float]:
        if self.evaluator is None:
            raise ValueError("evaluator is required")
        return {key: float(value) for key, value in self.evaluator(np.asarray(y), self.predict_score(X)).items()}
