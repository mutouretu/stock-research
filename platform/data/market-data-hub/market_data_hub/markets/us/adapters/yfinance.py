"""yfinance-backed US market adapter."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
import yfinance as yf

from market_data_hub.core.instruments import build_instrument_id
from market_data_hub.core.schemas import CorporateAction, DailyPrice, Instrument
from market_data_hub.markets.us.adapters.base import USMarketDataAdapter

logger = logging.getLogger(__name__)


class YFinanceUSAdapter(USMarketDataAdapter):
    source = "yfinance"

    def get_instruments(self, symbols: list[str] | None = None) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for symbol in symbols or []:
            instrument = Instrument(
                instrument_id=build_instrument_id("US", symbol),
                symbol=symbol.upper(),
                market="US",
                asset_type="equity",
                currency="USD",
                is_active=True,
                source=self.source,
            )
            rows.append(instrument.model_dump(mode="python"))
        return pd.DataFrame(rows)

    def get_daily_prices(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            try:
                history = self._download_symbol_history(symbol, start_date, end_date, interval)
            except Exception as exc:
                logger.error("Failed to download daily prices for symbol=%s: %s", symbol, exc)
                continue

            if history.empty:
                logger.warning("No daily price data returned for symbol=%s", symbol)
                continue

            for trade_date, record in history.iterrows():
                normalized_date = _normalize_date(trade_date)
                price = DailyPrice(
                    instrument_id=build_instrument_id("US", symbol),
                    symbol=symbol.upper(),
                    market="US",
                    trade_date=normalized_date,
                    open=_to_float(record.get("Open")),
                    high=_to_float(record.get("High")),
                    low=_to_float(record.get("Low")),
                    close=_to_float(record.get("Close")),
                    volume=_to_float(record.get("Volume")),
                    adj_close=_to_float(record.get("Adj Close")),
                    dividends=_to_float(record.get("Dividends")),
                    stock_splits=_to_float(record.get("Stock Splits")),
                    source=self.source,
                )
                rows.append(price.model_dump(mode="python"))

        return pd.DataFrame(rows)

    def get_corporate_actions(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date) if end_date else None

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                dividends = _filter_series_dates(ticker.dividends, start, end)
                splits = _filter_series_dates(ticker.splits, start, end)
            except Exception as exc:
                logger.error("Failed to download corporate actions for symbol=%s: %s", symbol, exc)
                continue

            for action_date, value in dividends.items():
                rows.append(
                    CorporateAction(
                        instrument_id=build_instrument_id("US", symbol),
                        symbol=symbol.upper(),
                        market="US",
                        action_date=_normalize_date(action_date),
                        action_type="dividend",
                        value=_to_float(value),
                        source=self.source,
                    ).model_dump(mode="python")
                )

            for action_date, value in splits.items():
                rows.append(
                    CorporateAction(
                        instrument_id=build_instrument_id("US", symbol),
                        symbol=symbol.upper(),
                        market="US",
                        action_date=_normalize_date(action_date),
                        action_type="stock_split",
                        value=_to_float(value),
                        source=self.source,
                    ).model_dump(mode="python")
                )

        return pd.DataFrame(rows)

    def _download_symbol_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str | None,
        interval: str,
    ) -> pd.DataFrame:
        ticker = yf.Ticker(symbol)
        history = ticker.history(
            start=start_date,
            end=end_date,
            interval=interval,
            auto_adjust=False,
            actions=True,
        )
        if history.empty:
            return history
        return history.reset_index().set_index("Date")


def _normalize_date(value: object) -> date:
    return pd.Timestamp(value).date()


def _to_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _filter_series_dates(
    series: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp | None,
) -> pd.Series:
    if series.empty:
        return series
    index = series.index.tz_localize(None) if getattr(series.index, "tz", None) else series.index
    filtered = series.copy()
    filtered.index = index
    filtered = filtered[filtered.index >= start]
    if end is not None:
        filtered = filtered[filtered.index <= end]
    return filtered
