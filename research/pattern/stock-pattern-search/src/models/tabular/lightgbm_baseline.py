from __future__ import annotations

from typing import Any

from research_ml_core.models import LightGBMAdapter, load_estimator, save_estimator

from src.models.base import BaseModel


class LightGBMBaseline(LightGBMAdapter, BaseModel):
    """Minimal LightGBM wrapper as tabular baseline model."""

    model_name = "lightgbm"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

    def save(self, path: str) -> None:
        save_estimator(self.model, path)

    @classmethod
    def load(cls, path: str) -> "LightGBMBaseline":
        instance = cls()
        instance.model = load_estimator(path)
        return instance
