"""Point-in-time history window construction."""

from __future__ import annotations

import pandas as pd


def build_history_window(
    frame: pd.DataFrame,
    asof: object,
    *,
    time_col: str,
    window_size: int,
    min_history: int,
) -> pd.DataFrame | None:
    """Return a sorted fixed-size history ending at ``asof`` without future rows."""
    if frame is None or frame.empty:
        return None
    if time_col not in frame.columns:
        raise KeyError(f"Missing required column: {time_col}")
    if window_size <= 0 or min_history <= 0:
        raise ValueError("window_size and min_history must be positive")

    working = frame.copy()
    working[time_col] = pd.to_datetime(working[time_col], errors="coerce")
    working = working.dropna(subset=[time_col]).sort_values(time_col).reset_index(drop=True)
    if working.empty:
        return None

    asof_time = pd.to_datetime(asof, errors="coerce")
    if pd.isna(asof_time):
        raise ValueError(f"Invalid asof value: {asof}")
    history = working[working[time_col] <= asof_time]
    if len(history) < min_history:
        return None
    window = history.tail(window_size).copy()
    if len(window) < window_size:
        return None
    return window.reset_index(drop=True)
