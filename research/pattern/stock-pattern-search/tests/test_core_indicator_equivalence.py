from __future__ import annotations

import pandas as pd
import pytest

from research_ml_core.features import add_return_features, add_rolling_features
from src.features.indicators import add_basic_indicators


def _core_expected(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"], errors="coerce")
    prepared = prepared.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    if "close" not in prepared:
        return prepared
    featured = add_return_features(prepared, column="close", periods=(1,), fill_method="pad")
    featured = add_rolling_features(
        featured, column="close", windows=(5, 20), min_periods=1
    )
    prepared["ret_1d"] = featured["close_return_1"]
    prepared["ma_5"] = featured["close_rolling_mean_5"]
    prepared["ma_20"] = featured["close_rolling_mean_20"]
    return prepared


def test_basic_indicators_match_configured_ml_core_primitives() -> None:
    frame = pd.DataFrame(
        {
            "trade_date": ["2026-01-03", "invalid", "2026-01-01", "2026-01-02"],
            "close": ["12", "999", "10", None],
            "vol": [3, 999, 1, 2],
        }
    )
    original = frame.copy(deep=True)
    actual = add_basic_indicators(frame)
    expected = _core_expected(frame)

    pd.testing.assert_frame_equal(actual, expected)
    pd.testing.assert_frame_equal(frame, original)


def test_basic_indicators_without_close_keeps_prepared_columns() -> None:
    frame = pd.DataFrame({"trade_date": ["2026-01-02", "2026-01-01"], "vol": [2, 1]})
    pd.testing.assert_frame_equal(add_basic_indicators(frame), _core_expected(frame))


def test_basic_indicators_missing_time_error_is_preserved() -> None:
    with pytest.raises(KeyError, match="Missing required column: trade_date"):
        add_basic_indicators(pd.DataFrame({"close": [10.0]}))
