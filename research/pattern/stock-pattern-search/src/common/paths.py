"""Workspace-aware paths for the migrated stock-pattern-search application."""

from pathlib import Path

from research_data_core.paths import get_shared_data_dir


def get_shared_daily_dir(name: str = "parquet_daily_cache") -> Path:
    """Return a named daily cache below the canonical shared-data root."""
    return get_shared_data_dir() / "raw" / "daily" / name


def get_shared_us_daily_dir() -> Path:
    """Return the canonical per-symbol US daily directory."""
    return get_shared_data_dir() / "us" / "raw" / "daily" / "parquet_by_symbol"
