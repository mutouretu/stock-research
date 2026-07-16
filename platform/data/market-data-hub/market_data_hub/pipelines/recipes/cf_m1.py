"""Milestone 1 ingestion pipeline for CF cycle research."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd
import yaml

from market_data_hub.domains.agriculture.ers import download_crop_costs_returns
from market_data_hub.domains.agriculture.nass import download_planted_acres
from market_data_hub.domains.commodities.henry_hub import download_henry_hub
from market_data_hub.domains.commodities.world_bank import download_monthly_urea
from market_data_hub.domains.company_operations.cf import download_cf_product_operations
from market_data_hub.domains.fundamentals.sec_companyfacts import download_companyfacts
from market_data_hub.markets.us.adapters.yahoo_chart import YahooChartUSAdapter


@dataclass(frozen=True)
class DownloadResult:
    source: str
    output_path: Path
    rows: int
    first_observation: str | None
    last_observation: str | None

    def summary_text(self) -> str:
        return (
            f"{self.source}: rows={self.rows}, range={self.first_observation}.."
            f"{self.last_observation}, output={self.output_path}"
        )


def download_cf_m1_data(
    config_path: str | Path,
    *,
    sources: list[str] | None = None,
) -> list[DownloadResult]:
    config_path = Path(config_path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"CF M1 config must contain a YAML mapping: {config_path}")

    root = _find_workspace_root(config_path)
    configured = config.get("sources") or {}
    selected = sources or list(configured)
    unknown = sorted(set(selected) - set(configured))
    if unknown:
        raise ValueError(f"Unknown CF M1 sources: {unknown}")

    downloaders: dict[str, Callable[[dict], pd.DataFrame]] = {
        "cf_price": _download_cf_price,
        "henry_hub": _download_henry_hub,
        "world_bank_urea": _download_world_bank_urea,
        "sec_companyfacts": _download_sec_companyfacts,
        "cf_product_operations": _download_cf_product_operations,
        "crop_futures": _download_crop_futures,
        "ers_corn": _download_ers_corn,
        "ers_soybeans": _download_ers_soybeans,
        "nass_planted_acres": _download_nass_planted_acres,
    }
    results: list[DownloadResult] = []
    for source in selected:
        source_config = dict(configured[source])
        source_config["_workspace_root"] = str(root)
        if not source_config.get("enabled", True):
            continue
        if source not in downloaders:
            raise ValueError(f"No downloader implemented for configured source {source!r}")
        frame = downloaders[source](source_config)
        output_path = _resolve_output(root, source_config["output"])
        _write_parquet(frame, output_path)
        date_column = _date_column(frame)
        first, last = _date_range(frame, date_column)
        results.append(
            DownloadResult(
                source=source,
                output_path=output_path,
                rows=len(frame),
                first_observation=first,
                last_observation=last,
            )
        )
    return results


def _download_cf_price(config: dict) -> pd.DataFrame:
    symbol = str(config.get("symbol", "CF")).upper()
    frame = YahooChartUSAdapter().get_daily_prices(
        [symbol],
        str(config.get("start_date", "2013-01-01")),
        config.get("end_date"),
        "1d",
    )
    if frame.empty:
        raise ValueError("Yahoo Chart returned no CF price rows")
    frame = frame.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame.sort_values("trade_date").reset_index(drop=True)


def _download_henry_hub(config: dict) -> pd.DataFrame:
    return download_henry_hub(str(config["url"]))


def _download_world_bank_urea(config: dict) -> pd.DataFrame:
    return download_monthly_urea(str(config["url"]))


def _download_sec_companyfacts(config: dict) -> pd.DataFrame:
    environment_name = str(config.get("user_agent_env", "SEC_USER_AGENT"))
    user_agent = os.environ.get(environment_name)
    if not user_agent:
        raise ValueError(
            f"SEC requires a declared user agent; set {environment_name}="
            "'Your Name your.email@example.com'"
        )
    return download_companyfacts(
        str(config["url"]),
        ticker=str(config.get("ticker", "CF")),
        user_agent=user_agent,
    )


def _download_cf_product_operations(config: dict) -> pd.DataFrame:
    environment_name = str(config.get("user_agent_env", "SEC_USER_AGENT"))
    user_agent = os.environ.get(environment_name)
    if not user_agent:
        raise ValueError(f"SEC requires a declared user agent; set {environment_name}")
    return download_cf_product_operations(
        str(_resolve_output(Path(config["_workspace_root"]), config["raw_dir"])),
        user_agent=user_agent,
        start_year=int(config.get("start_year", 2013)),
    )


def _download_crop_futures(config: dict) -> pd.DataFrame:
    symbols = [str(value) for value in config.get("symbols", ["ZC=F", "ZS=F"])]
    frame = YahooChartUSAdapter().get_daily_prices(
        symbols,
        str(config.get("start_date", "2013-01-01")),
        config.get("end_date"),
        "1d",
    )
    if frame.empty:
        raise ValueError("Yahoo Chart returned no corn/soybean futures rows")
    frame = frame.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    names = {"ZC=F": "corn", "ZS=F": "soybeans"}
    frame["commodity"] = frame["symbol"].map(names).fillna(frame["symbol"])
    frame["unit"] = "US_cents_per_bushel"
    return frame.sort_values(["symbol", "trade_date"]).reset_index(drop=True)


def _download_ers_corn(config: dict) -> pd.DataFrame:
    return download_crop_costs_returns(str(config["url"]), crop="corn")


def _download_ers_soybeans(config: dict) -> pd.DataFrame:
    return download_crop_costs_returns(str(config["url"]), crop="soybeans")


def _download_nass_planted_acres(config: dict) -> pd.DataFrame:
    environment_name = str(config.get("api_key_env", "NASS_API_KEY"))
    api_key = os.environ.get(environment_name)
    if not api_key:
        raise ValueError(
            f"USDA NASS Quick Stats requires a free API key; set {environment_name} in .env"
        )
    return download_planted_acres(
        str(config["url"]),
        api_key=api_key,
        start_year=int(config.get("start_year", 2013)),
    )


def _find_workspace_root(start: Path) -> Path:
    for candidate in (start.parent, *start.parents):
        if (candidate / "README.md").is_file() and (candidate / "platform").is_dir() and (
            candidate / "research"
        ).is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate stock-research root from {start}")


def _resolve_output(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    if frame.empty:
        raise ValueError(f"Refusing to write empty dataset: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _date_column(frame: pd.DataFrame) -> str | None:
    for column in ("observation_date", "trade_date", "period_end", "filing_date"):
        if column in frame:
            return column
    return None


def _date_range(frame: pd.DataFrame, column: str | None) -> tuple[str | None, str | None]:
    if column is None or frame.empty:
        return None, None
    values = pd.to_datetime(frame[column], errors="coerce").dropna()
    if values.empty:
        return None, None
    return values.min().date().isoformat(), values.max().date().isoformat()
