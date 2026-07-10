from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


@dataclass
class VolumeOnlySpikeConfig:
    lookback_window: int = 60
    min_history: int = 80
    min_vol_ratio_1d: float = 2.5
    min_vol_ratio_3d: float = 1.8
    max_abs_ret_1d: float = 0.02
    max_ret_3d: float = 0.03
    breakout_tolerance: float = 0.01
    min_candidate_score: int = 4
    top_n_per_symbol: int = 5
    max_candidates_total: int = 8000

    @classmethod
    def from_dict(cls, data: dict) -> "VolumeOnlySpikeConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class VolumeOnlySpikeMiner(BaseMiner):
    name = "volume_only_spike"

    def __init__(self, config: VolumeOnlySpikeConfig):
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
        base_high_prev = close.rolling(self.config.lookback_window).max().shift(1)
        breakout_flag = close >= base_high_prev * (1 - self.config.breakout_tolerance)

        if "vol" in out.columns:
            vol = pd.to_numeric(out["vol"], errors="coerce")
            vol_base = vol.rolling(self.config.lookback_window).mean().shift(1)
            vol_ratio_1d = vol / vol_base
            vol_ratio_3d = vol.rolling(3).mean() / vol_base
        else:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        spike_1d = pd.to_numeric(vol_ratio_1d, errors="coerce").fillna(0.0) >= self.config.min_vol_ratio_1d
        spike_3d = pd.to_numeric(vol_ratio_3d, errors="coerce").fillna(0.0) >= self.config.min_vol_ratio_3d
        weak_price_1d = ret_1d.abs() <= self.config.max_abs_ret_1d
        weak_price_3d = ret_3d <= self.config.max_ret_3d
        no_breakout = ~breakout_flag.fillna(False)

        score = (
            spike_1d.astype(int)
            + spike_3d.astype(int)
            + weak_price_1d.astype(int)
            + weak_price_3d.astype(int)
            + no_breakout.astype(int)
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
                "vol_ratio_1d": vol_ratio_1d,
                "vol_ratio_3d": vol_ratio_3d,
                "base_window_days": int(self.config.lookback_window),
                "base_range_pct": pd.NA,
                "breakout_flag": breakout_flag.fillna(False),
                "rule_flags": "",
            }
        )
        hit_df = hit_df[(score >= int(self.config.min_candidate_score)) & spike_1d & no_breakout].copy()
        if hit_df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        def _flags(idx: int) -> str:
            flags: list[str] = []
            if bool(spike_1d.loc[idx]):
                flags.append("spike_1d")
            if bool(spike_3d.loc[idx]):
                flags.append("spike_3d")
            if bool(weak_price_1d.loc[idx]):
                flags.append("weak_price_1d")
            if bool(weak_price_3d.loc[idx]):
                flags.append("weak_price_3d")
            if bool(no_breakout.loc[idx]):
                flags.append("no_breakout")
            return ";".join(flags)

        hit_df["rule_flags"] = [_flags(idx) for idx in hit_df.index]
        hit_df["asof_date"] = pd.to_datetime(hit_df["asof_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        hit_df["sample_id"] = hit_df["ts_code"].astype(str) + "_" + hit_df["asof_date"].astype(str)
        hit_df["event_id"] = hit_df["sample_id"].astype(str) + "_" + self.name
        hit_df = hit_df.sort_values(["candidate_score", "asof_date"], ascending=[False, False])
        if self.config.top_n_per_symbol > 0:
            hit_df = hit_df.head(int(self.config.top_n_per_symbol))
        return hit_df[CANDIDATE_COLUMNS].reset_index(drop=True)
