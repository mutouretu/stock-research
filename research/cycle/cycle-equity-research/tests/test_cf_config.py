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
        "cycle.cf.financials",
        "cycle.cf.price",
        "cycle.cf.product_operations",
    ]


def test_cf_panel_configs_declare_reusable_dataset_inputs() -> None:
    panel_dir = PROJECT_ROOT / "configs/panels"
    configs = [yaml.safe_load(path.read_text()) for path in sorted(panel_dir.glob("cf_*.yaml"))]
    assert {config["panel_id"] for config in configs} == {
        "cycle.cf.daily",
        "cycle.cf.quarterly",
    }
    assert all(config.get("output") for config in configs)
