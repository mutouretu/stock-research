import pandas as pd

from cycle_equity_research.instruments.cf.financials import extract_quarterly_financials


def test_extract_quarterly_financials_derives_q4_without_future_filings() -> None:
    facts = pd.DataFrame(
        {
            "concept": ["Revenues"] * 5,
            "value": [100.0, 220.0, 350.0, 500.0, 999.0],
            "period_start": pd.to_datetime(
                ["2025-01-01", "2025-01-01", "2025-01-01", "2025-01-01", "2025-10-01"]
            ),
            "period_end": pd.to_datetime(
                ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2025-12-31"]
            ),
            "filing_date": pd.to_datetime(
                ["2025-05-01", "2025-08-01", "2025-11-01", "2026-02-20", "2027-02-20"]
            ),
            "form": ["10-Q", "10-Q", "10-Q", "10-K", "10-K"],
        }
    )
    periods = pd.DataFrame(
        {
            "period_end": pd.to_datetime(["2025-12-31"]),
            "panel_available_time": pd.to_datetime(["2026-02-20"]),
        }
    )

    result = extract_quarterly_financials(
        facts,
        periods,
        [{"output_col": "revenue", "concepts": ["Revenues"], "kind": "flow"}],
    )

    assert result.loc[0, "revenue"] == 150.0
    assert result.loc[0, "revenue__available_time"] == pd.Timestamp("2026-02-20")
