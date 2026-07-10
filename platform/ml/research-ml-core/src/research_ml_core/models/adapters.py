"""Small fit/predict/predict_proba adapters based on the existing project model wrappers."""

from __future__ import annotations

from typing import Any


class SklearnAdapter:
    def __init__(self, estimator: Any):
        self.model = estimator

    def fit(self, X: Any, y: Any) -> "SklearnAdapter":
        self.model.fit(X, y)
        return self

    def predict(self, X: Any) -> Any:
        return self.model.predict(X)

    def predict_proba(self, X: Any) -> Any:
        return self.model.predict_proba(X)


class LightGBMAdapter(SklearnAdapter):
    def __init__(self, **kwargs: Any):
        try:
            import lightgbm as lgb
        except ImportError as exc:
            raise ImportError("Install research-ml-core[lightgbm] to use LightGBMAdapter") from exc
        super().__init__(lgb.LGBMClassifier(**kwargs))


class XGBoostAdapter(SklearnAdapter):
    def __init__(self, **kwargs: Any):
        try:
            from xgboost import XGBClassifier
        except ImportError as exc:
            raise ImportError("Install research-ml-core[xgboost] to use XGBoostAdapter") from exc
        super().__init__(XGBClassifier(**kwargs))
