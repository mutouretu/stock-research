import pandas as pd

from research_data_core.alignment import align_latest_available


def test_align_latest_available_never_exposes_value_before_release() -> None:
    calendar = pd.DataFrame({"date": pd.to_datetime(["2025-05-05", "2025-05-07", "2025-05-08"])})
    source = pd.DataFrame(
        {
            "period_end": pd.to_datetime(["2025-03-31"]),
            "filing_date": pd.to_datetime(["2025-05-07"]),
            "revenue": [1_000.0],
        }
    )

    result = align_latest_available(
        calendar,
        source,
        calendar_time_col="date",
        available_time_col="filing_date",
        value_columns=["period_end", "revenue"],
    )

    assert pd.isna(result.loc[0, "revenue"])
    assert result.loc[1, "revenue"] == 1_000.0
    assert result.loc[2, "source_available_time"] <= result.loc[2, "date"]
