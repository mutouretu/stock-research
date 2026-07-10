"""Generic pandas feature transformations extracted from stock research workflows."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def add_return_features(
    frame: pd.DataFrame,
    *,
    column: str = "close",
    periods: Iterable[int] = (1,),
    fill_method: str | None = None,
) -> pd.DataFrame:
    out = frame.copy()
    values = pd.to_numeric(out[column], errors="coerce")
    if fill_method in ("pad", "ffill"):
        values = values.ffill()
    elif fill_method in ("backfill", "bfill"):
        values = values.bfill()
    elif fill_method is not None:
        raise ValueError(
            "fill_method must be one of None, 'pad', 'ffill', 'backfill', or 'bfill'"
        )
    for period in periods:
        out[f"{column}_return_{period}"] = values.pct_change(int(period), fill_method=None)
    return out


def add_lag_features(
    frame: pd.DataFrame,
    *,
    columns: Iterable[str],
    lags: Iterable[int] = (1,),
) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        values = pd.to_numeric(out[column], errors="coerce")
        for lag in lags:
            out[f"{column}_lag_{lag}"] = values.shift(int(lag))
    return out


def add_rolling_features(
    frame: pd.DataFrame,
    *,
    column: str = "close",
    windows: Iterable[int] = (5, 20),
    min_periods: int | None = None,
) -> pd.DataFrame:
    out = frame.copy()
    values = pd.to_numeric(out[column], errors="coerce")
    for window in windows:
        required = int(window) if min_periods is None else int(min_periods)
        rolling = values.rolling(int(window), min_periods=required)
        out[f"{column}_rolling_mean_{window}"] = rolling.mean()
        out[f"{column}_rolling_std_{window}"] = rolling.std(ddof=0)
    return out


def rolling_zscore(series: pd.Series, window: int, *, min_periods: int | None = None) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    required = int(window if min_periods is None else min_periods)
    rolling = values.rolling(int(window), min_periods=required)
    mean = rolling.mean()
    std = rolling.std(ddof=0).replace(0.0, np.nan)
    return (values - mean) / std


def rolling_volatility(
    series: pd.Series,
    window: int,
    *,
    periods_per_year: int | None = None,
) -> pd.Series:
    returns = pd.to_numeric(series, errors="coerce").pct_change(fill_method=None)
    volatility = returns.rolling(int(window), min_periods=int(window)).std(ddof=0)
    if periods_per_year is not None:
        volatility = volatility * np.sqrt(int(periods_per_year))
    return volatility


def winsorize_series(series: pd.Series, *, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    if not 0 <= lower <= upper <= 1:
        raise ValueError("expected 0 <= lower <= upper <= 1")
    values = pd.to_numeric(series, errors="coerce")
    return values.clip(lower=values.quantile(lower), upper=values.quantile(upper))


def normalize_series(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    std = values.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(np.nan, index=values.index, dtype=float)
    return (values - values.mean()) / std
