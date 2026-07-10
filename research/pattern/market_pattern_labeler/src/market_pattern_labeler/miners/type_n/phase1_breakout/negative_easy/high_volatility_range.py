from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


@dataclass
class HighVolatilityRangeConfig:
    lookback_window: int = 60
    min_history: int = 80
    min_base_range_pct: float = 0.35
    min_avg_intraday_range: float = 0.04
    max_abs_ret_20d: float = 0.10
    top_n_per_symbol: int = 5
    max_candidates_total: int = 8000
    min_candidate_score: int = 4

    @classmethod
    def from_dict(cls, data: dict) -> "HighVolatilityRangeConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class HighVolatilityRangeMiner(BaseMiner):
    name = "high_volatility_range"

    def __init__(self, config: HighVolatilityRangeConfig):
        self.config = config

    def scan_one(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        out = df.copy()
        required = {"trade_date", "close", "high", "low"}
        if not required.issubset(out.columns):
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        out["trade_date"] = to_trade_datetime(out["trade_date"])
        out = out.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
        if len(out) < max(self.config.min_history, self.config.lookback_window):
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        close = pd.to_numeric(out["close"], errors="coerce")
        high = pd.to_numeric(out["high"], errors="coerce")
        low = pd.to_numeric(out["low"], errors="coerce")
        ret_1d = close.pct_change(1)
        ret_3d = close.pct_change(3)
        ret_20d = close.pct_change(20)

        base_high = close.rolling(self.config.lookback_window).max()
        base_low = close.rolling(self.config.lookback_window).min()
        base_range_pct = (base_high - base_low) / base_low
        intraday_range = (high - low) / close.replace(0, pd.NA)
        avg_intraday_range = intraday_range.rolling(20).mean()

        wide_range = base_range_pct >= self.config.min_base_range_pct
        noisy_range = avg_intraday_range >= self.config.min_avg_intraday_range
        non_trend = ret_20d.abs() <= self.config.max_abs_ret_20d

        score = wide_range.astype(int) * 2 + noisy_range.astype(int) * 2 + non_trend.astype(int)

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
                "base_range_pct": base_range_pct,
                "breakout_flag": False,
                "rule_flags": "",
            }
        )
        hit_df = hit_df[score >= int(self.config.min_candidate_score)].copy()
        if hit_df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        def _flags(idx: int) -> str:
            flags: list[str] = []
            if bool(wide_range.loc[idx]):
                flags.append("wide_range")
            if bool(noisy_range.loc[idx]):
                flags.append("noisy_range")
            if bool(non_trend.loc[idx]):
                flags.append("non_trend")
            return ";".join(flags)

        hit_df["rule_flags"] = [_flags(idx) for idx in hit_df.index]
        hit_df["asof_date"] = pd.to_datetime(hit_df["asof_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        hit_df["sample_id"] = hit_df["ts_code"].astype(str) + "_" + hit_df["asof_date"].astype(str)
        hit_df["event_id"] = hit_df["sample_id"].astype(str) + "_" + self.name
        hit_df = hit_df.sort_values(["candidate_score", "asof_date"], ascending=[False, False])
        if self.config.top_n_per_symbol > 0:
            hit_df = hit_df.head(int(self.config.top_n_per_symbol))

        return hit_df[CANDIDATE_COLUMNS].reset_index(drop=True)


__all__ = ["HighVolatilityRangeConfig", "HighVolatilityRangeMiner"]
