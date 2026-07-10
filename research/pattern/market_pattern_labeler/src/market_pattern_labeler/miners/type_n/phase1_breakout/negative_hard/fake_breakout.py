from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


@dataclass
class FakeBreakoutConfig:
    lookback_window: int = 60
    min_history: int = 90
    max_base_range_pct: float = 0.25
    min_ret_1d: float = 0.02
    min_ret_3d: float = 0.05
    min_vol_ratio_1d: float = 1.5
    breakout_tolerance: float = 0.01
    future_window: int = 5
    max_future_ret: float = 0.02
    min_candidate_score: int = 5
    top_n_per_symbol: int = 5
    max_candidates_total: int = 8000

    @classmethod
    def from_dict(cls, data: dict) -> "FakeBreakoutConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class FakeBreakoutMiner(BaseMiner):
    name = "fake_breakout"

    def __init__(self, config: FakeBreakoutConfig):
        self.config = config

    def scan_one(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        out = df.copy()
        required = {"trade_date", "close"}
        if not required.issubset(out.columns):
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        out["trade_date"] = to_trade_datetime(out["trade_date"])
        out = out.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
        if len(out) < max(self.config.min_history, self.config.lookback_window + self.config.future_window):
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        close = pd.to_numeric(out["close"], errors="coerce")
        ret_1d = close.pct_change(1)
        ret_3d = close.pct_change(3)
        base_high_prev = close.rolling(self.config.lookback_window).max().shift(1)
        base_low_prev = close.rolling(self.config.lookback_window).min().shift(1)
        base_range_pct = (base_high_prev - base_low_prev) / base_low_prev
        breakout_flag = close >= base_high_prev * (1 - self.config.breakout_tolerance)

        if "vol" in out.columns:
            vol = pd.to_numeric(out["vol"], errors="coerce")
            vol_base = vol.rolling(self.config.lookback_window).mean().shift(1)
            vol_ratio_1d = vol / vol_base
        else:
            vol_ratio_1d = pd.Series([pd.NA] * len(out), index=out.index, dtype="object")

        future_max_close = close.shift(-1).rolling(self.config.future_window).max()
        future_ret = (future_max_close - close) / close

        base_ok = base_range_pct <= self.config.max_base_range_pct
        ret_ok_1d = ret_1d >= self.config.min_ret_1d
        ret_ok_3d = ret_3d >= self.config.min_ret_3d
        vol_ok = pd.to_numeric(vol_ratio_1d, errors="coerce").fillna(0.0) >= self.config.min_vol_ratio_1d
        fail_follow_through = pd.to_numeric(future_ret, errors="coerce").fillna(0.0) <= self.config.max_future_ret

        score = (
            base_ok.astype(int)
            + ret_ok_1d.astype(int)
            + ret_ok_3d.astype(int)
            + vol_ok.astype(int)
            + breakout_flag.astype(int)
            + fail_follow_through.astype(int)
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
                "vol_ratio_3d": pd.NA,
                "base_window_days": int(self.config.lookback_window),
                "base_range_pct": base_range_pct,
                "breakout_flag": breakout_flag.fillna(False),
                "rule_flags": "",
            }
        )
        hit_df = hit_df[(score >= int(self.config.min_candidate_score)) & fail_follow_through].copy()
        if hit_df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        def _flags(idx: int) -> str:
            flags: list[str] = []
            if bool(base_ok.loc[idx]):
                flags.append("base_ok")
            if bool(ret_ok_1d.loc[idx]):
                flags.append("ret_1d_ok")
            if bool(ret_ok_3d.loc[idx]):
                flags.append("ret_3d_ok")
            if bool(vol_ok.loc[idx]):
                flags.append("vol_ok")
            if bool(breakout_flag.loc[idx]):
                flags.append("breakout_ok")
            if bool(fail_follow_through.loc[idx]):
                flags.append("fail_follow_through")
            return ";".join(flags)

        hit_df["rule_flags"] = [_flags(idx) for idx in hit_df.index]
        hit_df["asof_date"] = pd.to_datetime(hit_df["asof_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        hit_df["sample_id"] = hit_df["ts_code"].astype(str) + "_" + hit_df["asof_date"].astype(str)
        hit_df["event_id"] = hit_df["sample_id"].astype(str) + "_" + self.name
        hit_df = hit_df.sort_values(["candidate_score", "asof_date"], ascending=[False, False])
        if self.config.top_n_per_symbol > 0:
            hit_df = hit_df.head(int(self.config.top_n_per_symbol))
        return hit_df[CANDIDATE_COLUMNS].reset_index(drop=True)
