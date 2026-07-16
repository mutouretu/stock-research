from pathlib import Path

import pandas as pd
import yaml

from cycle_equity_research.panels.curation import (
    build_core_monthly_panel,
    build_core_quarterly_panel,
    build_tactical_context_panel,
)
from cycle_equity_research.quality.curated import assess_curated_panels


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _config() -> dict:
    return yaml.safe_load((PROJECT_ROOT / "configs/panels/cf_curated.yaml").read_text())


def test_monthly_panel_truncates_stale_urea_and_respects_filing_time() -> None:
    dates = pd.to_datetime(["2025-01-31", "2025-04-30"])
    daily = pd.DataFrame(
        {
            "instrument": ["CF", "CF"],
            "trade_date": dates,
            "panel_available_time": dates,
            "cf_adj_close": [80.0, 90.0],
            "henry_hub_spot": [3.0, 3.5],
            "henry_hub_spot__available_time": dates,
            "world_bank_urea__available_time": pd.to_datetime(
                ["2025-01-14", "2025-01-14"]
            ),
            "corn_futures": [450.0, 460.0],
            "corn_futures__available_time": dates,
        }
    )
    nitrogen = daily[["instrument", "trade_date", "panel_available_time"]].copy()
    nitrogen["global_urea_theoretical_cash_spread_base"] = [300.0, 310.0]
    quarterly = pd.DataFrame(
        {
            "instrument": ["CF", "CF", "CF"],
            "period_end": pd.to_datetime(["2024-06-30", "2024-09-30", "2024-12-31"]),
            "panel_available_time": pd.to_datetime(
                ["2024-08-01", "2024-11-01", "2025-02-20"]
            ),
            "cf_gross_margin": [0.20, 0.25, 0.40],
        }
    )
    quarterly_nitrogen = quarterly[
        ["instrument", "period_end", "panel_available_time"]
    ].copy()
    quarterly_nitrogen["cf_realized_basket_gas_spread_base"] = [100.0, 120.0, 200.0]

    result = build_core_monthly_panel(
        daily, nitrogen, quarterly, quarterly_nitrogen, _config()
    )

    january = result.loc[result["month_end"] == pd.Timestamp("2025-01-31")].iloc[0]
    april = result.loc[result["month_end"] == pd.Timestamp("2025-04-30")].iloc[0]
    assert january["latest_cf_period_end"] == pd.Timestamp("2024-09-30")
    assert january["latest_cf_realized_basket_gas_spread"] == 120.0
    assert pd.isna(april["global_urea_gas_spread_month_mean"])
    assert bool(april["global_urea_gas_spread_month_mean__missing"])


def test_quarterly_panel_exposes_only_configured_model_features() -> None:
    config = _config()
    quarterly = pd.DataFrame(
        {
            "instrument": ["CF", "CF"],
            "period_end": pd.to_datetime(["2024-12-31", "2025-03-31"]),
            "panel_available_time": pd.to_datetime(["2025-02-20", "2025-05-01"]),
            "cf_ammonia_sales_volume": [1.0, 2.0],
            "cf_granular_urea_sales_volume": [2.0, 3.0],
            "cf_uan_sales_volume": [3.0, 4.0],
            "cf_ammonium_nitrate_sales_volume": [4.0, 5.0],
            "cf_other_sales_volume": [5.0, 6.0],
            "cf_gross_margin": [0.2, 0.3],
            "cf_revenue": [1_000.0, 1_100.0],
            "cf_ebitda_proxy": [200.0, 250.0],
        }
    )
    nitrogen = quarterly[["instrument", "period_end", "panel_available_time"]].copy()
    nitrogen["global_urea_theoretical_cash_spread_base_quarter_mean"] = [200.0, 210.0]
    nitrogen["cf_realized_basket_gas_spread_base"] = [190.0, 205.0]
    nitrogen["cf_realized_natural_gas_cost"] = [3.0, 3.5]

    result = build_core_quarterly_panel(quarterly, nitrogen, config)

    assert result.loc[1, "cf_total_sales_volume"] == 20.0
    assert all(feature in result for feature in config["quarterly_model_features"])
    assert "ams_urea_theoretical_cash_spread_base" not in result
    assert result.loc[1, "available_model_feature_count"] == 5


def test_tactical_panel_masks_stale_ams_without_promoting_it_to_core() -> None:
    trade_date = pd.to_datetime(["2025-02-15"])
    daily = pd.DataFrame(
        {
            "instrument": ["CF"],
            "trade_date": trade_date,
            "panel_available_time": trade_date,
            "ams_ammonia": [500.0],
            "ams_ammonia__available_time": pd.to_datetime(["2025-01-01"]),
            "ams_urea_46": [450.0],
            "ams_urea_46__available_time": pd.to_datetime(["2025-01-01"]),
            "ams_uan_32": [350.0],
            "ams_uan_32__available_time": pd.to_datetime(["2025-01-01"]),
            "corn_planted_acres": [90.0],
            "corn_planted_acres__available_time": pd.to_datetime(["2024-06-30"]),
            "soybean_planted_acres": [85.0],
            "soybean_planted_acres__available_time": pd.to_datetime(["2024-06-30"]),
            "spring_application_season": [True],
            "fall_application_season": [False],
        }
    )
    nitrogen = daily[["instrument", "trade_date", "panel_available_time"]].copy()
    nitrogen["ams_urea_theoretical_cash_spread_base"] = [300.0]
    nitrogen["cf_nitrogen_basket"] = [110.0]
    quarterly_nitrogen = pd.DataFrame(
        {
            "period_end": pd.to_datetime(["2024-12-31"]),
            "panel_available_time": pd.to_datetime(["2025-02-01"]),
            "cf_granular_urea_other_cost_basis_residual": [25.0],
        }
    )

    result = build_tactical_context_panel(daily, nitrogen, quarterly_nitrogen, _config())

    assert pd.isna(result.loc[0, "ams_urea_46"])
    assert pd.isna(result.loc[0, "ams_urea_theoretical_cash_spread_base"])
    assert pd.isna(result.loc[0, "cf_nitrogen_basket"])
    assert bool(result.loc[0, "ams_urea_46__stale"])
    assert result.loc[0, "latest_residual_period_end"] == pd.Timestamp("2024-12-31")


def test_quality_gate_rejects_tactical_source_promoted_to_model() -> None:
    config = _config()
    config["quality"].update(
        {
            "monthly_min_rows": 1,
            "quarterly_min_rows": 1,
            "monthly_min_complete_rows": 1,
            "quarterly_min_complete_rows": 1,
        }
    )
    month = {feature: [1.0] for feature in config["monthly_model_features"]}
    month.update(
        {
            "instrument": ["CF"],
            "month_end": pd.to_datetime(["2025-01-31"]),
            "panel_available_time": pd.to_datetime(["2025-01-31"]),
            "henry_hub_source_age_days": [0],
            "world_bank_urea_source_age_days": [0],
            "corn_source_age_days": [0],
        }
    )
    quarter = {feature: [1.0] for feature in config["quarterly_model_features"]}
    quarter.update(
        {
            "instrument": ["CF"],
            "period_end": pd.to_datetime(["2024-12-31"]),
            "panel_available_time": pd.to_datetime(["2025-02-20"]),
        }
    )
    tactical = pd.DataFrame(
        {
            "instrument": ["CF"],
            "trade_date": pd.to_datetime(["2025-01-31"]),
            "panel_available_time": pd.to_datetime(["2025-01-31"]),
        }
    )
    registry = yaml.safe_load(
        (PROJECT_ROOT / "configs/features/cf_feature_registry.yaml").read_text()
    )
    roles = yaml.safe_load((PROJECT_ROOT / "configs/quality/cf_data_roles.yaml").read_text())
    registry["features"][0]["source"] = "commodity.fertilizer_ams_3195"

    report = assess_curated_panels(
        pd.DataFrame(month), pd.DataFrame(quarter), tactical, config, registry, roles
    )

    assert report["status"] == "ERROR"
    assert any("non-core source" in message for message in report["errors"])
