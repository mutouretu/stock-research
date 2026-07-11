from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from research_ml_core.models import SklearnAdapter, load_estimator, save_estimator
from research_ml_core.training import Trainer


def test_sklearn_adapter_and_legacy_pickle_roundtrip(tmp_path: Path) -> None:
    features = np.asarray([[0.0], [1.0], [2.0], [3.0]])
    target = np.asarray([0, 0, 1, 1])
    adapter = SklearnAdapter(LogisticRegression(random_state=7)).fit(features, target)
    before = adapter.predict_proba(features)

    path = tmp_path / "nested/model.pkl"
    save_estimator(adapter.model, path)
    restored = SklearnAdapter(load_estimator(path))
    np.testing.assert_allclose(restored.predict_proba(features), before)


def test_trainer_score_uses_probability_or_prediction_fallback() -> None:
    features = np.asarray([[0.0], [1.0], [2.0], [3.0]])
    target = np.asarray([0, 0, 1, 1])
    adapter = SklearnAdapter(LogisticRegression(random_state=7))
    trainer = Trainer(adapter).fit(features, target)
    np.testing.assert_allclose(
        trainer.predict_score(features),
        adapter.predict_proba(features)[:, 1],
    )

    class PredictOnly:
        def predict(self, values):
            return np.asarray([0.25] * len(values))

    np.testing.assert_allclose(Trainer(PredictOnly()).predict_score(features), 0.25)
