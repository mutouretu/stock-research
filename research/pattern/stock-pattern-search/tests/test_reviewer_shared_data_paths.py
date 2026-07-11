from pathlib import Path

import pandas as pd

from src.reviewers.type_n.phase1_breakout.penalties import apply_post_penalties


def test_post_penalties_resolve_legacy_shared_data_path_from_monorepo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    shared_data_dir = tmp_path / "storage" / "shared_data"
    raw_dir = shared_data_dir / "raw" / "daily" / "cache"
    raw_dir.mkdir(parents=True)
    monkeypatch.setenv("STOCK_RESEARCH_SHARED_DATA_DIR", str(shared_data_dir))

    asof_date = "2026-01-03"
    pd.DataFrame(
        {
            "trade_date": pd.date_range(end=asof_date, periods=3, freq="D"),
            "vol": [100.0, 100.0, 300.0],
        }
    ).to_parquet(raw_dir / "000001.SZ.parquet")

    rows = pd.DataFrame(
        [
            {
                "sample_id": f"000001.SZ_{asof_date}",
                "ts_code": "000001.SZ",
                "asof_date": asof_date,
                "score": 0.8,
            }
        ]
    )
    config = {
        "volume": {
            "enabled": True,
            "raw_data_dir": "../shared_data/raw/daily/cache",
            "ma_window": 2,
            "short_window": 1,
            "score_col": "score",
            "output_score_col": "adjusted_score",
            "ratio_col": "volume_ratio",
            "streak_col": "volume_spike_streak",
            "strength": {"threshold": 2.0, "sharpness": 3.0, "max_boost": 0.25},
            "streak": {"spike_ratio": 2.0, "threshold": 3.0, "sharpness": 1.5},
        }
    }
    monorepo_project_root = tmp_path / "research" / "pattern" / "stock-pattern-search"

    out = apply_post_penalties(rows, config, monorepo_project_root)

    assert out.loc[0, "volume_ratio"] == 3.0
    assert out.loc[0, "volume_spike_streak"] == 1
    assert out.loc[0, "adjusted_score"] > rows.loc[0, "score"]
