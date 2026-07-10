from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


@dataclass
class WeakSidewaysConfig:
    lookback_window: int = 60
    min_history: int = 80
    max_base_range_pct: float = 0.12
    max_abs_ret_3d: float = 0.02
    max_abs_ret_20d: float = 0.04
    max_vol_ratio_3d: float = 1.05
    top_n_per_symbol: int = 5
    max_candidates_total: int = 8000
    min_candidate_score: int = 4

    @classmethod
    def from_dict(cls, data: dict) -> "WeakSidewaysConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class WeakSidewaysMiner(BaseMiner):
    name = "weak_sideways"

    def __init__(self, config: WeakSidewaysConfig):
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
        base_high = close.rolling(self.config.lookback_window).max()
        base_low = close.rolling(self.config.lookback_window).min()
        base_range_pct = (base_high - base_low) / base_low
        ret_1d = close.pct_change(1)
        ret_3d = close.pct_change(3)
        ret_20d = close.pct_change(20)

        if "vol" in out.columns:
            vol = pd.to_numeric(out["vol"], errors="coerce")
            vol_base = vol.rolling(self.config.lookback_window).mean()
            vol_ratio_3d = vol.rolling(3).mean() / vol_base
        else:
            vol_ratio_3d = pd.Series([pd.NA] * len(out), index=out.index, dtype="object")

        tight_range = base_range_pct <= self.config.max_base_range_pct
        flat_3d = ret_3d.abs() <= self.config.max_abs_ret_3d
        flat_20d = ret_20d.abs() <= self.config.max_abs_ret_20d
        quiet_vol = pd.to_numeric(vol_ratio_3d, errors="coerce").fillna(0.0) <= self.config.max_vol_ratio_3d

        score = (
            tight_range.astype(int) * 2
            + flat_3d.astype(int)
            + flat_20d.astype(int)
            + quiet_vol.astype(int)
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
                "vol_ratio_3d": vol_ratio_3d,
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
            if bool(tight_range.loc[idx]):
                flags.append("tight_range")
            if bool(flat_3d.loc[idx]):
                flags.append("flat_3d")
            if bool(flat_20d.loc[idx]):
                flags.append("flat_20d")
            if bool(quiet_vol.loc[idx]):
                flags.append("quiet_vol")
            return ";".join(flags)

        hit_df["rule_flags"] = [_flags(idx) for idx in hit_df.index]
        hit_df["asof_date"] = pd.to_datetime(hit_df["asof_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        hit_df["sample_id"] = hit_df["ts_code"].astype(str) + "_" + hit_df["asof_date"].astype(str)
        hit_df["event_id"] = hit_df["sample_id"].astype(str) + "_" + self.name
        hit_df = hit_df.sort_values(["candidate_score", "asof_date"], ascending=[False, False])
        if self.config.top_n_per_symbol > 0:
            hit_df = hit_df.head(int(self.config.top_n_per_symbol))

        return hit_df[CANDIDATE_COLUMNS].reset_index(drop=True)


__all__ = ["WeakSidewaysConfig", "WeakSidewaysMiner"]
