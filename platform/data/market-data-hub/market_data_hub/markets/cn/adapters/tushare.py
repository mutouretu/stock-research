"""Tushare adapter for CN A-share daily data."""

from __future__ import annotations

from typing import Any

import pandas as pd


class TushareCNAdapter:
    """Thin wrapper around the Tushare pro client.

    The wrapper keeps the pipeline testable by accepting an injected client.
    Production usage passes a token and lazily imports ``tushare`` here rather
    than at module import time.
    """

    def __init__(self, token: str | None = None, client: Any | None = None) -> None:
        if client is not None:
            self.client = client
            return

        if not token:
            raise ValueError("Missing Tushare token")

        try:
            import tushare as ts
        except ImportError as exc:
            raise ImportError(
                "tushare is required for CN downloads. Install market-data-hub with "
                "the CN data dependencies."
            ) from exc

        ts.set_token(token)
        self.client = ts.pro_api(token)

    def trade_calendar(self, start_date: str, end_date: str) -> pd.DataFrame:
        return self.client.trade_cal(
            exchange="",
            start_date=start_date,
            end_date=end_date,
            is_open="1",
            fields="cal_date",
        )

    def stock_basic(self) -> pd.DataFrame:
        return self.client.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,list_date",
        )

    def daily(self, trade_date: str) -> pd.DataFrame:
        return self.client.daily(trade_date=trade_date)

    def daily_basic(self, trade_date: str) -> pd.DataFrame:
        return self.client.daily_basic(trade_date=trade_date)

    def cyq_perf(self, trade_date: str) -> pd.DataFrame:
        return self.client.cyq_perf(trade_date=trade_date)

    def stk_factor(self, trade_date: str) -> pd.DataFrame:
        return self.client.stk_factor_pro(trade_date=trade_date)

    def stock_st(self, trade_date: str) -> pd.DataFrame:
        return self.client.stock_st(trade_date=trade_date)

    def suspend(self, trade_date: str) -> pd.DataFrame:
        return self.client.suspend_d(trade_date=trade_date, suspend_type="S")
