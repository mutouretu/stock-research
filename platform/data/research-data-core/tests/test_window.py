import pandas as pd
import pytest

from research_data_core.alignment import build_history_window


def test_history_window_sorts_and_excludes_future_rows() -> None:
    frame = pd.DataFrame(
        {
            "event_time": ["2026-01-04", "2026-01-01", "invalid", "2026-01-03", "2026-01-02"],
            "value": [4, 1, 99, 3, 2],
        }
    )
    result = build_history_window(
        frame,
        "2026-01-03",
        time_col="event_time",
        window_size=2,
        min_history=3,
    )
    assert result is not None
    assert result["value"].tolist() == [2, 3]


def test_history_window_validates_contract() -> None:
    frame = pd.DataFrame({"other_time": ["2026-01-01"]})
    with pytest.raises(KeyError, match="Missing required column"):
        build_history_window(
            frame, "2026-01-01", time_col="event_time", window_size=1, min_history=1
        )
    assert (
        build_history_window(
            pd.DataFrame({"event_time": ["2026-01-01"]}),
            "2026-01-01",
            time_col="event_time",
            window_size=2,
            min_history=1,
        )
        is None
    )
