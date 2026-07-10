"""Forward-return based labels."""

from __future__ import annotations

import pandas as pd


def forward_return(series: pd.Series, periods: int = 1) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.shift(-int(periods)) / values - 1.0


def binary_classification_label(
    series: pd.Series,
    *,
    periods: int = 1,
    threshold: float = 0.0,
) -> pd.Series:
    target = forward_return(series, periods)
    result = (target > threshold).astype("Int64")
    return result.mask(target.isna())


def regression_target(series: pd.Series, *, periods: int = 1) -> pd.Series:
    return forward_return(series, periods)
