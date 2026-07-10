from __future__ import annotations

from typing import Optional, Union

import pandas as pd
from research_data_core.alignment import build_history_window


DateLike = Union[str, pd.Timestamp]


def build_window_by_asof_date(
    df: pd.DataFrame,
    asof_date: DateLike,
    window_size: int,
    min_history: int,
) -> Optional[pd.DataFrame]:
    """Compatibility wrapper for data-core point-in-time history windows."""
    try:
        return build_history_window(
            df,
            asof_date,
            time_col="trade_date",
            window_size=window_size,
            min_history=min_history,
        )
    except ValueError as error:
        if str(error).startswith("Invalid asof value:"):
            raise ValueError(f"Invalid asof_date: {asof_date}") from error
        raise
