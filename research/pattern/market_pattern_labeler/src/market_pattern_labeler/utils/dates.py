from __future__ import annotations

import pandas as pd


def to_trade_datetime(series: pd.Series) -> pd.Series:
    """Convert series to datetime and normalize format tolerance."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    return pd.to_datetime(series, errors="coerce")


def to_ymd(ts: pd.Timestamp) -> str:
    if pd.isna(ts):
        return ""
    return pd.Timestamp(ts).strftime("%Y-%m-%d")
