import pandas as pd

from research_data_core.aggregation import aggregate_asof_periods, aggregate_periods


def test_aggregate_periods_supports_grouped_quarterly_means() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-03-31", "2025-04-01"]),
            "product": ["urea", "urea", "urea"],
            "value": [300.0, 400.0, 500.0],
        }
    )

    result = aggregate_periods(
        frame,
        time_col="date",
        aggregations={"value": "mean"},
        group_by="product",
    )

    assert result["period_end"].dt.strftime("%Y-%m-%d").tolist() == [
        "2025-03-31",
        "2025-06-30",
    ]
    assert result["value"].tolist() == [350.0, 500.0]


def test_aggregate_asof_periods_excludes_late_release() -> None:
    periods = pd.DataFrame(
        {"period_end": pd.to_datetime(["2025-03-31"]), "cutoff": pd.to_datetime(["2025-05-01"])}
    )
    source = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(["2025-01-31", "2025-03-31"]),
            "available_time": pd.to_datetime(["2025-02-10", "2025-05-10"]),
            "value": [300.0, 900.0],
        }
    )

    result = aggregate_asof_periods(
        periods,
        source,
        period_end_col="period_end",
        cutoff_col="cutoff",
        observation_time_col="observation_date",
        available_time_col="available_time",
        value_col="value",
        output_col="urea_mean",
    )

    assert result.loc[0, "urea_mean"] == 300.0
    assert result.loc[0, "urea_mean__count"] == 1
    assert result.loc[0, "urea_mean__available_time"] <= periods.loc[0, "cutoff"]
