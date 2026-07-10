from pathlib import Path

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
        "commodity.henry_hub",
        "commodity.urea",
        "crop.corn",
        "cycle.cf.financials",
        "cycle.cf.price",
    ]
