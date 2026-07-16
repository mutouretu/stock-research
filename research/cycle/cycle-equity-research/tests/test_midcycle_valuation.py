from copy import deepcopy

import numpy as np
import pandas as pd

from cycle_equity_research.valuation.midcycle import (
    build_midcycle_ebitda_scenarios,
    scenario_sensitivities,
)


PRODUCTS = ["ammonia", "granular_urea", "uan", "ammonium_nitrate"]
VOLUME_PRODUCTS = [*PRODUCTS, "other"]


def _config() -> dict:
    return {
        "analysis_as_of": "2025-12-31",
        "market_conversion": {
            "usd_per_metric_ton_to_usd_per_short_ton": 0.9,
            "henry_hub_current_quarter_weight": 0.5,
            "henry_hub_previous_quarter_weight": 0.5,
        },
        "products": PRODUCTS,
        "volume_products": VOLUME_PRODUCTS,
        "scenarios": {
            "downside": {
                "urea_quantile": 0.25,
                "henry_hub_quantile": 0.75,
                "annual_volume_quantile": 0.25,
                "other_cost_quantile": 0.75,
                "other_product_margin_quantile": 0.25,
                "ebitda_conversion_quantile": 0.25,
            },
            "base": {
                "urea_quantile": 0.5,
                "henry_hub_quantile": 0.5,
                "annual_volume_quantile": 0.5,
                "other_cost_quantile": 0.5,
                "other_product_margin_quantile": 0.5,
                "ebitda_conversion_quantile": 0.5,
            },
            "upside": {
                "urea_quantile": 0.75,
                "henry_hub_quantile": 0.25,
                "annual_volume_quantile": 0.75,
                "other_cost_quantile": 0.25,
                "other_product_margin_quantile": 0.75,
                "ebitda_conversion_quantile": 0.75,
            },
        },
        "quality": {"identity_tolerance_usd_million": 1e-6},
    }


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    periods = pd.date_range("2016-03-31", periods=40, freq="QE")
    x = np.arange(len(periods), dtype=float)
    quarterly = pd.DataFrame(
        {
            "instrument": "CF",
            "period_end": periods,
            "panel_available_time": periods + pd.Timedelta(days=40),
            "world_bank_urea_quarter_mean": 180.0 + 8.0 * x,
            "henry_hub_quarter_mean": 5.0 - 0.05 * x,
            "cf_gross_profit": (350.0 + 10.0 * x) * 1_000_000.0,
            "cf_ebitda_proxy": (450.0 + 12.0 * x) * 1_000_000.0,
            "cf_ebitda_proxy_ttm": (1_800.0 + 48.0 * x) * 1_000_000.0,
        }
    )
    shares = {
        "ammonia": 0.22,
        "granular_urea": 0.24,
        "uan": 0.36,
        "ammonium_nitrate": 0.08,
        "other": 0.10,
    }
    for product, share in shares.items():
        quarterly[f"cf_{product}_sales_volume"] = (
            (4_500.0 + 5.0 * x) * share
        )
    nitrogen = quarterly[["instrument", "period_end", "panel_available_time"]].copy()
    for index, product in enumerate(PRODUCTS):
        nitrogen[f"cf_{product}_other_cost_basis_residual"] = (
            100.0 + index * 10.0 + x
        )
    nitrogen["cf_other_gross_margin_per_ton"] = 30.0 + x
    return quarterly, nitrogen


def _bridge_report() -> dict:
    return {
        "final_parameters": {
            "realized_gas_cost": {"intercept": 0.0, "slope": 1.0},
            "realized_price": {
                product: {"intercept": 50.0, "slope": 1.0}
                for product in PRODUCTS
            },
            "unit_margin": {
                product: {"gas_intensity": intensity}
                for product, intensity in zip(PRODUCTS, [28.0, 19.0, 13.0, 14.0])
            },
        }
    }


def test_scenarios_follow_declared_favorable_order() -> None:
    quarterly, nitrogen = _frames()
    result = build_midcycle_ebitda_scenarios(
        quarterly, nitrogen, _bridge_report(), _config()
    )
    values = result.scenarios.set_index("scenario")["scenario_ebitda_usd_million"]
    assert values["downside"] < values["base"] < values["upside"]
    assert result.diagnostics["scenario_ordering_pass"]


def test_product_contributions_reconcile_exactly_to_scenario_gross_profit() -> None:
    quarterly, nitrogen = _frames()
    result = build_midcycle_ebitda_scenarios(
        quarterly, nitrogen, _bridge_report(), _config()
    )
    contributions = result.product_bridge.groupby("scenario")["gross_profit_usd_million"].sum()
    summary = result.scenarios.set_index("scenario")["gross_profit_usd_million"]
    pd.testing.assert_series_equal(summary.sort_index(), contributions.sort_index())
    assert result.diagnostics["gross_profit_identity_pass"]


def test_base_ebitda_is_gross_profit_plus_conversion_residual() -> None:
    quarterly, nitrogen = _frames()
    result = build_midcycle_ebitda_scenarios(
        quarterly, nitrogen, _bridge_report(), _config()
    )
    base = result.scenarios.set_index("scenario").loc["base"]
    assert base["scenario_ebitda_usd_million"] == (
        base["gross_profit_usd_million"] + base["ebitda_conversion_usd_million"]
    )


def test_future_filings_do_not_enter_calibration() -> None:
    quarterly, nitrogen = _frames()
    cutoff = pd.Timestamp(_config()["analysis_as_of"])
    expected = int((quarterly["panel_available_time"] <= cutoff).sum())
    result = build_midcycle_ebitda_scenarios(
        quarterly, nitrogen, _bridge_report(), _config()
    )
    assert result.diagnostics["calibration_quarters"] == expected
    assert result.diagnostics["point_in_time_violations"] == 0
    assert result.calibration["last_period"][:10] == str(
        quarterly.loc[quarterly["panel_available_time"] <= cutoff, "period_end"].max().date()
    )


def test_sensitivities_have_expected_signs() -> None:
    quarterly, nitrogen = _frames()
    config = _config()
    result = build_midcycle_ebitda_scenarios(
        quarterly, nitrogen, _bridge_report(), config
    )
    sensitivities = scenario_sensitivities(result, _bridge_report(), config)
    assert sensitivities["ebitda_change_per_10_usd_metric_ton_urea"] > 0
    assert sensitivities["ebitda_change_per_1_usd_mmbtu_henry_hub"] < 0
    assert sensitivities["gross_profit_change_per_1_percent_volume"] > 0


def test_engine_does_not_accept_stock_price_as_an_input() -> None:
    quarterly, nitrogen = _frames()
    baseline = build_midcycle_ebitda_scenarios(
        quarterly, nitrogen, _bridge_report(), _config()
    )
    quarterly["cf_stock_price"] = np.linspace(1.0, 1_000.0, len(quarterly))
    changed = build_midcycle_ebitda_scenarios(
        quarterly, nitrogen, _bridge_report(), _config()
    )
    pd.testing.assert_frame_equal(baseline.scenarios, changed.scenarios)


def test_build_is_deterministic() -> None:
    quarterly, nitrogen = _frames()
    config = deepcopy(_config())
    first = build_midcycle_ebitda_scenarios(
        quarterly, nitrogen, _bridge_report(), config
    )
    second = build_midcycle_ebitda_scenarios(
        quarterly, nitrogen, _bridge_report(), config
    )
    pd.testing.assert_frame_equal(first.scenarios, second.scenarios)
    pd.testing.assert_frame_equal(first.product_bridge, second.product_bridge)
    assert first.calibration == second.calibration
    assert first.diagnostics == second.diagnostics
