from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


@dataclass
class LateStageAccelerationConfig:
    lookback_window: int = 60
    min_history: int = 80
    min_ret_60d: float = 0.30
    min_ret_20d: float = 0.10
    min_ret_3d: float = 0.05
    breakout_tolerance: float = 0.02
    max_base_range_pct: float = 0.45
    min_candidate_score: int = 4
    top_n_per_symbol: int = 5
    max_candidates_total: int = 8000

    @classmethod
    def from_dict(cls, data: dict) -> "LateStageAccelerationConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class LateStageAccelerationMiner(BaseMiner):
    name = "late_stage_acceleration"

    def __init__(self, config: LateStageAccelerationConfig):
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
        base_high = close.rolling(self.config.lookback_window).max()
        base_low = close.rolling(self.config.lookback_window).min()
        base_range_pct = (base_high - base_low) / base_low
        breakout_flag = close >= base_high * (1 - self.config.breakout_tolerance)

        long_up = ret_60d >= self.config.min_ret_60d
        medium_up = ret_20d >= self.config.min_ret_20d
        short_accel = ret_3d >= self.config.min_ret_3d
        already_extended = base_range_pct >= self.config.max_base_range_pct

        score = (
            long_up.astype(int) * 2
            + medium_up.astype(int)
            + short_accel.astype(int)
            + breakout_flag.astype(int)
            + already_extended.astype(int)
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
                "base_range_pct": base_range_pct,
                "breakout_flag": breakout_flag.fillna(False),
                "rule_flags": "",
            }
        )
        hit_df = hit_df[(score >= int(self.config.min_candidate_score)) & long_up & short_accel].copy()
        if hit_df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        def _flags(idx: int) -> str:
            flags: list[str] = []
            if bool(long_up.loc[idx]):
                flags.append("long_up")
            if bool(medium_up.loc[idx]):
                flags.append("medium_up")
            if bool(short_accel.loc[idx]):
                flags.append("short_accel")
            if bool(breakout_flag.loc[idx]):
                flags.append("breakout_ok")
            if bool(already_extended.loc[idx]):
                flags.append("already_extended")
            return ";".join(flags)

        hit_df["rule_flags"] = [_flags(idx) for idx in hit_df.index]
        hit_df["asof_date"] = pd.to_datetime(hit_df["asof_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        hit_df["sample_id"] = hit_df["ts_code"].astype(str) + "_" + hit_df["asof_date"].astype(str)
        hit_df["event_id"] = hit_df["sample_id"].astype(str) + "_" + self.name
        hit_df = hit_df.sort_values(["candidate_score", "asof_date"], ascending=[False, False])
        if self.config.top_n_per_symbol > 0:
            hit_df = hit_df.head(int(self.config.top_n_per_symbol))
        return hit_df[CANDIDATE_COLUMNS].reset_index(drop=True)
