from pathlib import Path

import yaml

from cycle_equity_research.data import load_dataset_catalog, load_instrument_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cf_config_declares_research_contract() -> None:
    config = load_instrument_config(PROJECT_ROOT / "configs/instruments/CF.yaml")
    assert config.instrument == "CF"
    assert config.drivers
    assert config.features
    assert config.targets


def test_dataset_contracts_parse_with_research_data_core() -> None:
    catalog = load_dataset_catalog(PROJECT_ROOT / "configs/datasets")
    assert catalog.list_dataset_ids() == [
        "commodity.fertilizer_ams_3195",
        "commodity.henry_hub",
        "commodity.urea",
        "crop.corn",
        "crop.planted_acres",
        "cycle.cf.core_monthly",
        "cycle.cf.core_quarterly",
        "cycle.cf.daily_nitrogen_economics",
        "cycle.cf.financials",
        "cycle.cf.operating_bridge_predictions",
        "cycle.cf.price",
        "cycle.cf.product_operations",
        "cycle.cf.quarterly_nitrogen_economics",
        "cycle.cf.tactical_context",
    ]


def test_cf_panel_configs_declare_reusable_dataset_inputs() -> None:
    panel_dir = PROJECT_ROOT / "configs/panels"
    configs = [
        config
        for path in sorted(panel_dir.glob("cf_*.yaml"))
        if (config := yaml.safe_load(path.read_text())).get("panel_id")
    ]
    assert {config["panel_id"] for config in configs} == {
        "cycle.cf.daily",
        "cycle.cf.quarterly",
    }
    assert all(config.get("output") for config in configs)


def test_curated_panel_config_separates_core_and_tactical_outputs() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "configs/panels/cf_curated.yaml").read_text())
    assert config["panel_group_id"] == "cycle.cf.curated"
    assert set(config["outputs"]) == {
        "core_monthly",
        "core_quarterly",
        "tactical_context",
        "lineage",
    }
    assert len(config["monthly_model_features"]) <= 7
    assert len(config["quarterly_model_features"]) <= 5


def test_operating_bridge_experiment_locks_prediction_timing_and_comparator() -> None:
    config = yaml.safe_load(
        (PROJECT_ROOT / "configs/experiments/cf_operating_bridge_v1.yaml").read_text()
    )
    assert config["experiment_id"] == "cf_operating_bridge_v1"
    assert config["evaluation"] == {
        "prediction_lag_days_after_period_end": 15,
        "minimum_training_quarters": 12,
        "window": "expanding",
        "naive_comparator": "last_disclosed_value",
        "metrics": [
            "mae",
            "rmse",
            "bias",
            "wape",
            "direction_accuracy",
            "improvement_vs_naive",
        ],
    }
    assert set(config["products"]) == {
        "ammonia",
        "granular_urea",
        "uan",
        "ammonium_nitrate",
    }


def test_valuation_config_matches_consolidated_ebitda_scope() -> None:
    valuation = yaml.safe_load(
        (PROJECT_ROOT / "configs/valuation/cf_valuation_data_v1.yaml").read_text()
    )
    assert valuation["enterprise_value"]["primary_definition"] == "consolidated_standard"
    assert valuation["enterprise_value"]["noncontrolling_interest_column"] == (
        "cf_noncontrolling_interest"
    )
    assert valuation["market_value"]["price_contract"].startswith("unadjusted_close")

    quarterly = yaml.safe_load(
        (PROJECT_ROOT / "configs/panels/cf_quarterly.yaml").read_text()
    )
    outputs = {metric["output_col"] for metric in quarterly["financials"]["metrics"]}
    assert {
        "cf_total_debt",
        "cf_noncontrolling_interest",
        "cf_preferred_equity",
        "cf_operating_lease_liability_current",
        "cf_operating_lease_liability_noncurrent",
    } <= outputs


def test_midcycle_scenarios_are_operating_assumptions_not_price_targets() -> None:
    config = yaml.safe_load(
        (PROJECT_ROOT / "configs/valuation/cf_midcycle_ebitda_v1.yaml").read_text()
    )
    assert list(config["scenarios"]) == ["downside", "base", "upside"]
    serialized = str(config).lower()
    assert "stock_price" not in serialized
    assert "target_price" not in serialized
    assert config["quality"]["minimum_annual_windows"] >= 24


def test_valuation_range_preserves_full_scenario_multiple_matrix() -> None:
    config = yaml.safe_load(
        (PROJECT_ROOT / "configs/valuation/cf_valuation_range_v1.yaml").read_text()
    )
    assert config["multiple_cases"] == {"low": 0.25, "median": 0.5, "high": 0.75}
    assert config["quality"]["required_scenarios"] == ["downside", "base", "upside"]
    assert "noncontrolling_interest" in config["equity_bridge"]["subtract"]
