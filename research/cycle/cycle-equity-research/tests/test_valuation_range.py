from copy import deepcopy

import numpy as np
import pandas as pd

from cycle_equity_research.valuation.range import build_valuation_range


def _config() -> dict:
    return {
        "analysis_as_of": "2025-12-31",
        "multiple_cases": {"low": 0.25, "median": 0.5, "high": 0.75},
        "implied_operations": {"reference_scenario": "base"},
        "quality": {
            "required_scenarios": ["downside", "base", "upside"],
            "identity_tolerance_usd": 1.0,
        },
    }


def _monthly() -> pd.DataFrame:
    dates = pd.date_range("2018-01-31", periods=96, freq="ME")
    multiples = np.linspace(4.0, 12.0, len(dates))
    shares = 100_000_000.0
    debt = 3_000_000_000.0
    cash = 500_000_000.0
    nci = 2_000_000_000.0
    preferred = 0.0
    price = np.linspace(40.0, 100.0, len(dates))
    market_cap = price * shares
    ev = market_cap + debt - cash + nci
    return pd.DataFrame(
        {
            "month_end": dates,
            "panel_available_time": dates,
            "fundamental_available_time": dates - pd.Timedelta(days=20),
            "reported_multiple_available": True,
            "ev_to_reported_ttm_ebitda": multiples,
            "market_price": price,
            "shares_outstanding": shares,
            "financial_debt": debt,
            "cash": cash,
            "noncontrolling_interest": nci,
            "preferred_equity": preferred,
            "enterprise_value_standard": ev,
        }
    )


def _scenarios() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "scenario": ["downside", "base", "upside"],
            "scenario_ebitda_usd_million": [300.0, 1_500.0, 3_000.0],
            "urea_usd_per_metric_ton": [200.0, 300.0, 400.0],
        }
    )


def _midcycle_report() -> dict:
    return {
        "sensitivities_usd_million": {
            "ebitda_change_per_10_usd_metric_ton_urea": 100.0
        },
        "calibration": {
            "urea_usd_per_metric_ton": {"q25": 220.0, "q50": 300.0, "q75": 380.0}
        },
    }


def _cycle_state() -> dict:
    return {
        "state": "MIXED",
        "raw_state_reason": "DATA_GAP",
        "confirmation_overlay": "DIVERGENT",
    }


def test_equity_bridge_subtracts_net_debt_and_nci() -> None:
    result = build_valuation_range(
        _monthly(), _scenarios(), _midcycle_report(), _cycle_state(), _config()
    )
    row = result.valuation_matrix.query(
        "scenario == 'base' and multiple_case == 'median'"
    ).iloc[0]
    expected_claims = 3_000_000_000 - 500_000_000 + 2_000_000_000
    assert row["raw_equity_value_usd"] == row["enterprise_value_usd"] - expected_claims
    assert row["per_share_value_usd"] == row["raw_equity_value_usd"] / 100_000_000
    assert result.diagnostics["equity_bridge_pass"]


def test_negative_raw_equity_is_floored_at_zero_per_share() -> None:
    result = build_valuation_range(
        _monthly(), _scenarios(), _midcycle_report(), _cycle_state(), _config()
    )
    downside = result.valuation_matrix.query("scenario == 'downside'")
    assert (downside["raw_equity_value_usd"] < 0).any()
    assert (downside.loc[downside["raw_equity_value_usd"] < 0, "per_share_value_usd"] == 0).all()


def test_current_ev_implies_ebitda_and_urea_at_each_multiple() -> None:
    monthly = _monthly()
    result = build_valuation_range(
        monthly, _scenarios(), _midcycle_report(), _cycle_state(), _config()
    )
    median = result.implied_assumptions.set_index("multiple_case").loc["median"]
    multiple = monthly["ev_to_reported_ttm_ebitda"].quantile(0.5)
    current_ev_million = monthly.iloc[-1]["enterprise_value_standard"] / 1_000_000
    expected_ebitda = current_ev_million / multiple
    expected_urea = 300.0 + (expected_ebitda - 1_500.0) / 10.0
    assert median["implied_ebitda_usd_million"] == expected_ebitda
    assert median["implied_urea_usd_per_metric_ton"] == expected_urea


def test_current_ev_to_scenario_ebitda_is_not_a_fair_value_multiple() -> None:
    result = build_valuation_range(
        _monthly(), _scenarios(), _midcycle_report(), _cycle_state(), _config()
    )
    ratios = result.valuation_matrix.groupby("scenario")[
        "current_ev_to_scenario_ebitda"
    ].nunique()
    assert (ratios == 1).all()
    ratio_by_scenario = result.valuation_matrix.groupby("scenario")[
        "current_ev_to_scenario_ebitda"
    ].first()
    assert ratio_by_scenario["downside"] > ratio_by_scenario["base"] > ratio_by_scenario["upside"]


def test_future_market_rows_do_not_change_as_of_result() -> None:
    baseline = build_valuation_range(
        _monthly(), _scenarios(), _midcycle_report(), _cycle_state(), _config()
    )
    future = _monthly()
    extra = future.iloc[-1:].copy()
    extra["month_end"] = pd.Timestamp("2026-01-31")
    extra["panel_available_time"] = pd.Timestamp("2026-01-31")
    extra["market_price"] = 1_000.0
    changed = build_valuation_range(
        pd.concat([future, extra], ignore_index=True),
        _scenarios(),
        _midcycle_report(),
        _cycle_state(),
        _config(),
    )
    pd.testing.assert_frame_equal(baseline.valuation_matrix, changed.valuation_matrix)
    pd.testing.assert_frame_equal(baseline.implied_assumptions, changed.implied_assumptions)
    assert baseline.snapshot == changed.snapshot


def test_cycle_state_is_context_only() -> None:
    baseline = build_valuation_range(
        _monthly(), _scenarios(), _midcycle_report(), _cycle_state(), _config()
    )
    other_state = {**_cycle_state(), "state": "EXPANSION"}
    changed = build_valuation_range(
        _monthly(), _scenarios(), _midcycle_report(), other_state, _config()
    )
    pd.testing.assert_frame_equal(baseline.valuation_matrix, changed.valuation_matrix)
    assert changed.snapshot["cycle_state"] == "EXPANSION"


def test_build_is_deterministic() -> None:
    config = deepcopy(_config())
    first = build_valuation_range(
        _monthly(), _scenarios(), _midcycle_report(), _cycle_state(), config
    )
    second = build_valuation_range(
        _monthly(), _scenarios(), _midcycle_report(), _cycle_state(), config
    )
    pd.testing.assert_frame_equal(first.valuation_matrix, second.valuation_matrix)
    pd.testing.assert_frame_equal(first.implied_assumptions, second.implied_assumptions)
    assert first.snapshot == second.snapshot
    assert first.diagnostics == second.diagnostics
