"""Download US corporate actions."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from market_data_hub.config import load_config
from market_data_hub.exports.parquet import ParquetExporter
from market_data_hub.markets.us.adapters.factory import create_us_adapter

logger = logging.getLogger(__name__)

CORPORATE_ACTION_COLUMNS = [
    "instrument_id",
    "symbol",
    "market",
    "action_date",
    "action_type",
    "value",
    "source",
    "created_at",
]


def run(
    config_path: str | Path = "configs/us.yaml",
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    config = load_config(config_path)
    if config.market != "US":
        raise ValueError(f"Expected US config, got market={config.market}")

    adapter = create_us_adapter(config.default_source)
    exporter = ParquetExporter(config.storage.root_dir)
    effective_start = start_date or config.download.start_date
    effective_end = end_date if end_date is not None else config.download.end_date

    actions = adapter.get_corporate_actions(config.universe.symbols, effective_start, effective_end)
    if actions.empty:
        logger.info("No US corporate actions downloaded.")
        actions = pd.DataFrame(columns=CORPORATE_ACTION_COLUMNS)
    else:
        actions = actions.sort_values(["symbol", "action_date", "action_type"]).reset_index(drop=True)
        actions = actions.reindex(columns=CORPORATE_ACTION_COLUMNS)

    path = exporter.save_corporate_actions(actions, config.market)
    logger.info("Saved %s US corporate action rows to %s", len(actions), path)
    return actions
