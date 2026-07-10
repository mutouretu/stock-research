from __future__ import annotations

import pandas as pd

from market_pattern_labeler.miners.type_n.phase2_pullback.negative import PullbackNegativeMiner
from market_pattern_labeler.miners.type_n.phase2_pullback.positive import (
    BASE_COLUMNS,
    PullbackPatternConfig,
    PullbackPatternMiner,
)


def _cfg() -> PullbackPatternConfig:
    return PullbackPatternConfig.from_dict(
        {
            "pullback": {
                "lookback_days": 30,
                "min_rise_into_high_pct": 0.10,
                "min_drawdown_pct": 0.03,
                "max_drawdown_pct": 0.25,
                "min_days_since_high": 1,
                "max_days_since_high": 12,
            },
            "diagnostics": {
                "compute_future_returns": True,
                "future_windows": [5, 10],
                "prefix": "diagnostic_",
            },
        }
    )


def _fastdrop_cfg() -> PullbackPatternConfig:
    return PullbackPatternConfig.from_dict(
        {
            "label_source": "pullback_fastdrop",
            "pullback": {
                "lookback_days": 30,
                "min_rise_into_high_pct": 0.15,
                "min_drawdown_pct": 0.06,
                "max_drawdown_pct": 0.22,
                "min_pullback_speed_pct_per_day": 0.008,
                "min_days_since_high": 1,
                "max_days_since_high": 10,
                "positive_label_subtype": "fastdrop_pullback",
            },
            "diagnostics": {
                "compute_future_returns": True,
                "future_windows": [5, 10],
                "prefix": "diagnostic_",
            },
        }
    )


def _daily(closes: list[float], vols: list[float] | None = None) -> pd.DataFrame:
    vols = vols or [1000.0] * len(closes)
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2025-01-01", periods=len(closes), freq="B"),
            "open": closes,
            "high": [value * 1.005 for value in closes],
            "low": [value * 0.995 for value in closes],
            "close": closes,
            "vol": vols,
        }
    )


def _row_for_last(df: pd.DataFrame) -> pd.Series:
    miner = PullbackPatternMiner(_cfg())
    out = miner.generate_samples("000001.SZ", df)
    return out.iloc[-1]


def test_pullback_import_paths_are_available() -> None:
    assert PullbackNegativeMiner.name == "pullback_negative"
    assert PullbackPatternMiner.name == "pullback_pattern"


def test_positive_simple_pullback_case() -> None:
    closes = [10.0] * 20 + [10.3, 10.8, 11.4, 12.0, 11.7, 11.45, 11.35, 11.4, 11.3, 11.32]

    row = _row_for_last(_daily(closes))

    assert row["label"] == 1
    assert row["label_subtype"] == "simple_pullback"
    assert row["rise_into_high_pct"] >= 0.10
    assert 0.03 <= row["pullback_depth_pct"] <= 0.25


def test_positive_fastdrop_pullback_case() -> None:
    closes = [10.0] * 20 + [10.6, 11.2, 12.0, 11.4, 11.1, 11.05, 11.0, 11.02, 11.05, 11.08]
    miner = PullbackPatternMiner(_fastdrop_cfg())

    row = miner.generate_samples("000001.SZ", _daily(closes)).iloc[-1]

    assert row["label"] == 1
    assert row["label_source"] == "pullback_fastdrop"
    assert row["label_subtype"] == "fastdrop_pullback"
    assert row["pullback_depth_pct"] >= 0.06
    assert row["pullback_speed_pct_per_day"] >= 0.008


def test_slow_pullback_negative_case() -> None:
    closes = [10.0] * 18 + [10.6, 11.2, 12.0, 11.9, 11.8, 11.7, 11.6, 11.5, 11.4, 11.3, 11.25, 11.2]
    miner = PullbackPatternMiner(_fastdrop_cfg())

    row = miner.generate_samples("000001.SZ", _daily(closes)).iloc[-1]

    assert row["label"] == 0
    assert row["label_subtype"] == "slow_pullback"


def test_no_prior_rise_negative_case() -> None:
    closes = [10.0 + (i % 3) * 0.02 for i in range(35)]

    row = _row_for_last(_daily(closes))

    assert row["label"] == 0
    assert row["label_subtype"] == "no_prior_rise"


def test_no_pullback_negative_case() -> None:
    closes = [10.0] * 20 + [10.5, 11.0, 11.4, 11.8, 12.0, 12.2, 12.3, 12.4, 12.5, 12.6]

    row = _row_for_last(_daily(closes))

    assert row["label"] == 0
    assert row["label_subtype"] == "no_pullback"


def test_too_deep_drawdown_negative_case() -> None:
    closes = [10.0] * 20 + [10.6, 11.2, 12.0, 11.0, 10.0, 9.0, 8.8, 8.7, 8.6, 8.5]

    row = _row_for_last(_daily(closes))

    assert row["label"] == 0
    assert row["label_subtype"] == "too_deep_drawdown"


def test_stale_pullback_negative_case() -> None:
    closes = [10.0] * 10 + [10.5, 11.2, 12.0] + [11.5] * 20 + [11.4, 11.35]

    row = _row_for_last(_daily(closes))

    assert row["label"] == 0
    assert row["label_subtype"] == "stale_pullback"


def test_label_generation_does_not_use_future_data() -> None:
    closes = [10.0] * 20 + [10.3, 10.8, 11.4, 12.0, 11.7, 11.45, 11.35, 11.4, 11.3, 11.32]
    asof_df = _daily(closes)
    future_df = _daily(closes + [30.0, 2.0, 50.0, 1.0, 60.0])
    miner = PullbackPatternMiner(_cfg())

    before = miner.generate_samples("000001.SZ", asof_df).iloc[-1]
    after = miner.generate_samples("000001.SZ", future_df)
    same_asof = after[after["asof_date"] == before["asof_date"]].iloc[0]

    stable_cols = [
        "label",
        "label_subtype",
        "recent_high_date",
        "recent_high",
        "days_since_high",
        "lookback_low",
        "rise_into_high_pct",
        "drawdown_from_high",
        "pullback_depth_pct",
    ]
    for col in stable_cols:
        assert same_asof[col] == before[col]


def test_output_fields_are_complete() -> None:
    closes = [10.0] * 20 + [10.3, 10.8, 11.4, 12.0, 11.7, 11.45, 11.35, 11.4, 11.3, 11.32, 11.5, 11.6]
    miner = PullbackPatternMiner(_cfg())

    out = miner.generate_samples("000001.SZ", _daily(closes))

    expected = set(BASE_COLUMNS)
    expected.update(
        {
            "diagnostic_future_max_return_5d",
            "diagnostic_future_min_return_5d",
            "diagnostic_future_close_return_5d",
            "diagnostic_future_max_return_10d",
            "diagnostic_future_min_return_10d",
            "diagnostic_future_close_return_10d",
        }
    )
    assert expected.issubset(set(out.columns))
