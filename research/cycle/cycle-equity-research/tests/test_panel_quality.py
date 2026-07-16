import pandas as pd

from cycle_equity_research.quality.panels import assess_panel


def test_panel_quality_detects_future_source_availability() -> None:
    frame = pd.DataFrame(
        {
            "instrument": ["CF"],
            "date": pd.to_datetime(["2025-05-01"]),
            "panel_available_time": pd.to_datetime(["2025-05-01"]),
            "urea": [400.0],
            "urea__available_time": pd.to_datetime(["2025-05-02"]),
        }
    )
    result = assess_panel(
        frame,
        {
            "panel_id": "test",
            "time_col": "date",
            "available_time_col": "panel_available_time",
            "key_columns": ["instrument", "date"],
            "required_columns": ["urea"],
        },
    )

    assert result["status"] == "ERROR"
    assert result["point_in_time_violations"] == 1
