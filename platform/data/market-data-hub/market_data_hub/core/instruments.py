"""Instrument helpers."""

from __future__ import annotations


def build_instrument_id(market: str, symbol: str) -> str:
    return f"{market.upper()}:{symbol.upper()}"
