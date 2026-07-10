from datetime import date

from market_data_hub.core.schemas import DailyPrice, Instrument


def test_instrument_schema_defaults() -> None:
    instrument = Instrument(
        instrument_id="US:AAPL",
        symbol="AAPL",
        market="US",
        source="yfinance",
    )

    assert instrument.asset_type == "equity"
    assert instrument.is_active is True


def test_daily_price_schema() -> None:
    price = DailyPrice(
        instrument_id="US:AAPL",
        symbol="AAPL",
        market="US",
        trade_date=date(2026, 7, 1),
        close=100.0,
        adj_close=99.0,
        source="yfinance",
    )

    assert price.trade_date == date(2026, 7, 1)
    assert price.adj_close == 99.0
