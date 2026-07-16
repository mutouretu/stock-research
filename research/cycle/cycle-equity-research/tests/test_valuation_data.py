from copy import deepcopy

import numpy as np
import pandas as pd

from cycle_equity_research.valuation.panel import build_monthly_valuation_panel


def _config() -> dict:
    return {
        "analysis_end_date": "2022-12-31",
        "market_value": {
            "price_column": "cf_close",
            "shares_column": "cf_shares_outstanding",
        },
        "enterprise_value": {
            "financial_debt_column": "cf_total_debt",
            "short_term_borrowings_column": "cf_short_term_borrowings",
            "cash_column": "cf_cash",
            "noncontrolling_interest_column": "cf_noncontrolling_interest",
            "preferred_equity_column": "cf_preferred_equity",
            "lease_columns": [
                "cf_operating_lease_liability_current",
                "cf_operating_lease_liability_noncurrent",
            ],
        },
        "earnings": {"reported_ttm_ebitda_column": "cf_ebitda_proxy_ttm"},
        "quality": {"maximum_fundamental_period_age_days": 240},
    }


def _daily() -> pd.DataFrame:
    dates = pd.date_range("2020-01-31", "2022-12-31", freq="ME")
    return pd.DataFrame(
        {
            "instrument": "CF",
            "trade_date": dates,
            "cf_close": np.linspace(40.0, 75.0, len(dates)),
            "cf_adj_close": np.linspace(30.0, 75.0, len(dates)),
        }
    )


def _quarterly() -> pd.DataFrame:
    periods = pd.date_range("2019-12-31", periods=12, freq="QE")
    available = periods + pd.Timedelta(days=40)
    x = np.arange(len(periods), dtype=float)
    short = np.full(len(periods), np.nan)
    short[4] = 200_000_000.0
    return pd.DataFrame(
        {
            "period_end": periods,
            "panel_available_time": available,
            "cf_shares_outstanding": 200_000_000.0 - x * 1_000_000.0,
            "cf_total_debt": 3_000_000_000.0,
            "cf_short_term_borrowings": short,
            "cf_cash": 500_000_000.0,
            "cf_noncontrolling_interest": 2_500_000_000.0,
            "cf_preferred_equity": 0.0,
            "cf_operating_lease_liability_current": 100_000_000.0,
            "cf_operating_lease_liability_noncurrent": 300_000_000.0,
            "cf_ebitda_proxy_ttm": 2_000_000_000.0,
            "cf_operating_cash_flow": 600_000_000.0 + x,
            "cf_capex": 100_000_000.0,
            "cf_long_term_debt": 3_000_000_000.0,
        }
    )


def test_standard_ev_includes_nci_but_excludes_operating_leases() -> None:
    result = build_monthly_valuation_panel(_daily(), _quarterly(), _config()).monthly
    row = result.iloc[-1]
    expected_market_cap = row["market_price"] * row["shares_outstanding"]
    expected_ev = expected_market_cap + 3_000_000_000 - 500_000_000 + 2_500_000_000
    assert row["market_cap"] == expected_market_cap
    assert row["enterprise_value_standard"] == expected_ev
    assert row["enterprise_value_lease_adjusted"] == expected_ev + 400_000_000
    assert row["nci_and_debt_scope_adjustment"] == 2_500_000_000


def test_market_cap_uses_unadjusted_close_not_total_return_price() -> None:
    result = build_monthly_valuation_panel(_daily(), _quarterly(), _config()).monthly
    first_valid = result.dropna(subset=["shares_outstanding"]).iloc[0]
    daily = _daily().set_index("trade_date")
    assert first_valid["market_price"] == daily.loc[first_valid["month_end"], "cf_close"]
    assert first_valid["market_price"] != daily.loc[first_valid["month_end"], "cf_adj_close"]


def test_financials_are_not_visible_before_filing_date() -> None:
    result = build_monthly_valuation_panel(_daily(), _quarterly(), _config())
    january = result.monthly.loc[result.monthly["month_end"] == pd.Timestamp("2020-01-31")].iloc[0]
    february = result.monthly.loc[result.monthly["month_end"] == pd.Timestamp("2020-02-29")].iloc[0]
    assert pd.isna(january["latest_period_end"])
    assert february["latest_period_end"] == pd.Timestamp("2019-12-31")
    assert result.diagnostics["point_in_time_violations"] == 0


def test_future_quarter_mutation_cannot_change_past_valuations() -> None:
    config = _config()
    baseline = build_monthly_valuation_panel(_daily(), _quarterly(), config).monthly
    changed_quarterly = _quarterly()
    changed_quarterly.loc[changed_quarterly.index[-1], "cf_noncontrolling_interest"] *= 10
    changed = build_monthly_valuation_panel(_daily(), changed_quarterly, config).monthly
    filing = changed_quarterly.loc[changed_quarterly.index[-1], "panel_available_time"]
    past = baseline["month_end"] < filing
    pd.testing.assert_frame_equal(
        baseline.loc[past].reset_index(drop=True), changed.loc[past].reset_index(drop=True)
    )


def test_missing_short_term_borrowings_are_zero_and_flagged() -> None:
    result = build_monthly_valuation_panel(_daily(), _quarterly(), _config()).monthly
    latest = result.iloc[-1]
    assert latest["financial_debt"] == 3_000_000_000.0
    assert bool(latest["short_term_borrowings_assumed_zero"])


def test_build_is_deterministic() -> None:
    config = deepcopy(_config())
    first = build_monthly_valuation_panel(_daily(), _quarterly(), config)
    second = build_monthly_valuation_panel(_daily(), _quarterly(), config)
    pd.testing.assert_frame_equal(first.monthly, second.monthly)
    assert first.diagnostics == second.diagnostics
