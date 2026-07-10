from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from market_data_hub.exceptions import DataDownloadError
from market_data_hub.markets.cn.adapters.tushare import TushareCNAdapter
from market_data_hub.markets.cn.pipelines.download_prices import (
    CNPriceDownloadConfig,
    build_cn_daily_increment,
)
from market_data_hub.markets.cn.pipelines.merge_daily_increment import (
    merge_cn_daily_increment,
)


class FakeTushareClient:
    def __init__(self, *, failing_endpoints: set[str] | None = None) -> None:
        self.failing_endpoints = failing_endpoints or set()

    def _maybe_fail(self, endpoint: str) -> None:
        if endpoint in self.failing_endpoints:
            raise RuntimeError(f"{endpoint} failed")

    def trade_cal(self, **_kwargs: object) -> pd.DataFrame:
        return pd.DataFrame([{"cal_date": "20260708"}])

    def stock_basic(self, **_kwargs: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "symbol": "000001",
                    "name": "keep",
                    "area": "SZ",
                    "industry": "bank",
                    "market": "main",
                    "list_date": "20200101",
                },
                {
                    "ts_code": "000002.SZ",
                    "symbol": "000002",
                    "name": "new",
                    "area": "SZ",
                    "industry": "new",
                    "market": "main",
                    "list_date": "20260701",
                },
                {
                    "ts_code": "000003.SZ",
                    "symbol": "000003",
                    "name": "large",
                    "area": "SZ",
                    "industry": "large",
                    "market": "main",
                    "list_date": "20200101",
                },
                {
                    "ts_code": "000004.SZ",
                    "symbol": "000004",
                    "name": "st",
                    "area": "SZ",
                    "industry": "st",
                    "market": "main",
                    "list_date": "20200101",
                },
                {
                    "ts_code": "000005.SZ",
                    "symbol": "000005",
                    "name": "suspend",
                    "area": "SZ",
                    "industry": "suspend",
                    "market": "main",
                    "list_date": "20200101",
                },
                {
                    "ts_code": "430001.BJ",
                    "symbol": "430001",
                    "name": "bj",
                    "area": "BJ",
                    "industry": "bj",
                    "market": "bj",
                    "list_date": "20200101",
                },
            ]
        )

    def daily(self, **_kwargs: object) -> pd.DataFrame:
        self._maybe_fail("daily")
        return pd.DataFrame(
            [
                {
                    "ts_code": ts_code,
                    "trade_date": "20260708",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.8,
                    "close": 10.5,
                    "vol": 1000,
                    "amount": 10000,
                    "pct_chg": 2.0,
                }
                for ts_code in [
                    "000001.SZ",
                    "000002.SZ",
                    "000003.SZ",
                    "000004.SZ",
                    "000005.SZ",
                    "430001.BJ",
                ]
            ]
        )

    def daily_basic(self, **_kwargs: object) -> pd.DataFrame:
        self._maybe_fail("daily_basic")
        return pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "20260708", "total_mv": 300000},
                {"ts_code": "000002.SZ", "trade_date": "20260708", "total_mv": 300000},
                {"ts_code": "000003.SZ", "trade_date": "20260708", "total_mv": 6000000},
                {"ts_code": "000004.SZ", "trade_date": "20260708", "total_mv": 300000},
                {"ts_code": "000005.SZ", "trade_date": "20260708", "total_mv": 300000},
                {"ts_code": "430001.BJ", "trade_date": "20260708", "total_mv": 300000},
            ]
        )

    def cyq_perf(self, **_kwargs: object) -> pd.DataFrame:
        self._maybe_fail("cyq_perf")
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260708",
                    "cost_5pct": 8.0,
                    "winner_rate": 0.8,
                }
            ]
        )

    def stk_factor_pro(self, **_kwargs: object) -> pd.DataFrame:
        self._maybe_fail("stk_factor_pro")
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260708",
                    "ma_bfq_20": 10.1,
                    "ma_bfq_60": 9.9,
                    "ma_bfq_250": 8.8,
                }
            ]
        )

    def stock_st(self, **_kwargs: object) -> pd.DataFrame:
        self._maybe_fail("stock_st")
        return pd.DataFrame([{"ts_code": "000004.SZ"}])

    def suspend_d(self, **_kwargs: object) -> pd.DataFrame:
        self._maybe_fail("suspend_d")
        return pd.DataFrame([{"ts_code": "000005.SZ"}])


def _config(tmp_path: Path) -> CNPriceDownloadConfig:
    return CNPriceDownloadConfig(
        token="test",
        start_date="20260708",
        end_date="20260708",
        output_path=tmp_path / "daily_increment_20260708.parquet",
        failed_dates_path=tmp_path / "failed_trade_dates_20260708.json",
        sleep_seconds=0,
        retry_times=1,
        min_listing_days=60,
        min_total_mv=200000,
        max_total_mv=5000000,
    )


def test_cn_download_filters_universe_and_preserves_type_n_fields(tmp_path: Path) -> None:
    adapter = TushareCNAdapter(client=FakeTushareClient())

    result = build_cn_daily_increment(config=_config(tmp_path), adapter=adapter)

    assert result.failed_trade_dates == {}
    assert result.data["ts_code"].tolist() == ["000001.SZ"]
    row = result.data.iloc[0]
    assert row["cost_5pct"] == 8.0
    assert row["winner_rate"] == 0.8
    assert row["ma_bfq_20"] == 10.1


def test_cn_download_records_optional_endpoint_failure_but_keeps_rows(tmp_path: Path) -> None:
    adapter = TushareCNAdapter(client=FakeTushareClient(failing_endpoints={"cyq_perf"}))

    result = build_cn_daily_increment(config=_config(tmp_path), adapter=adapter)

    assert result.data["ts_code"].tolist() == ["000001.SZ"]
    assert result.failed_trade_dates == {"20260708": ("cyq_perf",)}


def test_cn_download_raises_when_mandatory_endpoint_returns_no_rows(tmp_path: Path) -> None:
    adapter = TushareCNAdapter(client=FakeTushareClient(failing_endpoints={"daily"}))

    with pytest.raises(DataDownloadError, match="No CN daily rows downloaded"):
        build_cn_daily_increment(config=_config(tmp_path), adapter=adapter)


def test_merge_cn_daily_increment_deduplicates_and_keeps_latest(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2026-07-07"),
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "vol": 1000,
            },
            {
                "trade_date": pd.Timestamp("2026-07-08"),
                "open": 10.5,
                "high": 11.0,
                "low": 10.0,
                "close": 10.8,
                "vol": 1000,
            },
        ]
    ).to_parquet(base_dir / "000001.SZ.parquet", index=False)

    increment_path = tmp_path / "increment.parquet"
    pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20260708",
                "open": 11.0,
                "high": 12.0,
                "low": 10.8,
                "close": 11.8,
                "vol": 2000,
                "amount": 20000,
            },
            {
                "ts_code": "000002.SZ",
                "trade_date": "20260708",
                "open": 20.0,
                "high": 21.0,
                "low": 19.5,
                "close": 20.5,
                "vol": 3000,
                "amount": 30000,
            },
        ]
    ).to_parquet(increment_path, index=False)

    output_dir = tmp_path / "output"
    summary = merge_cn_daily_increment(
        base_dir=base_dir,
        increment_path=increment_path,
        output_dir=output_dir,
    )

    assert summary.base_symbols == 1
    assert summary.increment_symbols == 2
    assert summary.output_symbols == 2
    merged = pd.read_parquet(output_dir / "000001.SZ.parquet")
    assert len(merged) == 2
    assert merged.iloc[-1]["close"] == 11.8
    assert (output_dir / "000002.SZ.parquet").exists()
