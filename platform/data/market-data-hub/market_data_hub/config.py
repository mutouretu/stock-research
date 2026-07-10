"""Configuration loading for market-data-hub."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class StorageConfig:
    backend: str = "parquet"
    root_dir: str = "data"


@dataclass(frozen=True)
class UniverseConfig:
    symbols: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DownloadConfig:
    start_date: str
    end_date: str | None = None
    interval: str = "1d"


@dataclass(frozen=True)
class DownstreamRequirementsConfig:
    consumers: list[str] = field(default_factory=list)
    preferred_start_date: str | None = None
    min_history_days: int | None = None
    use_cases: list[str] = field(default_factory=list)
    w_bottom_windows: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketConfig:
    market: str
    default_source: str
    download: DownloadConfig
    storage: StorageConfig = field(default_factory=StorageConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    downstream_requirements: DownstreamRequirementsConfig = field(
        default_factory=DownstreamRequirementsConfig
    )


def load_config(config_path: str | Path) -> MarketConfig:
    """Load and validate a YAML market configuration file."""

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        raw: dict[str, Any] = yaml.safe_load(file) or {}

    try:
        market = str(raw["market"]).upper()
        default_source = str(raw["default_source"]).lower()
    except KeyError as exc:
        raise ValueError(f"Missing required config field: {exc.args[0]}") from exc

    storage_raw = raw.get("storage") or {}
    universe_raw = raw.get("universe") or {}
    download_raw = raw.get("download") or {}
    downstream_raw = raw.get("downstream_requirements") or {}
    if not download_raw.get("start_date"):
        raise ValueError("Missing required config field: download.start_date")

    symbols = [str(symbol).upper() for symbol in universe_raw.get("symbols", []) if symbol]
    w_bottom_windows = {
        str(name): int(days)
        for name, days in (downstream_raw.get("w_bottom_windows") or {}).items()
    }

    return MarketConfig(
        market=market,
        default_source=default_source,
        download=DownloadConfig(
            start_date=str(download_raw["start_date"]),
            end_date=download_raw.get("end_date"),
            interval=str(download_raw.get("interval", "1d")),
        ),
        storage=StorageConfig(
            backend=str(storage_raw.get("backend", "parquet")).lower(),
            root_dir=str(storage_raw.get("root_dir", "data")),
        ),
        universe=UniverseConfig(symbols=symbols),
        downstream_requirements=DownstreamRequirementsConfig(
            consumers=[
                str(consumer) for consumer in downstream_raw.get("consumers", []) if consumer
            ],
            preferred_start_date=downstream_raw.get("preferred_start_date"),
            min_history_days=(
                int(downstream_raw["min_history_days"])
                if downstream_raw.get("min_history_days") is not None
                else None
            ),
            use_cases=[str(use_case) for use_case in downstream_raw.get("use_cases", [])],
            w_bottom_windows=w_bottom_windows,
        ),
    )
