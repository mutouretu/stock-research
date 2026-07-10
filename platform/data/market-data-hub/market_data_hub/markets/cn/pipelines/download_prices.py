"""Download CN A-share daily data from Tushare into flat increment parquet files."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yaml

from market_data_hub.config import load_config
from market_data_hub.exceptions import DataDownloadError
from market_data_hub.markets.cn.adapters.tushare import TushareCNAdapter

DEFAULT_INCREMENT_DIR = Path("data/processed/cn/increments")
DEFAULT_FAILED_DATES_DIR = Path("data/processed/cn/failed_dates")


@dataclass(slots=True)
class CNPriceDownloadConfig:
    token: str
    start_date: str
    end_date: str
    output_path: Path
    failed_dates_path: Path
    min_listing_days: int = 60
    min_total_mv: float = 200_000
    max_total_mv: float = 5_000_000
    sleep_seconds: float = 0.15
    retry_times: int = 3
    retry_backoff_seconds: float = 1.5


@dataclass(slots=True)
class FetchResult:
    data: pd.DataFrame
    failed: bool = False


@dataclass(slots=True)
class TradeDateResult:
    data: pd.DataFrame
    failed_endpoints: tuple[str, ...] = ()


@dataclass(slots=True)
class CNPriceDownloadResult:
    data: pd.DataFrame
    output_path: Path
    failed_dates_path: Path
    failed_trade_dates: dict[str, tuple[str, ...]] = field(default_factory=dict)
    total_trade_dates: int = 0
    initial_failed_trade_dates: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def summary_text(self) -> str:
        initial_failed_count = len(self.initial_failed_trade_dates)
        final_failed_count = len(self.failed_trade_dates)
        recovered_count = initial_failed_count - final_failed_count
        symbols = int(self.data["ts_code"].nunique()) if "ts_code" in self.data.columns else 0
        return "\n".join(
            [
                "CN Tushare daily download summary",
                f"total_trade_dates: {self.total_trade_dates}",
                f"rows: {len(self.data)}",
                f"symbols: {symbols}",
                f"initial_failed_dates: {initial_failed_count}",
                f"recovered_after_retry: {recovered_count}",
                f"final_failed_dates: {final_failed_count}",
                f"output: {self.output_path}",
                f"failed_dates: {self.failed_dates_path}",
            ]
        )


def run(
    config_path: str | Path = "configs/cn.yaml",
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    output_path: str | Path | None = None,
    failed_dates_output: str | Path | None = None,
    retry_from_failed_dates: str | Path | None = None,
    adapter: TushareCNAdapter | None = None,
) -> CNPriceDownloadResult:
    config = build_download_config(
        config_path,
        start_date=start_date,
        end_date=end_date,
        output_path=output_path,
        failed_dates_output=failed_dates_output,
    )
    trade_dates_override = None
    if retry_from_failed_dates:
        trade_dates_override = sorted(load_failed_trade_dates(retry_from_failed_dates))

    active_adapter = adapter or TushareCNAdapter(token=config.token)
    result = build_cn_daily_increment(
        config=config,
        adapter=active_adapter,
        trade_dates_override=trade_dates_override,
    )

    final_data = result.data
    if retry_from_failed_dates and config.output_path.exists():
        existing = pd.read_parquet(config.output_path)
        final_data = merge_flat_daily_frames(existing, result.data)
        result.data = final_data

    save_increment(final_data, config.output_path)
    save_failed_trade_dates(result.failed_trade_dates, config.failed_dates_path)
    result.output_path = config.output_path
    result.failed_dates_path = config.failed_dates_path
    return result


def build_download_config(
    config_path: str | Path,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    output_path: str | Path | None = None,
    failed_dates_output: str | Path | None = None,
) -> CNPriceDownloadConfig:
    market_config = load_config(config_path)
    if market_config.market != "CN":
        raise ValueError(f"Expected CN config, got market={market_config.market}")
    if market_config.default_source != "tushare":
        raise ValueError(f"Expected Tushare source, got {market_config.default_source}")

    raw = _load_raw_yaml(config_path)
    cn_daily = raw.get("cn_daily") or {}
    filters = cn_daily.get("filters") or {}
    retry = cn_daily.get("retry") or {}
    outputs = cn_daily.get("outputs") or {}
    token_env = str(cn_daily.get("token_env", "TUSHARE_TOKEN"))
    token = os.getenv(token_env, "")
    if not token:
        token = str(cn_daily.get("token", "") or "")
    if not token:
        raise ValueError(f"Missing Tushare token. Set {token_env} or cn_daily.token.")

    effective_start = _compact_date(start_date or market_config.download.start_date)
    effective_end = _compact_date(end_date or market_config.download.end_date or effective_start)
    output = Path(
        output_path
        or outputs.get("increment_path")
        or DEFAULT_INCREMENT_DIR / f"daily_increment_{effective_start}_{effective_end}.parquet"
    )
    failed = Path(
        failed_dates_output
        or outputs.get("failed_dates_path")
        or DEFAULT_FAILED_DATES_DIR / f"failed_trade_dates_{effective_start}_{effective_end}.json"
    )

    return CNPriceDownloadConfig(
        token=token,
        start_date=effective_start,
        end_date=effective_end,
        output_path=output,
        failed_dates_path=failed,
        min_listing_days=int(filters.get("min_listing_days", 60)),
        min_total_mv=float(filters.get("min_total_mv", 200_000)),
        max_total_mv=float(filters.get("max_total_mv", 5_000_000)),
        sleep_seconds=float(cn_daily.get("sleep_seconds", 0.15)),
        retry_times=int(retry.get("times", 3)),
        retry_backoff_seconds=float(retry.get("backoff_seconds", 1.5)),
    )


def build_cn_daily_increment(
    *,
    config: CNPriceDownloadConfig,
    adapter: TushareCNAdapter,
    trade_dates_override: list[str] | None = None,
) -> CNPriceDownloadResult:
    trade_dates = trade_dates_override or get_trade_dates(
        adapter,
        config.start_date,
        config.end_date,
    )
    stock_basic = get_stock_basic(adapter)

    daily_results: dict[str, pd.DataFrame] = {}
    failed_trade_dates: dict[str, tuple[str, ...]] = {}
    for index, trade_date in enumerate(trade_dates, start=1):
        print(f"[{index}/{len(trade_dates)}] processing CN trade date {trade_date}")
        trade_result = fetch_one_trade_date(
            adapter=adapter,
            stock_basic=stock_basic,
            trade_date=trade_date,
            config=config,
        )
        daily_results[trade_date] = trade_result.data
        if trade_result.failed_endpoints:
            failed_trade_dates[trade_date] = trade_result.failed_endpoints
        time.sleep(config.sleep_seconds)

    initial_failed_trade_dates = dict(failed_trade_dates)
    if failed_trade_dates:
        retry_results = retry_failed_trade_dates(
            adapter=adapter,
            stock_basic=stock_basic,
            failed_trade_dates=failed_trade_dates,
            config=config,
        )
        daily_results.update(retry_results["daily_results"])
        failed_trade_dates = retry_results["failed_trade_dates"]

    frames = [frame for frame in daily_results.values() if not frame.empty]
    data = merge_flat_daily_frames(*frames)
    if data.empty:
        raise DataDownloadError(
            "No CN daily rows downloaded. "
            f"start_date={config.start_date}, end_date={config.end_date}"
        )

    return CNPriceDownloadResult(
        data=data,
        output_path=config.output_path,
        failed_dates_path=config.failed_dates_path,
        failed_trade_dates=failed_trade_dates,
        total_trade_dates=len(trade_dates),
        initial_failed_trade_dates=initial_failed_trade_dates,
    )


def get_trade_dates(adapter: TushareCNAdapter, start_date: str, end_date: str) -> list[str]:
    trade_cal = adapter.trade_calendar(start_date=start_date, end_date=end_date)
    if trade_cal.empty:
        raise DataDownloadError(
            f"Tushare trade_cal returned no open dates between {start_date} and {end_date}"
        )
    return sorted(trade_cal["cal_date"].astype(str).tolist())


def get_stock_basic(adapter: TushareCNAdapter) -> pd.DataFrame:
    stock_basic = adapter.stock_basic()
    if stock_basic.empty:
        raise DataDownloadError("Tushare stock_basic returned no active stocks")

    stock_basic = stock_basic.copy()
    stock_basic["ts_code"] = stock_basic["ts_code"].astype(str)
    stock_basic["list_date"] = pd.to_datetime(stock_basic["list_date"], format="%Y%m%d")
    stock_basic = stock_basic[~stock_basic["ts_code"].str.endswith(".BJ")].copy()
    return stock_basic.sort_values("ts_code").reset_index(drop=True)


def fetch_one_trade_date(
    *,
    adapter: TushareCNAdapter,
    stock_basic: pd.DataFrame,
    trade_date: str,
    config: CNPriceDownloadConfig,
) -> TradeDateResult:
    failed_endpoints: list[str] = []

    daily_result = safe_fetch(
        "daily",
        adapter.daily,
        config=config,
        trade_date=trade_date,
    )
    if daily_result.failed or daily_result.data.empty:
        failed_endpoints.append("daily")
        return TradeDateResult(pd.DataFrame(), tuple(failed_endpoints))

    daily_basic_result = safe_fetch(
        "daily_basic",
        adapter.daily_basic,
        config=config,
        trade_date=trade_date,
    )
    if daily_basic_result.failed or daily_basic_result.data.empty:
        failed_endpoints.append("daily_basic")
        return TradeDateResult(pd.DataFrame(), tuple(failed_endpoints))

    cyq_perf_result = safe_fetch("cyq_perf", adapter.cyq_perf, config=config, trade_date=trade_date)
    if cyq_perf_result.failed:
        failed_endpoints.append("cyq_perf")

    stk_factor_result = safe_fetch(
        "stk_factor_pro",
        adapter.stk_factor,
        config=config,
        trade_date=trade_date,
    )
    if stk_factor_result.failed:
        failed_endpoints.append("stk_factor_pro")

    stock_st_result = safe_fetch("stock_st", adapter.stock_st, config=config, trade_date=trade_date)
    if stock_st_result.failed:
        failed_endpoints.append("stock_st")

    suspend_result = safe_fetch("suspend_d", adapter.suspend, config=config, trade_date=trade_date)
    if suspend_result.failed:
        failed_endpoints.append("suspend_d")

    merged = stock_basic.merge(daily_result.data, on="ts_code", how="inner")
    if merged.empty:
        return TradeDateResult(pd.DataFrame(), tuple(failed_endpoints))

    merged["trade_date"] = merged["trade_date"].astype(str)
    merged["trade_date_dt"] = pd.to_datetime(merged["trade_date"], format="%Y%m%d")
    merged["listing_days"] = (merged["trade_date_dt"] - merged["list_date"]).dt.days

    st_codes = to_code_set(stock_st_result.data)
    suspended_codes = to_code_set(suspend_result.data)
    merged = merged[~merged["ts_code"].isin(st_codes)]
    merged = merged[~merged["ts_code"].isin(suspended_codes)]
    merged = merged[merged["listing_days"] >= config.min_listing_days]

    merged = merged.merge(
        daily_basic_result.data,
        on=["ts_code", "trade_date"],
        how="inner",
        suffixes=("", "_daily_basic"),
    )
    merged = merged[
        merged["total_mv"].between(config.min_total_mv, config.max_total_mv, inclusive="both")
    ]
    merged = merge_optional_frame(merged, cyq_perf_result.data, suffix="_cyq")
    merged = merge_optional_frame(merged, stk_factor_result.data, suffix="_factor")
    merged = merged.drop(columns=["trade_date_dt"])
    merged = merged.drop_duplicates(subset=["ts_code", "trade_date"]).reset_index(drop=True)
    return TradeDateResult(merged, tuple(failed_endpoints))


def safe_fetch(
    endpoint_name: str,
    fetcher: Callable[[str], pd.DataFrame],
    *,
    config: CNPriceDownloadConfig,
    trade_date: str,
) -> FetchResult:
    for attempt in range(1, config.retry_times + 1):
        try:
            df = fetcher(trade_date)
            if df is None or df.empty:
                return FetchResult(pd.DataFrame(), failed=False)
            data = df.copy()
            if "trade_date" in data.columns:
                data["trade_date"] = data["trade_date"].astype(str)
            if "ts_code" in data.columns:
                data["ts_code"] = data["ts_code"].astype(str)
            return FetchResult(data, failed=False)
        except Exception as exc:
            if attempt == config.retry_times:
                print(f"warning: {endpoint_name} failed for {trade_date}: {exc}")
                return FetchResult(pd.DataFrame(), failed=True)
            wait_seconds = config.retry_backoff_seconds * attempt
            print(
                f"warning: {endpoint_name} attempt {attempt}/{config.retry_times} "
                f"failed for {trade_date}: {exc}; retrying in {wait_seconds:.1f}s"
            )
            time.sleep(wait_seconds)
    return FetchResult(pd.DataFrame(), failed=True)


def retry_failed_trade_dates(
    *,
    adapter: TushareCNAdapter,
    stock_basic: pd.DataFrame,
    failed_trade_dates: dict[str, tuple[str, ...]],
    config: CNPriceDownloadConfig,
) -> dict[str, Any]:
    retried_daily_results: dict[str, pd.DataFrame] = {}
    unresolved_trade_dates: dict[str, tuple[str, ...]] = {}

    for index, (trade_date, endpoints) in enumerate(sorted(failed_trade_dates.items()), start=1):
        print(
            f"[retry {index}/{len(failed_trade_dates)}] processing CN trade date "
            f"{trade_date} for endpoints {','.join(endpoints)}"
        )
        trade_result = fetch_one_trade_date(
            adapter=adapter,
            stock_basic=stock_basic,
            trade_date=trade_date,
            config=config,
        )
        retried_daily_results[trade_date] = trade_result.data
        if trade_result.failed_endpoints:
            unresolved_trade_dates[trade_date] = trade_result.failed_endpoints
        time.sleep(config.sleep_seconds)

    return {
        "daily_results": retried_daily_results,
        "failed_trade_dates": unresolved_trade_dates,
    }


def merge_optional_frame(base: pd.DataFrame, other: pd.DataFrame, suffix: str) -> pd.DataFrame:
    if other.empty:
        return base
    return base.merge(
        other,
        on=["ts_code", "trade_date"],
        how="left",
        suffixes=("", suffix),
    )


def merge_flat_daily_frames(*frames: pd.DataFrame) -> pd.DataFrame:
    non_empty = [frame.copy() for frame in frames if frame is not None and not frame.empty]
    if not non_empty:
        return pd.DataFrame()
    data = pd.concat(non_empty, ignore_index=True)
    data["ts_code"] = data["ts_code"].astype(str)
    data["trade_date"] = data["trade_date"].astype(str).str.replace("-", "", regex=False)
    data = data.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    return data.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)


def to_code_set(df: pd.DataFrame) -> set[str]:
    if df.empty or "ts_code" not in df.columns:
        return set()
    return set(df["ts_code"].dropna().astype(str).tolist())


def save_increment(data: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(output_path, index=False)


def save_failed_trade_dates(
    failed_trade_dates: dict[str, tuple[str, ...]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        trade_date: list(endpoints)
        for trade_date, endpoints in sorted(failed_trade_dates.items())
    }
    output_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def load_failed_trade_dates(input_path: str | Path) -> dict[str, tuple[str, ...]]:
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid failed dates file: {input_path}")
    return {
        str(trade_date): tuple(str(endpoint) for endpoint in endpoints)
        if isinstance(endpoints, list)
        else ()
        for trade_date, endpoints in data.items()
    }


def _load_raw_yaml(config_path: str | Path) -> dict[str, Any]:
    with Path(config_path).open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _compact_date(value: str) -> str:
    return str(value).replace("-", "")
