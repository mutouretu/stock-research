"""Generic point-in-time alignment helpers."""

from collections.abc import Sequence

import pandas as pd


def merge_asof_by_entity(
    left: pd.DataFrame,
    right: pd.DataFrame,
    on: str,
    by: str | Sequence[str] | None = None,
    direction: str = "backward",
) -> pd.DataFrame:
    """Sort inputs and perform a pandas as-of merge, optionally within entities."""
    by_columns = [by] if isinstance(by, str) else list(by or [])
    sort_columns = [on, *by_columns]
    left_sorted = left.sort_values(sort_columns).reset_index(drop=True)
    right_sorted = right.sort_values(sort_columns).reset_index(drop=True)
    return pd.merge_asof(
        left_sorted,
        right_sorted,
        on=on,
        by=by,
        direction=direction,
    )
