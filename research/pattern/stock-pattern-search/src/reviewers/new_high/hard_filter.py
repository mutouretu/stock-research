from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class NewHighReviewConfig:
    rolling_window: int = 750
    min_periods: int = 250
    min_high_ratio: float = 0.90
    max_high_ratio: float = 1.30
    require_amount: bool = True
    avg_amount_window: int = 20
    min_avg_amount: float = 100_000_000.0
    enable_score_adjustment: bool = True
    breakout_ratio: float = 1.00
    ideal_min_ratio: float = 1.02
    ideal_max_ratio: float = 1.08
    far_ratio: float = 1.20
    pre_breakout_min_factor: float = 0.65
    pre_breakout_max_factor: float = 0.95
    ideal_factor: float = 1.25
    far_factor: float = 0.70
    very_far_factor: float = 0.45

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NewHighReviewConfig":
        return cls(**{k: v for k, v in (data or {}).items() if k in cls.__annotations__})


def evaluate_new_high_review(
    df: pd.DataFrame,
    asof_date: str | pd.Timestamp,
    config: NewHighReviewConfig | None = None,
) -> dict[str, Any]:
    """Apply a hard near-3-year-high reviewer to one stock history.

    The training labeler uses Tushare `amount` in thousand-yuan units. In this
    project daily data is normalized to yuan, so the default liquidity threshold
    is 100,000,000 yuan.
    """
    cfg = config or NewHighReviewConfig()
    fields = _empty_fields()

    daily = _prepare_daily(df)
    asof_ts = pd.to_datetime(asof_date, errors="coerce")
    if pd.isna(asof_ts):
        return {**fields, "new_high_review_reason": "invalid_asof_date"}

    history = daily[daily["trade_date"] <= asof_ts].copy()
    if history.empty:
        return {**fields, "new_high_review_reason": "asof_not_covered"}

    previous = history.iloc[:-1]
    if len(previous) < int(cfg.min_periods):
        return {**fields, "new_high_review_reason": "insufficient_history"}

    current = history.iloc[-1]
    close = _to_float(current.get("close"))
    high_prev = _to_float(previous["high"].tail(int(cfg.rolling_window)).max())
    if close is None or close <= 0 or high_prev is None or high_prev <= 0:
        return {**fields, "new_high_review_reason": "invalid_price"}

    high_ratio = close / high_prev
    distance_to_high = 1.0 - high_ratio
    fields.update(
        {
            "high_3y_prev": high_prev,
            "high_ratio_750": high_ratio,
            "distance_to_high_750": distance_to_high,
            **_score_adjustment_fields(high_ratio, cfg),
        }
    )

    if high_ratio < float(cfg.min_high_ratio):
        return {**fields, "new_high_review_reason": "high_ratio_below_min"}
    if high_ratio > float(cfg.max_high_ratio):
        return {**fields, "new_high_review_reason": "high_ratio_above_max"}

    if bool(cfg.require_amount):
        if "amount" not in history.columns:
            return {**fields, "new_high_review_reason": "missing_amount"}
        avg_amount = _to_float(history["amount"].tail(int(cfg.avg_amount_window)).mean())
        fields["avg_amount_20d"] = avg_amount
        if avg_amount is None:
            return {**fields, "new_high_review_reason": "invalid_amount"}
        if avg_amount < float(cfg.min_avg_amount):
            return {**fields, "new_high_review_reason": "avg_amount_below_min"}

    return {**fields, "new_high_review_pass": True, "new_high_review_reason": "pass"}


def _score_adjustment_fields(high_ratio: float, cfg: NewHighReviewConfig) -> dict[str, Any]:
    if not bool(cfg.enable_score_adjustment):
        return {
            "new_high_score_factor": 1.0,
            "new_high_score_reason": "disabled",
        }

    min_ratio = float(cfg.min_high_ratio)
    breakout_ratio = float(cfg.breakout_ratio)
    ideal_min = float(cfg.ideal_min_ratio)
    ideal_max = float(cfg.ideal_max_ratio)
    far_ratio = float(cfg.far_ratio)
    max_ratio = float(cfg.max_high_ratio)

    if high_ratio < breakout_ratio:
        factor = _linear_interpolate(
            high_ratio,
            left_x=min_ratio,
            right_x=breakout_ratio,
            left_y=float(cfg.pre_breakout_min_factor),
            right_y=float(cfg.pre_breakout_max_factor),
        )
        reason = "near_high_not_breakout"
    elif high_ratio < ideal_min:
        factor = _linear_interpolate(
            high_ratio,
            left_x=breakout_ratio,
            right_x=ideal_min,
            left_y=1.0,
            right_y=float(cfg.ideal_factor),
        )
        reason = "fresh_breakout"
    elif high_ratio <= ideal_max:
        factor = float(cfg.ideal_factor)
        reason = "confirmed_breakout_ideal"
    elif high_ratio <= far_ratio:
        factor = _linear_interpolate(
            high_ratio,
            left_x=ideal_max,
            right_x=far_ratio,
            left_y=float(cfg.ideal_factor),
            right_y=float(cfg.far_factor),
        )
        reason = "extended_breakout"
    else:
        factor = _linear_interpolate(
            high_ratio,
            left_x=far_ratio,
            right_x=max_ratio,
            left_y=float(cfg.far_factor),
            right_y=float(cfg.very_far_factor),
        )
        reason = "too_extended"

    return {
        "new_high_score_factor": max(0.0, float(factor)),
        "new_high_score_reason": reason,
    }


def _prepare_daily(df: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_date", "high", "close"}
    if df is None or df.empty or not required.issubset(df.columns):
        return pd.DataFrame(columns=["trade_date", "high", "close"])

    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce")
    out = out.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    for col in ["high", "close", "amount"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _empty_fields() -> dict[str, Any]:
    return {
        "new_high_review_pass": False,
        "new_high_review_reason": "not_evaluated",
        "high_3y_prev": pd.NA,
        "high_ratio_750": pd.NA,
        "distance_to_high_750": pd.NA,
        "avg_amount_20d": pd.NA,
        "new_high_score_factor": pd.NA,
        "new_high_score_reason": pd.NA,
    }


def _to_float(value: Any) -> float | None:
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _linear_interpolate(
    value: float,
    *,
    left_x: float,
    right_x: float,
    left_y: float,
    right_y: float,
) -> float:
    if right_x <= left_x:
        return right_y
    clipped = min(max(value, left_x), right_x)
    ratio = (clipped - left_x) / (right_x - left_x)
    return left_y + ratio * (right_y - left_y)
