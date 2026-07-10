from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.pipelines.w_bottom.train_long_base_breakout_baseline import (
    build_daily_features,
    build_tabular_dataset,
    describe_temporal_split,
    load_labels,
    run_pipeline,
    validate_temporal_split,
)
from src.pipelines.w_bottom.run_long_base_latest_ensemble import run_latest_ensemble_scan


def _make_daily(n: int = 760, drift: float = 0.001) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    wave = np.sin(np.linspace(0, 14, n)) * 0.4
    close = 20 + np.arange(n) * drift + wave
    open_ = close * 0.998
    high = close * 1.015
    low = close * 0.985
    vol = 100_000 + np.arange(n) * 10
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "vol": vol,
        }
    )


def _write_fixture(tmp_path):
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    _make_daily(drift=0.003).to_parquet(daily_dir / "AAA.parquet", index=False)
    _make_daily(drift=-0.001).to_parquet(daily_dir / "BBB.parquet", index=False)

    labels = pd.DataFrame(
        {
            "sample_id": [
                "AAA_2021-03-01",
                "BBB_2021-03-02",
                "AAA_2021-05-01",
                "BBB_2021-05-02",
                "AAA_2021-07-01",
                "BBB_2021-07-02",
            ],
            "ts_code": ["AAA", "BBB", "AAA", "BBB", "AAA", "BBB"],
            "asof_date": [
                "2021-03-01",
                "2021-03-02",
                "2021-05-01",
                "2021-05-02",
                "2021-07-01",
                "2021-07-02",
            ],
            "label": [1, 0, 1, 0, 1, 0],
            "label_source": ["fixture"] * 6,
            "confidence": [1.0] * 6,
            "pattern_type": ["long_base_breakout"] * 6,
            "source_miner": ["fixture"] * 6,
            "split": ["train", "train", "valid", "valid", "test", "test"],
        }
    )
    labels_path = tmp_path / "labels.csv"
    labels.to_csv(labels_path, index=False)
    return labels_path, daily_dir


def test_build_daily_features_has_expected_columns():
    features = build_daily_features(_make_daily())

    assert features["history_bars"] == 760.0
    assert "ret_252d" in features
    assert "close_vs_ma200" in features
    assert "drawdown_from_504d_high" in features
    assert np.isfinite(features["current_close"])


def test_build_tabular_dataset_uses_label_splits(tmp_path):
    labels_path, daily_dir = _write_fixture(tmp_path)
    labels = load_labels(labels_path)

    result = build_tabular_dataset(labels, daily_dir=daily_dir, min_history=252, max_window=504)

    assert result.skipped_samples == 0
    assert len(result.dataset) == 6
    assert set(result.dataset["split"]) == {"train", "valid", "test"}
    assert set(result.dataset["label"]) == {0, 1}
    assert "candidate_score" not in result.feature_columns
    assert "close_vs_ma200" in result.feature_columns


def test_temporal_split_validation_rejects_overlapping_dates(tmp_path):
    labels_path, daily_dir = _write_fixture(tmp_path)
    labels = load_labels(labels_path)
    labels.loc[labels["split"] == "valid", "asof_date"] = pd.Timestamp("2021-02-01")
    result = build_tabular_dataset(labels, daily_dir=daily_dir, min_history=252, max_window=504)

    temporal_split = describe_temporal_split(result.dataset)

    with pytest.raises(ValueError, match="Temporal split violation"):
        validate_temporal_split(temporal_split)


def test_run_pipeline_writes_dataset_model_and_report(tmp_path):
    labels_path, daily_dir = _write_fixture(tmp_path)
    output_dir = tmp_path / "outputs"

    summary = run_pipeline(
        labels_path=labels_path,
        daily_dir=daily_dir,
        output_dir=output_dir,
        min_history=252,
        max_window=504,
    )

    assert summary["samples"] == 6
    assert (output_dir / "dataset.parquet").exists()
    assert (output_dir / "sample_meta.parquet").exists()
    assert (output_dir / "X_tabular.parquet").exists()
    assert (output_dir / "model.joblib").exists()
    assert (output_dir / "evaluation_report.md").exists()
    assert (output_dir / "valid_predictions.csv").exists()

    metrics = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["train"]["samples"] == 2
    assert metrics["valid"]["samples"] == 2
    assert metrics["test"]["samples"] == 2
    assert summary["metrics"]["logistic_regression"]["train"]["samples"] == 2

    report = (output_dir / "evaluation_report.md").read_text(encoding="utf-8")
    assert "## Temporal Split Check" in report
    assert "## Metrics Summary" in report
    assert "| train | 2021-03-01 | 2021-03-02 | 2 |" in report


def test_run_pipeline_trains_multiple_models(tmp_path):
    labels_path, daily_dir = _write_fixture(tmp_path)
    output_dir = tmp_path / "outputs"

    summary = run_pipeline(
        labels_path=labels_path,
        daily_dir=daily_dir,
        output_dir=output_dir,
        min_history=252,
        max_window=504,
        models=["logistic_regression", "lightgbm", "xgboost"],
    )

    assert set(summary["metrics"]) == {"logistic_regression", "lightgbm", "xgboost"}
    assert (output_dir / "model_metrics.json").exists()
    assert (output_dir / "ensemble_lgbm_xgboost_predictions.csv").exists()
    assert (output_dir / "latest_ensemble_predictions.csv").exists()
    assert (output_dir / "latest_ensemble_candidates.csv").exists()
    assert (output_dir / "ensemble_lgbm_xgboost_report.md").exists()
    assert summary["ensemble"]["latest_date"] == "2021-07-02"
    for model_name in ["logistic_regression", "lightgbm", "xgboost"]:
        model_dir = output_dir / "models" / model_name
        assert (model_dir / "model.joblib").exists()
        assert (model_dir / "metrics.json").exists()
        assert (model_dir / "valid_predictions.csv").exists()
        assert summary["metrics"][model_name]["test"]["samples"] == 2

    ensemble = pd.read_csv(output_dir / "ensemble_lgbm_xgboost_predictions.csv")
    assert {"lgbm_score", "xgb_score", "ensemble_score", "model_agreement"} <= set(ensemble.columns)


def test_latest_ensemble_scan_writes_universe_outputs(tmp_path):
    labels_path, daily_dir = _write_fixture(tmp_path)
    train_output_dir = tmp_path / "train_outputs"
    scan_output_dir = tmp_path / "scan_outputs"
    run_pipeline(
        labels_path=labels_path,
        daily_dir=daily_dir,
        output_dir=train_output_dir,
        min_history=252,
        max_window=504,
        models=["lightgbm", "xgboost"],
    )

    summary = run_latest_ensemble_scan(
        daily_dir=daily_dir,
        model_root=train_output_dir / "models",
        output_dir=scan_output_dir,
        min_history=252,
        max_window=504,
    )

    assert summary["symbols_scanned"] == 2
    assert (scan_output_dir / "latest_universe_predictions.csv").exists()
    assert (scan_output_dir / "latest_universe_candidates.csv").exists()
    assert (scan_output_dir / "latest_universe_report.md").exists()
    predictions = pd.read_csv(scan_output_dir / "latest_universe_predictions.csv")
    assert {"ts_code", "lgbm_score", "xgb_score", "ensemble_score"} <= set(predictions.columns)
