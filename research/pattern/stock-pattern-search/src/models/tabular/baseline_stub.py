from __future__ import annotations

from typing import Any

from research_ml_core.models import SklearnAdapter, load_estimator, save_estimator
from sklearn.linear_model import LogisticRegression

from src.models.base import BaseModel


class LogisticRegressionBaseline(SklearnAdapter, BaseModel):
    """Minimal LogisticRegression wrapper as tabular baseline model."""
    model_name = "logistic_regression"

    def __init__(self, **kwargs: Any):
        super().__init__(LogisticRegression(**kwargs))

    def save(self, path: str) -> None:
        save_estimator(self.model, path)

    @classmethod
    def load(cls, path: str) -> "LogisticRegressionBaseline":
        instance = cls()
        instance.model = load_estimator(path)
        return instance
