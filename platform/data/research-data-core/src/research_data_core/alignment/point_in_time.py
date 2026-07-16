"""Point-in-time alignment using when a source value became observable."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def align_latest_available(
    calendar: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    calendar_time_col: str,
    available_time_col: str,
    value_columns: Sequence[str],
    by: str | Sequence[str] | None = None,
    matched_available_time_col: str = "source_available_time",
) -> pd.DataFrame:
    """Attach the latest source row available at each calendar timestamp.

    The source observation date is intentionally not used as the join key. This prevents a value
    from appearing before its release date. Callers may include the observation date in
    ``value_columns`` when lineage needs to retain it.
    """
    by_columns = [by] if isinstance(by, str) else list(by or [])
    required_left = [calendar_time_col, *by_columns]
    required_right = [available_time_col, *by_columns, *value_columns]
    _require_columns(calendar, required_left)
    _require_columns(observations, required_right)
    if matched_available_time_col in calendar.columns:
        raise ValueError(f"Calendar already contains {matched_available_time_col!r}")

    left = calendar.copy()
    right = observations.copy()
    left[calendar_time_col] = _timestamps(left[calendar_time_col])
    right[available_time_col] = _timestamps(right[available_time_col])
    left = left.dropna(subset=[calendar_time_col, *by_columns])
    right = right.dropna(subset=[available_time_col, *by_columns])
    right[matched_available_time_col] = right[available_time_col]

    join_key = "__point_in_time__"
    order_key = "__left_order__"
    if join_key in left.columns or join_key in right.columns or order_key in left.columns:
        raise ValueError("Input uses a reserved point-in-time alignment column")
    left[order_key] = range(len(left))
    left = left.rename(columns={calendar_time_col: join_key})
    right = right.rename(columns={available_time_col: join_key})
    keep = [join_key, *by_columns, matched_available_time_col, *value_columns]
    right = right[keep].drop_duplicates([join_key, *by_columns], keep="last")
    sort_columns = [join_key, *by_columns]

    aligned = pd.merge_asof(
        left.sort_values(sort_columns),
        right.sort_values(sort_columns),
        on=join_key,
        by=by_columns or None,
        direction="backward",
        allow_exact_matches=True,
    )
    aligned = aligned.sort_values(order_key).drop(columns=[order_key])
    return aligned.rename(columns={join_key: calendar_time_col}).reset_index(drop=True)


def _timestamps(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    return parsed.dt.tz_localize(None)


def _require_columns(frame: pd.DataFrame, columns: Sequence[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")
