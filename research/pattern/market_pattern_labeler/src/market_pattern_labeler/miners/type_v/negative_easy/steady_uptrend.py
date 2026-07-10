from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


@dataclass
class SteadyUptrendConfig:
    lookback_window: int = 150
    min_history: int = 180
    min_ret_20d: float = 0.05
    min_ret_60d: float = 0.12
    min_position_in_range: float = 0.60
    max_drawdown_from_window_high: float = 0.18
    ma_short_window: int = 20
    ma_long_window: int = 60
    min_ma_short_slope: float = 0.00
    min_ma_long_slope: float = 0.00
    ma_slope_lag: int = 5
    min_candidate_score: int = 5
    top_n_per_symbol: int = 5
    max_candidates_total: int = 8000

    @classmethod
    def from_dict(cls, data: dict) -> "SteadyUptrendConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class SteadyUptrendMiner(BaseMiner):
    name = "steady_uptrend"

    def __init__(self, config: SteadyUptrendConfig):
        self.config = config

    def scan_one(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        out = df.copy()
        if not {"trade_date", "close"}.issubset(out.columns):
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        out["trade_date"] = to_trade_datetime(out["trade_date"])
        out = out.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
        min_required = max(
            self.config.min_history,
            self.config.lookback_window,
            self.config.ma_long_window + self.config.ma_slope_lag + 1,
        )
        if len(out) < min_required:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        close = pd.to_numeric(out["close"], errors="coerce")
        high = pd.to_numeric(out["high"], errors="coerce") if "high" in out.columns else close
        low = pd.to_numeric(out["low"], errors="coerce") if "low" in out.columns else close

        window_high = high.rolling(self.config.lookback_window).max()
        window_low = low.rolling(self.config.lookback_window).min()
        range_width = (window_high - window_low).where((window_high - window_low) > 0)
        position_in_range = (close - window_low) / range_width
        drawdown_from_window_high = 1.0 - close / window_high

        ret_1d = close.pct_change(1)
        ret_3d = close.pct_change(3)
        ret_20d = close.pct_change(20)
        ret_60d = close.pct_change(60)
        ma_short = close.rolling(self.config.ma_short_window).mean()
        ma_long = close.rolling(self.config.ma_long_window).mean()
        ma_short_slope = ma_short / ma_short.shift(self.config.ma_slope_lag) - 1.0
        ma_long_slope = ma_long / ma_long.shift(self.config.ma_slope_lag) - 1.0

        if "vol" in out.columns:
            vol = pd.to_numeric(out["vol"], errors="coerce")
            vol_base = vol.rolling(self.config.lookback_window).mean()
            vol_ratio_1d = vol / vol_base
            vol_ratio_3d = vol.rolling(3).mean() / vol_base
        else:
            vol_ratio_1d = pd.Series([pd.NA] * len(out), index=out.index, dtype="object")
            vol_ratio_3d = pd.Series([pd.NA] * len(out), index=out.index, dtype="object")

        up_20d = ret_20d >= self.config.min_ret_20d
        up_60d = ret_60d >= self.config.min_ret_60d
        high_position = position_in_range >= self.config.min_position_in_range
        shallow_drawdown = drawdown_from_window_high <= self.config.max_drawdown_from_window_high
        ma_short_up = ma_short_slope >= self.config.min_ma_short_slope
        ma_long_up = ma_long_slope >= self.config.min_ma_long_slope

        score = (
            up_20d.astype(int)
            + up_60d.astype(int) * 2
            + high_position.astype(int)
            + shallow_drawdown.astype(int)
            + ma_short_up.astype(int)
            + ma_long_up.astype(int)
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
                "base_range_pct": (window_high - window_low) / window_low,
                "breakout_flag": False,
                "rule_flags": "",
            }
        )
        hit_df = hit_df[score >= int(self.config.min_candidate_score)].copy()
        if hit_df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        def _flags(idx: int) -> str:
            flags: list[str] = []
            if bool(up_20d.loc[idx]):
                flags.append("up_20d")
            if bool(up_60d.loc[idx]):
                flags.append("up_60d")
            if bool(high_position.loc[idx]):
                flags.append("high_position")
            if bool(shallow_drawdown.loc[idx]):
                flags.append("shallow_drawdown")
            if bool(ma_short_up.loc[idx]):
                flags.append("ma20_up")
            if bool(ma_long_up.loc[idx]):
                flags.append("ma60_up")
            flags.append(f"position={position_in_range.loc[idx]:.3f}")
            flags.append(f"drawdown={drawdown_from_window_high.loc[idx]:.3f}")
            return ";".join(flags)

        hit_df["rule_flags"] = [_flags(idx) for idx in hit_df.index]
        hit_df["asof_date"] = pd.to_datetime(hit_df["asof_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        hit_df["sample_id"] = hit_df["ts_code"].astype(str) + "_" + hit_df["asof_date"].astype(str)
        hit_df["event_id"] = hit_df["sample_id"].astype(str) + "_" + self.name
        hit_df = hit_df.sort_values(["candidate_score", "asof_date"], ascending=[False, False])
        if self.config.top_n_per_symbol > 0:
            hit_df = hit_df.head(int(self.config.top_n_per_symbol))

        for col in CANDIDATE_COLUMNS:
            if col not in hit_df.columns:
                hit_df[col] = pd.NA

        return hit_df[CANDIDATE_COLUMNS].reset_index(drop=True)


__all__ = ["SteadyUptrendConfig", "SteadyUptrendMiner"]
