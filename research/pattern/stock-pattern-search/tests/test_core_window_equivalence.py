from __future__ import annotations

import pandas as pd
import pytest

from research_data_core.alignment import build_history_window
from src.features.window_builder import build_window_by_asof_date


@pytest.mark.parametrize(
    ("asof", "window_size", "min_history"),
    [
        ("2026-01-04", 3, 4),
        ("2026-01-02", 2, 4),
        ("2025-12-31", 2, 1),
    ],
)
def test_application_window_matches_data_core(
    asof: str, window_size: int, min_history: int
) -> None:
    frame = pd.DataFrame(
        {
            "trade_date": ["2026-01-04", "invalid", "2026-01-01", "2026-01-03", "2026-01-02"],
            "close": [14.0, 99.0, 10.0, 13.0, 12.0],
        }
    )
    actual = build_window_by_asof_date(frame, asof, window_size, min_history)
    expected = build_history_window(
        frame,
        asof,
        time_col="trade_date",
        window_size=window_size,
        min_history=min_history,
    )
    if expected is None:
        assert actual is None
    else:
        pd.testing.assert_frame_equal(actual, expected)


def test_application_window_error_contract_is_explicit() -> None:
    frame = pd.DataFrame({"trade_date": ["2026-01-01"]})
    with pytest.raises(ValueError, match="Invalid asof_date"):
        build_window_by_asof_date(frame, "invalid", 1, 1)
    with pytest.raises(ValueError, match="window_size and min_history must be positive"):
        build_window_by_asof_date(frame, "2026-01-01", 0, 1)
