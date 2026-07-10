import pandas as pd
import pytest

from market_data_hub.exceptions import DataDownloadError
from market_data_hub.markets.us.pipelines.download_instruments import (
    INSTRUMENT_COLUMNS,
    _sort_columns,
)
from market_data_hub.markets.us.pipelines import download_prices
from market_data_hub.markets.us.pipelines.download_prices import (
    DAILY_PRICE_COLUMNS,
    _normalize_prices_frame,
)


def test_instrument_columns_are_preserved() -> None:
    data = pd.DataFrame([{"symbol": "AAPL", "market": "US", "source": "test"}])

    normalized = _sort_columns(data)

    assert list(normalized.columns) == INSTRUMENT_COLUMNS


def test_daily_price_columns_are_preserved() -> None:
    data = pd.DataFrame(
        [
            {
                "instrument_id": "US:AAPL",
                "symbol": "AAPL",
                "market": "US",
                "trade_date": "2026-07-01",
                "close": 100.0,
                "source": "test",
            }
        ]
    )

    normalized = _normalize_prices_frame(data)

    assert list(normalized.columns) == DAILY_PRICE_COLUMNS


def test_download_prices_uses_configured_window_and_interval(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "us.yaml"
    config_path.write_text(
        f"""
market: US
default_source: yfinance

storage:
  backend: parquet
  root_dir: "{tmp_path / "data"}"

universe:
  symbols:
    - AAPL

download:
  start_date: "2015-01-01"
  end_date: null
  interval: "1d"
""",
        encoding="utf-8",
    )

    class FixedDate:
        @classmethod
        def today(cls):
            return pd.Timestamp("2026-07-04").date()

    class FakeAdapter:
        def __init__(self) -> None:
            self.calls = []

        def get_daily_prices(
            self,
            symbols: list[str],
            start_date: str,
            end_date: str | None = None,
            interval: str = "1d",
        ) -> pd.DataFrame:
            self.calls.append((symbols, start_date, end_date, interval))
            return pd.DataFrame(
                [
                    {
                        "instrument_id": "US:AAPL",
                        "symbol": "AAPL",
                        "market": "US",
                        "trade_date": "2026-07-01",
                        "open": 100.0,
                        "high": 101.0,
                        "low": 99.0,
                        "close": 100.5,
                        "volume": 1000,
                        "adj_close": 100.5,
                        "source": "test",
                    }
                ]
            )

    adapter = FakeAdapter()
    monkeypatch.setattr(download_prices, "date", FixedDate)
    monkeypatch.setattr(download_prices, "create_us_adapter", lambda source: adapter)

    download_prices.run(config_path)

    assert adapter.calls == [(["AAPL"], "2015-01-01", "2026-07-04", "1d")]


def test_download_prices_raises_when_configured_symbols_return_no_rows(
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "us.yaml"
    config_path.write_text(
        f"""
market: US
default_source: yfinance

storage:
  backend: parquet
  root_dir: "{tmp_path / "data"}"

universe:
  symbols:
    - AAPL

download:
  start_date: "2015-01-01"
  end_date: "2026-07-04"
  interval: "1d"
""",
        encoding="utf-8",
    )

    class EmptyAdapter:
        def get_daily_prices(
            self,
            symbols: list[str],
            start_date: str,
            end_date: str | None = None,
            interval: str = "1d",
        ) -> pd.DataFrame:
            return pd.DataFrame(columns=DAILY_PRICE_COLUMNS)

    monkeypatch.setattr(download_prices, "create_us_adapter", lambda source: EmptyAdapter())

    with pytest.raises(DataDownloadError, match="No US daily prices downloaded"):
        download_prices.run(config_path)
