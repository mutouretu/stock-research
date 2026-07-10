"""Storage abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


class MarketDataStorage(ABC):
    """Interface for normalized market data storage backends."""

    def __init__(self, root_dir: str | Path = "data") -> None:
        self.root_dir = Path(root_dir)

    @abstractmethod
    def save_instruments(self, instruments: pd.DataFrame, market: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    def save_daily_prices(self, prices: pd.DataFrame, market: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    def load_daily_prices(self, market: str) -> pd.DataFrame:
        raise NotImplementedError
