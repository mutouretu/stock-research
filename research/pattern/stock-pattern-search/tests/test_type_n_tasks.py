from __future__ import annotations

import json

import pandas as pd

from src.pipelines.type_n.tasks import (
    build_phase1_pool_from_cache_task,
    build_phase1_pool_task,
    generate_two_phase_report_task,
    merge_final_candidates_task,
)


def test_build_phase1_pool_task_deduplicates_hits(tmp_path):
    hits_path = tmp_path / "phase1_hits.csv"
    pool_path = tmp_path / "phase1_pool.csv"
    status_path = tmp_path / "pool_status.json"
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-12",
                "anchor_date": "2026-05-08",
                "ts_code": "000001.SZ",
                "sample_id": "000001.SZ_2026-05-08",
                "phase1_rank": 2,
                "phase1_score_lgbm": 0.8,
                "phase1_score_xgb": 0.7,
                "phase1_score_mean": 0.75,
                "phase1_score_min": 0.7,
            },
            {
                "target_date": "2026-05-12",
                "anchor_date": "2026-05-11",
                "ts_code": "000001.SZ",
                "sample_id": "000001.SZ_2026-05-11",
                "phase1_rank": 1,
                "phase1_score_lgbm": 0.9,
                "phase1_score_xgb": 0.8,
                "phase1_score_mean": 0.85,
                "phase1_score_min": 0.8,
            },
        ]
    ).to_csv(hits_path, index=False)

    status = build_phase1_pool_task(
        phase1_hits_path=hits_path,
        output_path=pool_path,
        status_path=status_path,
        target_date="2026-05-12",
    )

    pool = pd.read_csv(pool_path)
    assert status["ok"] is True
    assert len(pool) == 1
    assert pool.loc[0, "phase1_hit_count"] == 2
    assert pool.loc[0, "first_phase1_date"] == "2026-05-08"
    assert pool.loc[0, "last_phase1_date"] == "2026-05-11"
    assert pool.loc[0, "best_phase1_score_mean"] == 0.85
    assert json.loads(status_path.read_text())["phase1_pool_count"] == 1


def test_build_phase1_pool_from_cache_filters_target_anchor_dates(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    dates = pd.date_range("2026-05-01", periods=7, freq="D")
    pd.DataFrame(
        {
            "trade_date": dates,
            "open": [10.0] * 7,
            "high": [10.5] * 7,
            "low": [9.5] * 7,
            "close": [10.0, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6],
            "vol": [1000.0] * 7,
        }
    ).to_parquet(raw_dir / "000001.SZ.parquet")

    cache_path = tmp_path / "phase1_cache.csv"
    hits_path = tmp_path / "phase1_hits.csv"
    pool_path = tmp_path / "phase1_pool.csv"
    status_path = tmp_path / "pool_from_cache_status.json"
    pd.DataFrame(
        [
            {
                "anchor_date": "2026-05-02",
                "ts_code": "000001.SZ",
                "sample_id": "000001.SZ_2026-05-02",
                "phase1_rank": 1,
                "phase1_score_lgbm": 0.7,
                "phase1_score_xgb": 0.8,
                "phase1_score_mean": 0.75,
                "phase1_score_min": 0.7,
            },
            {
                "anchor_date": "2026-05-04",
                "ts_code": "000002.SZ",
                "sample_id": "000002.SZ_2026-05-04",
                "phase1_rank": 1,
                "phase1_score_lgbm": 0.9,
                "phase1_score_xgb": 0.8,
                "phase1_score_mean": 0.85,
                "phase1_score_min": 0.8,
            },
            {
                "anchor_date": "2026-05-05",
                "ts_code": "000001.SZ",
                "sample_id": "000001.SZ_2026-05-05",
                "phase1_rank": 2,
                "phase1_score_lgbm": 0.95,
                "phase1_score_xgb": 0.85,
                "phase1_score_mean": 0.90,
                "phase1_score_min": 0.85,
            },
        ]
    ).to_csv(cache_path, index=False)

    status = build_phase1_pool_from_cache_task(
        phase1_cache_path=cache_path,
        target_date="2026-05-06",
        anchor_lookback_days=2,
        raw_daily_dir=raw_dir,
        hits_output_path=hits_path,
        pool_output_path=pool_path,
        status_path=status_path,
    )

    hits = pd.read_csv(hits_path)
    pool = pd.read_csv(pool_path)
    assert status["anchor_dates"] == ["2026-05-04", "2026-05-05"]
    assert hits["anchor_date"].tolist() == ["2026-05-04", "2026-05-05"]
    assert set(pool["ts_code"]) == {"000001.SZ", "000002.SZ"}
    assert set(pool["target_date"]) == {"2026-05-06"}


def test_merge_final_candidates_prefers_adjusted_phase2_score(tmp_path):
    pool_path = tmp_path / "phase1_pool.csv"
    scores_path = tmp_path / "phase2_scores.csv"
    final_path = tmp_path / "final_candidates.csv"
    status_path = tmp_path / "final_status.json"
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-12",
                "ts_code": "000001.SZ",
                "first_phase1_date": "2026-05-08",
                "last_phase1_date": "2026-05-11",
                "phase1_hit_count": 2,
                "best_phase1_score_mean": 0.85,
                "latest_phase1_score_mean": 0.85,
            }
        ]
    ).to_csv(pool_path, index=False)
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-12",
                "ts_code": "000001.SZ",
                "sample_id": "000001.SZ_2026-05-12",
                "phase2_score_mean": 0.4,
                "phase2_score_min": 0.3,
                "adjusted_phase2_score": 0.9,
            }
        ]
    ).to_csv(scores_path, index=False)

    status = merge_final_candidates_task(
        phase1_pool_path=pool_path,
        phase2_scores_path=scores_path,
        output_path=final_path,
        status_path=status_path,
    )

    final = pd.read_csv(final_path)
    assert status["ok"] is True
    assert final.loc[0, "final_rank"] == 1
    assert final.loc[0, "final_score"] == 0.9
    assert "adjusted_phase2_score" in final.loc[0, "reason"]


def test_generate_two_phase_report_task_writes_markdown(tmp_path):
    hits_path = tmp_path / "phase1_hits.csv"
    pool_path = tmp_path / "phase1_pool.csv"
    scores_path = tmp_path / "phase2_scores.csv"
    final_path = tmp_path / "final_candidates.csv"
    phase1_status_path = tmp_path / "phase1_status.json"
    report_path = tmp_path / "type_n_two_phase_report.md"

    pd.DataFrame([{"target_date": "2026-05-12", "ts_code": "000001.SZ"}]).to_csv(hits_path, index=False)
    pd.DataFrame([{"target_date": "2026-05-12", "ts_code": "000001.SZ"}]).to_csv(pool_path, index=False)
    pd.DataFrame([{"target_date": "2026-05-12", "ts_code": "000001.SZ"}]).to_csv(scores_path, index=False)
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-12",
                "ts_code": "000001.SZ",
                "final_rank": 1,
                "final_score": 0.9,
                "phase2_score_mean": 0.4,
                "best_phase1_score_mean": 0.85,
                "decision": "candidate",
            }
        ]
    ).to_csv(final_path, index=False)
    phase1_status_path.write_text(
        json.dumps(
            {
                "ok": True,
                "target_date": "2026-05-12",
                "anchor_lookback_days": 20,
                "anchor_dates": ["2026-05-08", "2026-05-11"],
                "warnings": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )

    result = generate_two_phase_report_task(
        phase1_hits_path=hits_path,
        phase1_pool_path=pool_path,
        phase2_scores_path=scores_path,
        final_candidates_path=final_path,
        status_paths=[phase1_status_path],
        output_path=report_path,
    )

    text = report_path.read_text(encoding="utf-8")
    assert result["ok"] is True
    assert "# Type-N Two Phase Report" in text
    assert "000001.SZ" in text
