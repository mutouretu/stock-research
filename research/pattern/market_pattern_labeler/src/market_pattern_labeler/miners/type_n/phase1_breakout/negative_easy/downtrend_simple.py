from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


@dataclass
class DowntrendSimpleConfig:
    lookback_window: int = 60
    min_history: int = 80
    max_ret_20d: float = -0.08
    max_ret_60d: float = -0.15
    max_ret_3d: float = 0.02
    ma_window: int = 20
    ma_gap_threshold: float = 0.03
    top_n_per_symbol: int = 5
    max_candidates_total: int = 8000
    min_candidate_score: int = 4

    @classmethod
    def from_dict(cls, data: dict) -> "DowntrendSimpleConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class DowntrendSimpleMiner(BaseMiner):
    name = "downtrend_simple"

    def __init__(self, config: DowntrendSimpleConfig):
        self.config = config

    def scan_one(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        out = df.copy()
        if "trade_date" not in out.columns or "close" not in out.columns:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        out["trade_date"] = to_trade_datetime(out["trade_date"])
        out = out.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
        if len(out) < max(self.config.min_history, self.config.lookback_window):
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        close = pd.to_numeric(out["close"], errors="coerce")
        ret_3d = close.pct_change(3)
        ret_20d = close.pct_change(20)
        ret_60d = close.pct_change(60)
        ma = close.rolling(self.config.ma_window).mean()
        ma_gap = (ma - close) / ma

        down_20d = ret_20d <= self.config.max_ret_20d
        down_60d = ret_60d <= self.config.max_ret_60d
        weak_rebound = ret_3d <= self.config.max_ret_3d
        below_ma = ma_gap >= self.config.ma_gap_threshold

        score = (
            down_20d.astype(int)
            + down_60d.astype(int) * 2
            + weak_rebound.astype(int)
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
                "ret_1d": close.pct_change(1),
                "ret_3d": ret_3d,
                "vol_ratio_1d": pd.NA,
                "vol_ratio_3d": pd.NA,
                "base_window_days": int(self.config.lookback_window),
                "base_range_pct": pd.NA,
                "breakout_flag": False,
                "rule_flags": "",
            }
        )
        hit_df = hit_df[score >= int(self.config.min_candidate_score)].copy()
        if hit_df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        def _flags(idx: int) -> str:
            flags: list[str] = []
            if bool(down_20d.loc[idx]):
                flags.append("down_20d")
            if bool(down_60d.loc[idx]):
                flags.append("down_60d")
            if bool(weak_rebound.loc[idx]):
                flags.append("weak_rebound")
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


__all__ = ["DowntrendSimpleConfig", "DowntrendSimpleMiner"]
