from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from research_ml_core.models import SklearnAdapter, load_estimator, save_estimator
from research_ml_core.training import Trainer as CoreTrainer
from src.models.tabular.baseline_stub import LogisticRegressionBaseline
from src.models.factory import build_model, load_model
from src.training.trainer import Trainer as ApplicationTrainer


def _sample() -> tuple[np.ndarray, np.ndarray]:
    return (
        np.asarray([[0.0, 1.0], [1.0, 0.0], [2.0, 1.0], [3.0, 0.0]]),
        np.asarray([0, 0, 1, 1]),
    )


def test_logistic_wrapper_matches_core_adapter() -> None:
    features, target = _sample()
    application = LogisticRegressionBaseline(random_state=7, max_iter=200).fit(features, target)
    core = SklearnAdapter(LogisticRegression(random_state=7, max_iter=200)).fit(features, target)

    np.testing.assert_array_equal(application.predict(features), core.predict(features))
    np.testing.assert_allclose(application.predict_proba(features), core.predict_proba(features))


def test_logistic_pickle_is_bidirectionally_compatible(tmp_path: Path) -> None:
    features, target = _sample()
    application = LogisticRegressionBaseline(random_state=7, max_iter=200).fit(features, target)
    application_path = tmp_path / "application.pkl"
    application.save(str(application_path))
    core = SklearnAdapter(load_estimator(application_path))
    np.testing.assert_allclose(core.predict_proba(features), application.predict_proba(features))

    core_path = tmp_path / "core.pkl"
    save_estimator(core.model, core_path)
    restored_application = LogisticRegressionBaseline.load(str(core_path))
    np.testing.assert_allclose(
        restored_application.predict_proba(features), application.predict_proba(features)
    )


def test_application_trainer_score_matches_core(tmp_path: Path) -> None:
    features, target = _sample()
    model = LogisticRegressionBaseline(random_state=7, max_iter=200).fit(features, target)
    application = ApplicationTrainer(model, evaluator=None, output_dir=str(tmp_path))
    core = CoreTrainer(model)
    np.testing.assert_allclose(application._predict_score(features), core.predict_score(features))


@pytest.mark.parametrize(
    ("model_name", "kwargs"),
    [
        ("logistic_regression", {"random_state": 7, "max_iter": 200}),
        ("lightgbm", {"random_state": 7, "n_estimators": 5, "verbosity": -1}),
        (
            "xgboost",
            {"random_state": 7, "n_estimators": 5, "max_depth": 2, "n_jobs": 1},
        ),
    ],
)
def test_registered_model_pickle_roundtrip(
    model_name: str, kwargs: dict[str, object], tmp_path: Path
) -> None:
    features, target = _sample()
    model = build_model(model_name, **kwargs).fit(features, target)
    before = model.predict_proba(features)
    path = tmp_path / model_name / "model.pkl"
    model.save(str(path))
    restored = load_model(model_name, str(path))
    np.testing.assert_allclose(restored.predict_proba(features), before)
