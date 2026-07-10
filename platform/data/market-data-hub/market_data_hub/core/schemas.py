"""Unified schemas for normalized market data."""

from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Instrument(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instrument_id: str
    symbol: str
    market: str
    exchange: str | None = None
    name: str | None = None
    asset_type: str = "equity"
    sector: str | None = None
    industry: str | None = None
    currency: str | None = None
    is_active: bool = True
    list_date: date | None = None
    delist_date: date | None = None
    source: str
    updated_at: datetime = Field(default_factory=utc_now)


class DailyPrice(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instrument_id: str
    symbol: str
    market: str
    trade_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    adj_close: float | None = None
    dividends: float | None = None
    stock_splits: float | None = None
    source: str
    created_at: datetime = Field(default_factory=utc_now)


class CorporateAction(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instrument_id: str
    symbol: str
    market: str
    action_date: date
    action_type: str
    value: float | str | None = None
    source: str
    created_at: datetime = Field(default_factory=utc_now)
