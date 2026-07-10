"""US adapter factory."""

from __future__ import annotations

from market_data_hub.exceptions import UnsupportedDataSourceError
from market_data_hub.markets.us.adapters.base import USMarketDataAdapter
from market_data_hub.markets.us.adapters.polygon import PolygonUSAdapter
from market_data_hub.markets.us.adapters.tiingo import TiingoUSAdapter
from market_data_hub.markets.us.adapters.yahoo_chart import YahooChartUSAdapter
from market_data_hub.markets.us.adapters.yfinance import YFinanceUSAdapter


def create_us_adapter(source: str) -> USMarketDataAdapter:
    source_key = source.lower()
    if source_key == "yahoo_chart":
        return YahooChartUSAdapter()
    if source_key == "yfinance":
        return YFinanceUSAdapter()
    if source_key == "polygon":
        return PolygonUSAdapter()
    if source_key == "tiingo":
        return TiingoUSAdapter()
    raise UnsupportedDataSourceError(f"Unsupported US data source: {source}")
