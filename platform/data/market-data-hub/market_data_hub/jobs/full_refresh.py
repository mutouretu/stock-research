"""Full refresh jobs."""

from __future__ import annotations

from pathlib import Path

from market_data_hub.markets.us.pipelines import download_instruments, download_prices


def run_us_full_refresh(config_path: str | Path = "configs/us.yaml") -> None:
    download_instruments.run(config_path)
    download_prices.run(config_path)
