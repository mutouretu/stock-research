from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

KEY_COLUMNS = ["sample_id", "ts_code", "asof_date"]


def _normalize_daily_dates(daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out = out.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    return out


def _read_daily(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        daily = pd.read_parquet(path).copy()
    except Exception:
        return pd.DataFrame()
    if "trade_date" not in daily.columns or "close" not in daily.columns:
        return pd.DataFrame()
    daily = _normalize_daily_dates(daily)
    for col in ["open", "high", "low", "close", "ma_bfq_20", "ma_bfq_60", "ma_bfq_120", "ma_bfq_250"]:
        if col in daily.columns:
            daily[col] = pd.to_numeric(daily[col], errors="coerce")
    return daily


def _series_or_rolling(daily: pd.DataFrame, col: str, close: pd.Series, window: int) -> pd.Series:
    if col in daily.columns:
        values = pd.to_numeric(daily[col], errors="coerce")
        return values.where(values.notna(), close.rolling(window, min_periods=window).mean())
    return close.rolling(window, min_periods=window).mean()


def _window_return(close: pd.Series, idx: int, window: int) -> float:
    prior_idx = idx - int(window)
    if prior_idx < 0:
        return float("nan")
    current = close.iloc[idx]
    prior = close.iloc[prior_idx]
    if pd.isna(current) or pd.isna(prior) or prior == 0:
        return float("nan")
    return float(current / prior - 1.0)


def _slope(values: pd.Series, idx: int, lag: int) -> float:
    prior_idx = idx - int(lag)
    if prior_idx < 0:
        return float("nan")
    current = values.iloc[idx]
    prior = values.iloc[prior_idx]
    if pd.isna(current) or pd.isna(prior) or prior == 0:
        return float("nan")
    return float(current / prior - 1.0)


def _position_in_range(high: pd.Series, low: pd.Series, close: pd.Series, idx: int, window: int) -> float:
    start = max(0, idx - int(window) + 1)
    high_window = high.iloc[start : idx + 1]
    low_window = low.iloc[start : idx + 1]
    high_max = high_window.max()
    low_min = low_window.min()
    current = close.iloc[idx]
    if pd.isna(high_max) or pd.isna(low_min) or pd.isna(current) or high_max == low_min:
        return float("nan")
    return float((current - low_min) / (high_max - low_min))


def _bool_score(flags: list[bool]) -> float:
    if not flags:
        return float("nan")
    return float(sum(flags) / len(flags))


def _row_metrics(
    daily: pd.DataFrame,
    *,
    asof_date: str,
    short_window: int,
    mid_window: int,
    long_window: int,
    slope_lag: int,
    return_window: int,
    position_window: int,
    min_return: float,
    min_mid_ma_slope: float,
    min_position: float,
    require_above_mid_ma: bool,
) -> Dict[str, Any]:
    if daily.empty:
        return _empty_metrics()

    history = daily[daily["trade_date"] <= asof_date].copy()
    if history.empty:
        return _empty_metrics()

    idx = len(history) - 1
    close = pd.to_numeric(history["close"], errors="coerce")
    high = pd.to_numeric(history["high"] if "high" in history.columns else history["close"], errors="coerce")
    low = pd.to_numeric(history["low"] if "low" in history.columns else history["close"], errors="coerce")
    ma_short = _series_or_rolling(history, f"ma_bfq_{short_window}", close, short_window)
    ma_mid = _series_or_rolling(history, f"ma_bfq_{mid_window}", close, mid_window)
    ma_long = _series_or_rolling(history, f"ma_bfq_{long_window}", close, long_window)

    current_close = close.iloc[idx]
    current_ma_short = ma_short.iloc[idx]
    current_ma_mid = ma_mid.iloc[idx]
    current_ma_long = ma_long.iloc[idx]
    price_vs_mid = current_close / current_ma_mid - 1.0 if pd.notna(current_close) and pd.notna(current_ma_mid) and current_ma_mid else float("nan")
    price_vs_long = current_close / current_ma_long - 1.0 if pd.notna(current_close) and pd.notna(current_ma_long) and current_ma_long else float("nan")
    mid_slope = _slope(ma_mid, idx, slope_lag)
    long_slope = _slope(ma_long, idx, slope_lag)
    ret = _window_return(close, idx, return_window)
    position = _position_in_range(high, low, close, idx, position_window)

    flags = [
        bool(pd.notna(ret) and ret >= min_return),
        bool(pd.notna(mid_slope) and mid_slope >= min_mid_ma_slope),
        bool(pd.notna(position) and position >= min_position),
    ]
    if require_above_mid_ma:
        flags.append(bool(pd.notna(price_vs_mid) and price_vs_mid >= 0))

    return {
        "trend_data_date": history.iloc[idx]["trade_date"],
        "trend_close": current_close,
        "trend_ma_short": current_ma_short,
        "trend_ma_mid": current_ma_mid,
        "trend_ma_long": current_ma_long,
        "trend_price_vs_mid_ma": price_vs_mid,
        "trend_price_vs_long_ma": price_vs_long,
        "trend_mid_ma_slope": mid_slope,
        "trend_long_ma_slope": long_slope,
        "trend_return": ret,
        "trend_position": position,
        "trend_midlong_score": _bool_score(flags),
        "trend_midlong_pass": all(flags),
    }


def _empty_metrics() -> Dict[str, Any]:
    return {
        "trend_data_date": pd.NA,
        "trend_close": pd.NA,
        "trend_ma_short": pd.NA,
        "trend_ma_mid": pd.NA,
        "trend_ma_long": pd.NA,
        "trend_price_vs_mid_ma": pd.NA,
        "trend_price_vs_long_ma": pd.NA,
        "trend_mid_ma_slope": pd.NA,
        "trend_long_ma_slope": pd.NA,
        "trend_return": pd.NA,
        "trend_position": pd.NA,
        "trend_midlong_score": pd.NA,
        "trend_midlong_pass": False,
    }


def load_midlong_trend_values(
    rows: pd.DataFrame,
    *,
    raw_data_dir: Path,
    short_window: int = 20,
    mid_window: int = 60,
    long_window: int = 120,
    slope_lag: int = 20,
    return_window: int = 120,
    position_window: int = 120,
    min_return: float = 0.0,
    min_mid_ma_slope: float = 0.0,
    min_position: float = 0.45,
    require_above_mid_ma: bool = True,
) -> pd.DataFrame:
    """Load mid/long uptrend review fields for phase2 candidates."""
    review_rows = rows.copy()
    missing = [col for col in KEY_COLUMNS if col not in review_rows.columns]
    if missing:
        raise ValueError(f"midlong trend reviewer missing required columns: {missing}")

    output_rows: List[Dict[str, Any]] = []
    for ts_code, group in review_rows[KEY_COLUMNS].drop_duplicates().groupby("ts_code"):
        daily = _read_daily(raw_data_dir / f"{ts_code}.parquet")
        for _, row in group.iterrows():
            metrics = _row_metrics(
                daily,
                asof_date=str(row["asof_date"]),
                short_window=short_window,
                mid_window=mid_window,
                long_window=long_window,
                slope_lag=slope_lag,
                return_window=return_window,
                position_window=position_window,
                min_return=min_return,
                min_mid_ma_slope=min_mid_ma_slope,
                min_position=min_position,
                require_above_mid_ma=require_above_mid_ma,
            )
            output_rows.append(
                {
                    "sample_id": row["sample_id"],
                    "ts_code": row["ts_code"],
                    "asof_date": row["asof_date"],
                    **metrics,
                }
            )
    return pd.DataFrame(output_rows)


__all__ = ["load_midlong_trend_values"]
