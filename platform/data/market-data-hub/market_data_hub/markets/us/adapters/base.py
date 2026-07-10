"""US market data adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class USMarketDataAdapter(ABC):
    source: str

    @abstractmethod
    def get_instruments(self, symbols: list[str] | None = None) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_daily_prices(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_corporate_actions(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError
