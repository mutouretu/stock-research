from pathlib import Path

import pandas as pd

from market_data_hub.markets.us.pipelines.export_daily_by_symbol import (
    export_us_daily_by_symbol,
)
from market_data_hub.markets.us.pipelines.validate_prices import validate_us_prices


def test_validate_us_prices_reports_duplicates_anomalies_and_markdown(tmp_path: Path) -> None:
    input_path = tmp_path / "prices.parquet"
    report_path = tmp_path / "report.md"
    prices = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "trade_date": "2015-01-02",
                "open": 10.0,
                "high": 9.0,
                "low": 11.0,
                "close": 10.0,
                "volume": 1000,
                "adj_close": 10.0,
                "market": "US",
            },
            {
                "symbol": "AAPL",
                "trade_date": "2015-01-02",
                "open": 10.0,
                "high": 12.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1100,
                "adj_close": 10.5,
                "market": "US",
            },
            {
                "symbol": "MSFT",
                "trade_date": "2016-03-01",
                "open": 20.0,
                "high": 21.0,
                "low": 19.5,
                "close": 20.5,
                "volume": 2000,
                "adj_close": 20.5,
                "market": "US",
            },
        ]
    )
    prices.to_parquet(input_path, index=False)

    report = validate_us_prices(input_path, report_path)

    assert report.rows == 3
    assert report.symbol_count == 2
    assert report.missing_required_columns == []
    assert report.duplicate_count == 2
    assert report.anomaly_counts["high_less_than_low"] == 1
    assert report_path.exists()
    assert "US Prices Validation Report" in report_path.read_text(encoding="utf-8")


def test_export_us_daily_by_symbol_writes_compatible_sorted_files(tmp_path: Path) -> None:
    input_path = tmp_path / "prices.parquet"
    output_dir = tmp_path / "by_symbol"
    prices = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "trade_date": "2020-01-03",
                "open": 11.0,
                "high": 12.0,
                "low": 10.0,
                "close": 11.5,
                "volume": 1100,
                "adj_close": 11.5,
                "market": "US",
            },
            {
                "symbol": "AAPL",
                "trade_date": "2020-01-02",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1000,
                "adj_close": 10.5,
                "market": "US",
            },
            {
                "symbol": "MSFT",
                "trade_date": "2020-01-02",
                "open": 20.0,
                "high": 21.0,
                "low": 19.5,
                "close": 20.5,
                "volume": 2000,
                "adj_close": 20.5,
                "market": "US",
            },
            {
                "symbol": "MSFT",
                "trade_date": "2020-01-03",
                "open": 21.0,
                "high": 22.0,
                "low": 20.5,
                "close": 21.5,
                "volume": 2100,
                "adj_close": 21.5,
                "market": "US",
            },
        ]
    )
    prices.to_parquet(input_path, index=False)

    summary = export_us_daily_by_symbol(input_path, output_dir, min_rows=2)

    assert summary.exported_symbols == 2
    assert (output_dir / "AAPL.parquet").exists()
    assert (output_dir / "MSFT.parquet").exists()

    aapl = pd.read_parquet(output_dir / "AAPL.parquet")
    assert {"ts_code", "symbol", "vol", "volume"}.issubset(aapl.columns)
    assert aapl["trade_date"].is_monotonic_increasing
    assert aapl["ts_code"].unique().tolist() == ["AAPL"]
    assert aapl["vol"].tolist() == aapl["volume"].tolist()

    skipped_output_dir = tmp_path / "skipped"
    skipped_summary = export_us_daily_by_symbol(input_path, skipped_output_dir, min_rows=3)

    assert skipped_summary.exported_symbols == 0
    assert skipped_summary.skipped_symbols == ["AAPL", "MSFT"]
    assert not (skipped_output_dir / "AAPL.parquet").exists()
