import pandas as pd

from src.pipelines.type_n.phase_tracking import (
    _anchor_dates_from_config,
    _build_pool_score_rows,
    _build_stock_resource_pool,
    _track_dates_for_anchor,
)


def test_phase_tracking_builds_anchor_dates_before_target_date():
    all_dates = ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-07", "2026-04-08"]

    anchor_dates = _anchor_dates_from_config(
        {"target_date": "2026-04-08", "anchor_lookback_days": 3},
        all_dates,
    )

    assert anchor_dates == ["2026-04-02", "2026-04-03", "2026-04-07"]


def test_phase_tracking_tracks_from_anchor_to_target_date():
    all_dates = ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-07", "2026-04-08"]

    track_dates = _track_dates_for_anchor(
        all_dates,
        anchor_date="2026-04-02",
        max_forward_days=10,
        target_date="2026-04-08",
    )

    assert track_dates == ["2026-04-03", "2026-04-07", "2026-04-08"]


def test_phase_tracking_target_date_respects_max_watch_days():
    all_dates = ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-07", "2026-04-08"]

    track_dates = _track_dates_for_anchor(
        all_dates,
        anchor_date="2026-04-01",
        max_forward_days=2,
        target_date="2026-04-08",
    )

    assert track_dates == ["2026-04-02", "2026-04-03"]


def test_phase_tracking_builds_pool_score_rows_without_status_machine():
    item = pd.Series(
        {
            "ts_code": "000001.SZ",
            "asof_date": "2026-04-01",
            "pool_entry_date": "2026-04-01",
            "phase1_rank": 1,
            "phase1_score_lgbm": 0.9,
            "phase1_score_xgb": 0.8,
            "phase1_score_mean": 0.85,
            "phase1_score_min": 0.8,
            "phase1_seen_count": 1,
            "phase1_seen_dates": "2026-04-01",
        }
    )
    daily_df = pd.DataFrame(
        {
            "trade_date": ["2026-04-01", "2026-04-02", "2026-04-03"],
            "open": [10.0, 10.1, 10.2],
            "high": [10.1, 10.2, 10.3],
            "low": [9.9, 10.0, 10.1],
            "close": [10.0, 10.1, 10.2],
        }
    )

    rows = _build_pool_score_rows(
        item,
        daily_df,
        phase2_scores={
            ("000001.SZ", "2026-04-03"): {
                "phase2_score_lgbm": 0.81,
                "phase2_score_xgb": 0.73,
                "phase2_score_mean": 0.77,
                "phase2_score_min": 0.73,
            }
        },
        score_dates=["2026-04-03"],
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["sample_id"] == "000001.SZ_2026-04-03"
    assert row["asof_date"] == "2026-04-03"
    assert row["days_since_anchor"] == 2
    assert row["phase2_score_mean"] == 0.77
    assert "status_after" not in row
    assert "decision" not in row


def test_phase_tracking_resource_pool_keeps_one_row_per_stock():
    daily_anchor_top = pd.DataFrame(
        [
            {
                "sample_id": "a_2026-04-15",
                "ts_code": "a",
                "asof_date": "2026-04-15",
                "phase1_rank": 5,
                "phase1_score_lgbm": 0.90,
                "phase1_score_xgb": 0.80,
                "phase1_score_mean": 0.85,
                "phase1_score_min": 0.80,
            },
            {
                "sample_id": "a_2026-04-16",
                "ts_code": "a",
                "asof_date": "2026-04-16",
                "phase1_rank": 1,
                "phase1_score_lgbm": 0.98,
                "phase1_score_xgb": 0.94,
                "phase1_score_mean": 0.96,
                "phase1_score_min": 0.94,
            },
            {
                "sample_id": "b_2026-04-16",
                "ts_code": "b",
                "asof_date": "2026-04-16",
                "phase1_rank": 2,
                "phase1_score_lgbm": 0.93,
                "phase1_score_xgb": 0.91,
                "phase1_score_mean": 0.92,
                "phase1_score_min": 0.91,
            },
        ]
    )

    pool = _build_stock_resource_pool(daily_anchor_top)

    assert len(pool) == 2
    row = pool[pool["ts_code"] == "a"].iloc[0]
    assert row["asof_date"] == "2026-04-15"
    assert row["pool_entry_date"] == "2026-04-15"
    assert row["phase1_seen_count"] == 2
    assert row["phase1_seen_dates"] == "2026-04-15;2026-04-16"
    assert row["last_seen_phase1_date"] == "2026-04-16"
    assert row["latest_phase1_rank"] == 1
    assert row["best_phase1_date"] == "2026-04-16"
