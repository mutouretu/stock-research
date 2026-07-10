import pandas as pd

from market_data_hub.exports.parquet import ParquetExporter


def test_save_and_load_daily_prices(tmp_path) -> None:
    exporter = ParquetExporter(tmp_path)
    prices = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "market": "US",
                "trade_date": "2026-07-01",
                "close": 100.0,
                "adj_close": 100.0,
                "source": "test",
                "created_at": "2026-07-01T00:00:00Z",
            }
        ]
    )

    path = exporter.save_daily_prices(prices, "US")
    loaded = exporter.load_daily_prices("US")

    assert path.exists()
    assert len(loaded) == 1
    assert loaded.loc[0, "symbol"] == "AAPL"
