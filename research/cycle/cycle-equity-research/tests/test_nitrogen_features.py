from pathlib import Path

import pandas as pd
import pytest

from cycle_equity_research.features.nitrogen import (
    build_daily_nitrogen_features,
    build_quarterly_nitrogen_features,
    load_nitrogen_config,
    price_per_metric_ton_to_short_ton,
    theoretical_cash_spread,
)
from cycle_equity_research.features.nitrogen_validation import validate_nitrogen_features


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs/features/cf_nitrogen_economics_v1.yaml"


def test_unit_conversion_and_cash_spread_formula() -> None:
    config = load_nitrogen_config(CONFIG_PATH)
    assert price_per_metric_ton_to_short_ton(1_000.0, config) == pytest.approx(907.18474)
    assert theoretical_cash_spread(400.0, 4.0, 19.0) == 324.0


def test_configured_intensity_reconciles_to_disclosed_portfolio_anchor() -> None:
    config = load_nitrogen_config(CONFIG_PATH)
    calibration = config["calibration"]
    disclosed = float(calibration["implied_portfolio_intensity_mmbtu_per_ton"])
    configured = float(calibration["configured_fixed_weight_intensity_mmbtu_per_ton"])
    assert abs(configured / disclosed - 1) < 0.01


def test_daily_features_preserve_scenario_order_and_base_indices() -> None:
    config = load_nitrogen_config(CONFIG_PATH)
    basket = config["cf_nitrogen_basket"]["components"]
    global_base = config["global_fertilizer_index"]["base_price"]
    frame = pd.DataFrame(
        {
            "instrument": ["CF"],
            "trade_date": pd.to_datetime(["2025-01-02"]),
            "panel_available_time": pd.to_datetime(["2025-01-02"]),
            "henry_hub_spot": [4.0],
            "world_bank_urea": [global_base],
            "ams_ammonia": [basket["ams_ammonia"]["base_price"]],
            "ams_urea_46": [basket["ams_urea"]["base_price"]],
            "ams_uan_32": [basket["ams_uan32"]["base_price"]],
        }
    )

    result = build_daily_nitrogen_features(frame, config)

    assert result.loc[0, "global_fertilizer_index"] == pytest.approx(100.0)
    assert result.loc[0, "cf_nitrogen_basket"] == pytest.approx(100.0)
    assert result.loc[0, "panel_available_time"] == frame.loc[0, "panel_available_time"]
    assert (
        result.loc[0, "ams_urea_theoretical_cash_spread_low"]
        > result.loc[0, "ams_urea_theoretical_cash_spread_base"]
        > result.loc[0, "ams_urea_theoretical_cash_spread_high"]
    )


def test_quarterly_realized_proxy_retains_other_cost_residual() -> None:
    config = load_nitrogen_config(CONFIG_PATH)
    quarter = {
        "instrument": ["CF"],
        "period_end": pd.to_datetime(["2025-03-31"]),
        "panel_available_time": pd.to_datetime(["2025-05-01"]),
        "cf_all_products_realized_natural_gas_cost": [4.0],
    }
    for product in config["quarterly_cf_products"]:
        quarter[f"cf_{product}_average_selling_price"] = [400.0]
        quarter[f"cf_{product}_gross_margin_per_ton"] = [200.0]
    daily = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2025-01-02"]),
            "global_urea_theoretical_cash_spread_base": [300.0],
            "ams_ammonia_theoretical_cash_spread_base": [300.0],
            "ams_urea_theoretical_cash_spread_base": [300.0],
            "ams_uan32_theoretical_cash_spread_base": [300.0],
        }
    )

    result = build_quarterly_nitrogen_features(pd.DataFrame(quarter), daily, config)

    assert result.loc[0, "cf_granular_urea_realized_gas_spread_base"] == 324.0
    assert result.loc[0, "cf_granular_urea_other_cost_basis_residual"] == 124.0
    assert result.loc[0, "panel_available_time"] == pd.Timestamp("2025-05-01")


def test_validation_thresholds_and_scenario_ordering_are_enforced() -> None:
    config = load_nitrogen_config(CONFIG_PATH)
    values = pd.Series([1, 2, 4, 7, 11, 16, 22, 29], dtype=float)
    daily = pd.DataFrame(index=range(8))
    for prefix in config["daily_market_products"]:
        daily[f"{prefix}_theoretical_cash_spread_low"] = values + 1
        daily[f"{prefix}_theoretical_cash_spread_base"] = values
        daily[f"{prefix}_theoretical_cash_spread_high"] = values - 1
    quarterly = pd.DataFrame({"period_end": pd.date_range("2024-03-31", periods=8, freq="QE")})
    for product in config["quarterly_cf_products"]:
        quarterly[f"cf_{product}_realized_gas_spread_low"] = values + 1
        quarterly[f"cf_{product}_realized_gas_spread_base"] = values
        quarterly[f"cf_{product}_realized_gas_spread_high"] = values - 1
        quarterly[f"cf_{product}_actual_gross_margin_per_ton"] = values * 2
    quarterly["ams_urea_theoretical_cash_spread_base_quarter_mean"] = values
    quarterly["global_urea_theoretical_cash_spread_base_quarter_mean"] = values
    quarterly["cf_granular_urea_realized_price"] = values * 2
    quarterly["cf_realized_basket_gas_spread_base"] = values
    panel = pd.DataFrame(
        {"period_end": quarterly["period_end"], "cf_gross_margin": values, "cf_ebitda_proxy": values}
    )

    passed = validate_nitrogen_features(daily, quarterly, panel, config)
    assert passed["status"] == "PASS"

    daily.loc[0, "ams_urea_theoretical_cash_spread_low"] = -100
    failed = validate_nitrogen_features(daily, quarterly, panel, config)
    assert failed["status"] == "ERROR"
    assert failed["scenario_ordering_violations"] == 1
