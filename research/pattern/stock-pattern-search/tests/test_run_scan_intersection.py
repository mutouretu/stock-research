from __future__ import annotations

import pandas as pd
import pytest

from src.pipelines.run_scan_intersection import merge_ranked_predictions


def test_merge_ranked_predictions_keeps_shared_metadata_once() -> None:
    lgbm = pd.DataFrame(
        [
            {
                "sample_id": "a_2026-07-01",
                "ts_code": "a",
                "asof_date": "2026-07-01",
                "high_ratio_750": 0.95,
                "model_score": 0.75,
                "score": 0.8,
            },
            {
                "sample_id": "b_2026-07-01",
                "ts_code": "b",
                "asof_date": "2026-07-01",
                "high_ratio_750": 1.05,
                "model_score": 0.85,
                "score": 0.9,
            },
        ]
    )
    xgb = pd.DataFrame(
        [
            {
                "sample_id": "a_2026-07-01",
                "ts_code": "a",
                "asof_date": "2026-07-01",
                "high_ratio_750": 0.95,
                "model_score": 0.65,
                "score": 0.7,
            },
            {
                "sample_id": "b_2026-07-01",
                "ts_code": "b",
                "asof_date": "2026-07-01",
                "high_ratio_750": 1.05,
                "model_score": 0.55,
                "score": 0.6,
            },
        ]
    )

    merged = merge_ranked_predictions(lgbm, xgb)

    assert "high_ratio_750" in merged.columns
    assert "high_ratio_750_x" not in merged.columns
    assert "high_ratio_750_y" not in merged.columns
    assert {
        "score_lgbm",
        "score_xgb",
        "model_score_lgbm",
        "model_score_xgb",
        "score_mean",
        "score_min",
        "rank_sum",
    }.issubset(merged.columns)
    assert merged.loc[0, "ts_code"] == "a"


def test_merge_ranked_predictions_rejects_empty_intersection() -> None:
    lgbm = pd.DataFrame([{"sample_id": "a", "ts_code": "a", "asof_date": "2026-07-01", "score": 0.8}])
    xgb = pd.DataFrame([{"sample_id": "b", "ts_code": "b", "asof_date": "2026-07-01", "score": 0.7}])

    with pytest.raises(ValueError, match="No intersection"):
        merge_ranked_predictions(lgbm, xgb)
