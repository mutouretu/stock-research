"""Download or build US instrument master data."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from market_data_hub.config import load_config
from market_data_hub.exports.parquet import ParquetExporter
from market_data_hub.markets.us.adapters.factory import create_us_adapter

logger = logging.getLogger(__name__)

INSTRUMENT_COLUMNS = [
    "instrument_id",
    "symbol",
    "market",
    "exchange",
    "name",
    "asset_type",
    "sector",
    "industry",
    "currency",
    "is_active",
    "list_date",
    "delist_date",
    "source",
    "updated_at",
]


def run(config_path: str | Path = "configs/us.yaml") -> pd.DataFrame:
    config = load_config(config_path)
    if config.market != "US":
        raise ValueError(f"Expected US config, got market={config.market}")
    if config.storage.backend != "parquet":
        raise ValueError(f"Unsupported storage backend for phase one: {config.storage.backend}")

    adapter = create_us_adapter(config.default_source)
    exporter = ParquetExporter(config.storage.root_dir)

    instruments = adapter.get_instruments(config.universe.symbols)
    if instruments.empty:
        logger.warning("No US instruments generated. Check universe.symbols in %s", config_path)
        instruments = pd.DataFrame(columns=INSTRUMENT_COLUMNS)
    else:
        instruments = _sort_columns(instruments)

    path = exporter.save_instruments(instruments, config.market)
    logger.info("Saved %s US instruments to %s", len(instruments), path)
    return instruments


def _sort_columns(data: pd.DataFrame) -> pd.DataFrame:
    return data.reindex(columns=INSTRUMENT_COLUMNS)
