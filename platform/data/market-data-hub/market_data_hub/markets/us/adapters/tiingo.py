"""Tiingo US market adapter placeholder."""

from __future__ import annotations

import pandas as pd

from market_data_hub.markets.us.adapters.base import USMarketDataAdapter


class TiingoUSAdapter(USMarketDataAdapter):
    source = "tiingo"

    def get_instruments(self, symbols: list[str] | None = None) -> pd.DataFrame:
        raise NotImplementedError("Tiingo adapter is not implemented in phase one.")

    def get_daily_prices(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        raise NotImplementedError("Tiingo adapter is not implemented in phase one.")

    def get_corporate_actions(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError("Tiingo adapter is not implemented in phase one.")
