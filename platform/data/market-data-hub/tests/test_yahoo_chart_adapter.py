from market_data_hub.markets.us.adapters.factory import create_us_adapter
from market_data_hub.markets.us.adapters.yahoo_chart import (
    YahooChartUSAdapter,
    _parse_daily_prices,
)


def test_factory_creates_yahoo_chart_adapter() -> None:
    adapter = create_us_adapter("yahoo_chart")

    assert isinstance(adapter, YahooChartUSAdapter)


def test_parse_yahoo_chart_daily_prices() -> None:
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1577923200],
                    "indicators": {
                        "quote": [
                            {
                                "open": [10.0],
                                "high": [11.0],
                                "low": [9.5],
                                "close": [10.5],
                                "volume": [1000],
                            }
                        ],
                        "adjclose": [{"adjclose": [10.4]}],
                    },
                    "events": {
                        "dividends": {
                            "1577923200": {"date": 1577923200, "amount": 0.2}
                        },
                        "splits": {
                            "1577923200": {
                                "date": 1577923200,
                                "numerator": 4,
                                "denominator": 1,
                            }
                        },
                    },
                }
            ],
            "error": None,
        }
    }

    rows = _parse_daily_prices("AAPL", payload, "yahoo_chart")

    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "AAPL"
    assert row["market"] == "US"
    assert row["open"] == 10.0
    assert row["adj_close"] == 10.4
    assert row["dividends"] == 0.2
    assert row["stock_splits"] == 4.0
    assert row["source"] == "yahoo_chart"
