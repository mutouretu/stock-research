"""Local Parquet storage backend."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from market_data_hub.core.storage import MarketDataStorage


class ParquetExporter(MarketDataStorage):
    """Persist normalized data to local Parquet files."""

    def save_instruments(self, instruments: pd.DataFrame, market: str) -> Path:
        path = self.root_dir / "processed" / market.lower() / "instruments" / "instruments.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        instruments.to_parquet(path, index=False)
        return path

    def save_daily_prices(self, prices: pd.DataFrame, market: str) -> Path:
        path = self.root_dir / "processed" / market.lower() / "prices_daily" / "prices.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        prices.to_parquet(path, index=False)
        return path

    def save_corporate_actions(self, actions: pd.DataFrame, market: str) -> Path:
        path = (
            self.root_dir
            / "processed"
            / market.lower()
            / "corporate_actions"
            / "corporate_actions.parquet"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        actions.to_parquet(path, index=False)
        return path

    def load_daily_prices(self, market: str) -> pd.DataFrame:
        path = self.root_dir / "processed" / market.lower() / "prices_daily" / "prices.parquet"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)
