from __future__ import annotations

import numpy as np
import pandas as pd

from src.reviewers.new_high import NewHighReviewConfig, evaluate_new_high_review


def _make_daily(last_close: float, amount: float = 150_000_000.0) -> pd.DataFrame:
    n = 760
    close = np.linspace(10.0, 12.0, n)
    close[-1] = last_close
    high = close * 1.01
    high[20] = 13.0
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2023-01-01", periods=n, freq="D"),
            "high": high,
            "close": close,
            "amount": np.full(n, amount),
        }
    )


def test_new_high_reviewer_passes_near_prior_high() -> None:
    result = evaluate_new_high_review(_make_daily(last_close=12.0), "2025-01-29")

    assert result["new_high_review_pass"] is True
    assert result["new_high_review_reason"] == "pass"
    assert result["high_ratio_750"] >= 0.90


def test_new_high_reviewer_rejects_low_rebound() -> None:
    result = evaluate_new_high_review(_make_daily(last_close=8.0), "2025-01-29")

    assert result["new_high_review_pass"] is False
    assert result["new_high_review_reason"] == "high_ratio_below_min"
    assert result["high_ratio_750"] < 0.90


def test_new_high_reviewer_rejects_low_liquidity() -> None:
    result = evaluate_new_high_review(_make_daily(last_close=12.0, amount=10_000_000.0), "2025-01-29")

    assert result["new_high_review_pass"] is False
    assert result["new_high_review_reason"] == "avg_amount_below_min"


def test_new_high_reviewer_supports_custom_thresholds() -> None:
    cfg = NewHighReviewConfig(min_high_ratio=0.50, min_avg_amount=1.0)
    result = evaluate_new_high_review(_make_daily(last_close=8.0, amount=10.0), "2025-01-29", cfg)

    assert result["new_high_review_pass"] is True


def test_new_high_reviewer_prefers_confirmed_breakout_over_extended_move() -> None:
    cfg = NewHighReviewConfig(min_avg_amount=1.0)

    near = evaluate_new_high_review(_make_daily(last_close=13.5), "2025-01-29", cfg)
    far = evaluate_new_high_review(_make_daily(last_close=15.5), "2025-01-29", cfg)
    not_breakout = evaluate_new_high_review(_make_daily(last_close=12.5), "2025-01-29", cfg)

    assert near["new_high_score_reason"] == "confirmed_breakout_ideal"
    assert near["new_high_score_factor"] > far["new_high_score_factor"]
    assert near["new_high_score_factor"] > not_breakout["new_high_score_factor"]
    assert far["new_high_score_reason"] == "extended_breakout"
    assert not_breakout["new_high_score_reason"] == "near_high_not_breakout"
