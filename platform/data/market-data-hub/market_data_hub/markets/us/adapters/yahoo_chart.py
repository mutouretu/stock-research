"""Yahoo Chart API-backed US market adapter."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import ssl

import certifi
import pandas as pd

from market_data_hub.core.instruments import build_instrument_id
from market_data_hub.core.schemas import CorporateAction, DailyPrice, Instrument
from market_data_hub.markets.us.adapters.base import USMarketDataAdapter

logger = logging.getLogger(__name__)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


class YahooChartUSAdapter(USMarketDataAdapter):
    source = "yahoo_chart"

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
                payload = self._fetch_chart(symbol, start_date, end_date, interval)
                rows.extend(_parse_daily_prices(symbol, payload, self.source))
            except Exception as exc:
                logger.error("Failed to download daily prices for symbol=%s: %s", symbol, exc)
                continue
        return pd.DataFrame(rows)

    def get_corporate_actions(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            try:
                payload = self._fetch_chart(symbol, start_date, end_date, "1d")
                rows.extend(_parse_corporate_actions(symbol, payload, self.source))
            except Exception as exc:
                logger.error("Failed to download corporate actions for symbol=%s: %s", symbol, exc)
                continue
        return pd.DataFrame(rows)

    def _fetch_chart(
        self,
        symbol: str,
        start_date: str,
        end_date: str | None,
        interval: str,
    ) -> dict[str, Any]:
        params = {
            "period1": _to_unix_start(start_date),
            "period2": _to_unix_end(end_date),
            "interval": interval,
            "events": "div,splits",
        }
        url = f"{YAHOO_CHART_URL.format(symbol=symbol.upper())}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        context = ssl.create_default_context(cafile=certifi.where())
        with urlopen(request, timeout=30, context=context) as response:
            return json.loads(response.read().decode("utf-8"))


def _parse_daily_prices(
    symbol: str,
    payload: dict[str, Any],
    source: str,
) -> list[dict[str, Any]]:
    result = _chart_result(payload)
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    adjclose = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
    events = result.get("events") or {}
    dividends = _event_values_by_date(events.get("dividends") or {}, "amount")
    splits = _split_values_by_date(events.get("splits") or {})

    rows: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps):
        trade_date = _timestamp_to_date(timestamp)
        price = DailyPrice(
            instrument_id=build_instrument_id("US", symbol),
            symbol=symbol.upper(),
            market="US",
            trade_date=trade_date,
            open=_list_get(quote.get("open"), index),
            high=_list_get(quote.get("high"), index),
            low=_list_get(quote.get("low"), index),
            close=_list_get(quote.get("close"), index),
            volume=_list_get(quote.get("volume"), index),
            adj_close=_list_get(adjclose, index),
            dividends=dividends.get(trade_date),
            stock_splits=splits.get(trade_date),
            source=source,
        )
        rows.append(price.model_dump(mode="python"))
    return rows


def _parse_corporate_actions(
    symbol: str,
    payload: dict[str, Any],
    source: str,
) -> list[dict[str, Any]]:
    result = _chart_result(payload)
    events = result.get("events") or {}
    rows: list[dict[str, Any]] = []
    for action in (events.get("dividends") or {}).values():
        rows.append(
            CorporateAction(
                instrument_id=build_instrument_id("US", symbol),
                symbol=symbol.upper(),
                market="US",
                action_date=_timestamp_to_date(action["date"]),
                action_type="dividend",
                value=action.get("amount"),
                source=source,
            ).model_dump(mode="python")
        )
    for action in (events.get("splits") or {}).values():
        rows.append(
            CorporateAction(
                instrument_id=build_instrument_id("US", symbol),
                symbol=symbol.upper(),
                market="US",
                action_date=_timestamp_to_date(action["date"]),
                action_type="stock_split",
                value=_split_value(action),
                source=source,
            ).model_dump(mode="python")
        )
    return rows


def _chart_result(payload: dict[str, Any]) -> dict[str, Any]:
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise ValueError(chart["error"])
    results = chart.get("result") or []
    if not results:
        raise ValueError("Yahoo Chart returned no result")
    return results[0]


def _to_unix_start(value: str) -> int:
    day = pd.Timestamp(value).date()
    return int(datetime.combine(day, time.min, tzinfo=timezone.utc).timestamp())


def _to_unix_end(value: str | None) -> int:
    day = pd.Timestamp(value).date() if value else date.today()
    return int(datetime.combine(day, time.max, tzinfo=timezone.utc).timestamp())


def _timestamp_to_date(value: int | float) -> date:
    return datetime.fromtimestamp(value, tz=timezone.utc).date()


def _list_get(values: list[Any] | None, index: int) -> float | None:
    if values is None or index >= len(values):
        return None
    value = values[index]
    if value is None or pd.isna(value):
        return None
    return float(value)


def _event_values_by_date(events: dict[str, dict[str, Any]], field: str) -> dict[date, float]:
    values: dict[date, float] = {}
    for event in events.values():
        values[_timestamp_to_date(event["date"])] = float(event[field])
    return values


def _split_values_by_date(events: dict[str, dict[str, Any]]) -> dict[date, float]:
    values: dict[date, float] = {}
    for event in events.values():
        values[_timestamp_to_date(event["date"])] = _split_value(event)
    return values


def _split_value(event: dict[str, Any]) -> float:
    numerator = event.get("numerator")
    denominator = event.get("denominator")
    if numerator is not None and denominator:
        return float(numerator) / float(denominator)
    split_ratio = str(event.get("splitRatio", ""))
    if ":" in split_ratio:
        left, right = split_ratio.split(":", 1)
        return float(left) / float(right)
    return 0.0
