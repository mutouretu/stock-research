"""Frequency conversion helpers for normalized time series."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


def aggregate_asof_periods(
    periods: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    period_end_col: str,
    cutoff_col: str,
    observation_time_col: str,
    available_time_col: str,
    value_col: str,
    output_col: str,
    aggregation: str = "mean",
) -> pd.DataFrame:
    """Aggregate observations within each period using only values available by its cutoff."""
    supported = {"mean", "last", "sum", "min", "max"}
    if aggregation not in supported:
        raise ValueError(f"Unsupported aggregation {aggregation!r}; expected {sorted(supported)}")
    _require(periods, [period_end_col, cutoff_col])
    _require(observations, [observation_time_col, available_time_col, value_col])
    source = observations.copy()
    source[observation_time_col] = pd.to_datetime(source[observation_time_col], errors="coerce")
    source[available_time_col] = pd.to_datetime(source[available_time_col], errors="coerce")
    source[value_col] = pd.to_numeric(source[value_col], errors="coerce")
    source = source.dropna(subset=[observation_time_col, available_time_col, value_col])

    rows: list[dict] = []
    for period in periods[[period_end_col, cutoff_col]].itertuples(index=False, name=None):
        period_end, cutoff = map(pd.Timestamp, period)
        period_start = period_end.to_period("Q").start_time
        eligible = source[
            source[observation_time_col].between(period_start, period_end)
            & (source[available_time_col] <= cutoff)
        ].sort_values(observation_time_col)
        value = getattr(eligible[value_col], aggregation)() if not eligible.empty else float("nan")
        rows.append(
            {
                period_end_col: period_end,
                output_col: value,
                f"{output_col}__last_observation": (
                    eligible[observation_time_col].max() if not eligible.empty else pd.NaT
                ),
                f"{output_col}__available_time": (
                    eligible[available_time_col].max() if not eligible.empty else pd.NaT
                ),
                f"{output_col}__count": len(eligible),
            }
        )
    return pd.DataFrame(rows)


def aggregate_periods(
    frame: pd.DataFrame,
    *,
    time_col: str,
    aggregations: Mapping[str, str],
    frequency: str = "Q",
    group_by: str | list[str] | None = None,
    period_end_col: str = "period_end",
) -> pd.DataFrame:
    """Aggregate values into calendar periods and label rows by period end."""
    groups = [group_by] if isinstance(group_by, str) else list(group_by or [])
    required = [time_col, *groups, *aggregations]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")
    if not aggregations:
        raise ValueError("At least one aggregation is required")

    working = frame[required].copy()
    working[time_col] = pd.to_datetime(working[time_col], errors="coerce")
    working = working.dropna(subset=[time_col, *groups])
    period = working[time_col].dt.to_period(frequency)
    working[period_end_col] = period.dt.end_time.dt.normalize()
    result = (
        working.groupby([*groups, period_end_col], as_index=False, dropna=False)
        .agg(dict(aggregations))
        .sort_values([*groups, period_end_col])
    )
    return result.reset_index(drop=True)


def _require(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")
