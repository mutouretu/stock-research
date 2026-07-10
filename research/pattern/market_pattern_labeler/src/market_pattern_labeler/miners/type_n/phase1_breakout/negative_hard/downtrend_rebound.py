from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


@dataclass
class DowntrendReboundConfig:
    lookback_window: int = 60
    min_history: int = 80
    max_ret_60d: float = -0.12
    min_ret_3d: float = 0.04
    max_ret_20d: float = -0.03
    min_ma_gap: float = 0.02
    min_candidate_score: int = 4
    top_n_per_symbol: int = 5
    max_candidates_total: int = 8000

    @classmethod
    def from_dict(cls, data: dict) -> "DowntrendReboundConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class DowntrendReboundMiner(BaseMiner):
    name = "downtrend_rebound"

    def __init__(self, config: DowntrendReboundConfig):
        self.config = config

    def scan_one(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        out = df.copy()
        if not {"trade_date", "close"}.issubset(out.columns):
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        out["trade_date"] = to_trade_datetime(out["trade_date"])
        out = out.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
        if len(out) < max(self.config.min_history, self.config.lookback_window):
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        close = pd.to_numeric(out["close"], errors="coerce")
        ret_1d = close.pct_change(1)
        ret_3d = close.pct_change(3)
        ret_20d = close.pct_change(20)
        ret_60d = close.pct_change(60)
        ma_20 = close.rolling(20).mean()
        ma_gap = (ma_20 - close) / ma_20

        trend_down = ret_60d <= self.config.max_ret_60d
        rebound_up = ret_3d >= self.config.min_ret_3d
        still_weak = ret_20d <= self.config.max_ret_20d
        below_ma = ma_gap >= self.config.min_ma_gap

        score = (
            trend_down.astype(int) * 2
            + rebound_up.astype(int)
            + still_weak.astype(int)
            + below_ma.astype(int)
        )

        hit_df = pd.DataFrame(
            {
                "sample_id": "",
                "ts_code": ts_code,
                "asof_date": out["trade_date"],
                "label": 0,
                "label_source": self.name,
                "confidence": 1.0,
                "event_id": "",
                "miner_name": self.name,
                "candidate_score": score,
                "close": close,
                "ret_1d": ret_1d,
                "ret_3d": ret_3d,
                "vol_ratio_1d": pd.NA,
                "vol_ratio_3d": pd.NA,
                "base_window_days": int(self.config.lookback_window),
                "base_range_pct": pd.NA,
                "breakout_flag": False,
                "rule_flags": "",
            }
        )
        hit_df = hit_df[(score >= int(self.config.min_candidate_score)) & trend_down & rebound_up].copy()
        if hit_df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        def _flags(idx: int) -> str:
            flags: list[str] = []
            if bool(trend_down.loc[idx]):
                flags.append("trend_down")
            if bool(rebound_up.loc[idx]):
                flags.append("rebound_up")
            if bool(still_weak.loc[idx]):
                flags.append("still_weak")
            if bool(below_ma.loc[idx]):
                flags.append("below_ma")
            return ";".join(flags)

        hit_df["rule_flags"] = [_flags(idx) for idx in hit_df.index]
        hit_df["asof_date"] = pd.to_datetime(hit_df["asof_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        hit_df["sample_id"] = hit_df["ts_code"].astype(str) + "_" + hit_df["asof_date"].astype(str)
        hit_df["event_id"] = hit_df["sample_id"].astype(str) + "_" + self.name
        hit_df = hit_df.sort_values(["candidate_score", "asof_date"], ascending=[False, False])
        if self.config.top_n_per_symbol > 0:
            hit_df = hit_df.head(int(self.config.top_n_per_symbol))
        return hit_df[CANDIDATE_COLUMNS].reset_index(drop=True)
