from __future__ import annotations

import pandas as pd
import pytest

from research_data_core.schema import require_columns
from src.data.validator import validate_daily_df, validate_labels_df


def test_core_and_daily_validator_accept_required_columns() -> None:
    frame = pd.DataFrame(
        {
            "trade_date": ["2026-01-02"],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "vol": [100.0],
        }
    )
    require_columns(frame, ("trade_date", "open", "high", "low", "close", "vol"))
    result = validate_daily_df(frame)
    assert pd.api.types.is_datetime64_any_dtype(result["trade_date"])


def test_daily_missing_columns_retains_application_error_contract() -> None:
    frame = pd.DataFrame({"trade_date": ["2026-01-02"], "close": [10.5]})
    with pytest.raises(
        ValueError,
        match=r"daily missing required columns: \['open', 'high', 'low', 'vol'\]",
    ):
        validate_daily_df(frame)
    assert validate_daily_df(frame, raise_on_error=False) is frame


def test_labels_missing_columns_retains_application_error_contract() -> None:
    frame = pd.DataFrame({"label": [1]})
    with pytest.raises(
        ValueError,
        match=r"labels missing required columns: \['sample_id', 'ts_code', 'asof_date'\]",
    ):
        validate_labels_df(frame)
    assert validate_labels_df(frame, raise_on_error=False) is frame
