"""Generic point-in-time alignment helpers."""

from collections.abc import Sequence

import pandas as pd


def merge_asof_by_entity(
    left: pd.DataFrame,
    right: pd.DataFrame,
    on: str,
    by: str | Sequence[str] | None = None,
    direction: str = "backward",
    preserve_left_order: bool = True,
) -> pd.DataFrame:
    """Sort inputs and perform a pandas as-of merge, optionally within entities."""
    by_columns = [by] if isinstance(by, str) else list(by or [])
    sort_columns = [on, *by_columns]
    order_column = "__research_data_core_left_order__"
    if order_column in left.columns or order_column in right.columns:
        raise ValueError(f"Reserved alignment column already exists: {order_column}")
    left_working = left.copy()
    if preserve_left_order:
        left_working[order_column] = range(len(left_working))
    left_sorted = left_working.sort_values(sort_columns).reset_index(drop=True)
    right_sorted = right.sort_values(sort_columns).reset_index(drop=True)
    merged = pd.merge_asof(
        left_sorted,
        right_sorted,
        on=on,
        by=by,
        direction=direction,
    )
    if preserve_left_order:
        merged = merged.sort_values(order_column).drop(columns=[order_column]).reset_index(drop=True)
    return merged
