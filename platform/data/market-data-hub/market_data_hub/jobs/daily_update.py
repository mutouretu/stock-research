"""Daily incremental update jobs."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from market_data_hub.markets.us.pipelines import download_instruments, download_prices


def run_us_daily_update(config_path: str | Path = "configs/us.yaml", lookback_days: int = 10) -> None:
    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=lookback_days)).isoformat()
    download_instruments.run(config_path)
    download_prices.run(config_path, start_date=start_date, end_date=end_date)
