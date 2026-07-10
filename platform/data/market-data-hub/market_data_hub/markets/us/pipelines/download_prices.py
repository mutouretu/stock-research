"""Download US daily OHLCV data and save normalized Parquet output."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from market_data_hub.config import load_config
from market_data_hub.exceptions import DataDownloadError
from market_data_hub.exports.parquet import ParquetExporter
from market_data_hub.markets.us.adapters.factory import create_us_adapter

logger = logging.getLogger(__name__)

DAILY_PRICE_COLUMNS = [
    "instrument_id",
    "symbol",
    "market",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adj_close",
    "dividends",
    "stock_splits",
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
    if config.storage.backend != "parquet":
        raise ValueError(f"Unsupported storage backend for phase one: {config.storage.backend}")

    symbols = config.universe.symbols
    if not symbols:
        logger.warning("No symbols configured in %s", config_path)
        prices = pd.DataFrame(columns=DAILY_PRICE_COLUMNS)
        ParquetExporter(config.storage.root_dir).save_daily_prices(prices, config.market)
        return prices

    adapter = create_us_adapter(config.default_source)
    exporter = ParquetExporter(config.storage.root_dir)
    effective_start = start_date or config.download.start_date
    effective_end = end_date if end_date is not None else config.download.end_date
    if effective_end is None:
        effective_end = date.today().isoformat()
    effective_interval = config.download.interval

    prices = adapter.get_daily_prices(
        symbols=symbols,
        start_date=effective_start,
        end_date=effective_end,
        interval=effective_interval,
    )
    if prices.empty:
        raise DataDownloadError(
            "No US daily prices downloaded. "
            f"source={config.default_source}, symbols={len(symbols)}, "
            f"start_date={effective_start}, end_date={effective_end}, interval={effective_interval}. "
            "The existing parquet was not overwritten."
        )
    else:
        prices = _normalize_prices_frame(prices)

    path = exporter.save_daily_prices(prices, config.market)
    logger.info(
        "Saved %s US daily price rows for %s symbols to %s",
        len(prices),
        prices["symbol"].nunique() if "symbol" in prices.columns and not prices.empty else 0,
        path,
    )
    return prices


def _normalize_prices_frame(prices: pd.DataFrame) -> pd.DataFrame:
    prices = prices.copy()
    prices["trade_date"] = pd.to_datetime(prices["trade_date"]).dt.date
    prices = prices.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    return prices.reindex(columns=DAILY_PRICE_COLUMNS)
