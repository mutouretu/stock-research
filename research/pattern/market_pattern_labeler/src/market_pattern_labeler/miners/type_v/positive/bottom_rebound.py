from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


@dataclass
class BottomReboundConfig:
    bottom_window: int = 150
    rebound_window: int = 10
    min_history: int = 180
    min_drawdown_from_window_high: float = 0.25
    max_position_in_bottom_range: float = 0.45
    min_rebound_from_recent_low: float = 0.05
    max_rebound_from_recent_low: float = 0.35
    min_ret_3d: float = 0.03
    min_ret_10d: float = 0.05
    ma_window: int = 20
    ma_slope_lag: int = 5
    min_ma_slope: float = -0.01
    ma_reclaim_tolerance: float = 0.01
    min_vol_ratio_3d: float = 1.15
    max_vol_ratio_1d: float = 6.0
    max_abs_ret_1d: float = 0.115
    min_amount: float = 0.0
    min_candidate_score: int = 7
    top_n_per_symbol: int = 5
    max_candidates_total: int = 8000
    require_drawdown: bool = True
    require_rebound: bool = True
    require_not_overextended: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "BottomReboundConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class BottomReboundMiner(BaseMiner):
    name = "bottom_rebound"

    def __init__(self, config: BottomReboundConfig):
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
            self.config.bottom_window + 1,
            self.config.rebound_window + 1,
            self.config.ma_window + self.config.ma_slope_lag + 1,
        )
        if len(out) < min_required:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        close = pd.to_numeric(out["close"], errors="coerce")
        high = pd.to_numeric(out["high"], errors="coerce") if "high" in out.columns else close
        low = pd.to_numeric(out["low"], errors="coerce") if "low" in out.columns else close

        window_high = high.rolling(self.config.bottom_window).max().shift(1)
        window_low = low.rolling(self.config.bottom_window).min().shift(1)
        bottom_range = window_high - window_low
        bottom_range = bottom_range.where(bottom_range > 0)
        position_in_range = (close - window_low) / bottom_range
        drawdown_from_window_high = 1.0 - close / window_high

        recent_low = low.rolling(self.config.rebound_window).min().shift(1)
        rebound_from_recent_low = close / recent_low - 1.0
        ret_1d = close.pct_change(1)
        ret_3d = close.pct_change(3)
        ret_10d = close.pct_change(self.config.rebound_window)

        ma = close.rolling(self.config.ma_window).mean()
        ma_slope = ma / ma.shift(self.config.ma_slope_lag) - 1.0
        ma_reclaim = close >= ma * (1.0 - self.config.ma_reclaim_tolerance)

        if "vol" in out.columns:
            vol = pd.to_numeric(out["vol"], errors="coerce")
            vol_base = vol.rolling(self.config.bottom_window).mean().shift(1)
            vol_ratio_1d = vol / vol_base
            vol_ratio_3d = vol.rolling(3).mean() / vol_base
        else:
            vol_ratio_1d = pd.Series([pd.NA] * len(out), index=out.index, dtype="object")
            vol_ratio_3d = pd.Series([pd.NA] * len(out), index=out.index, dtype="object")

        if "amount" in out.columns:
            amount = pd.to_numeric(out["amount"], errors="coerce")
            amount_ok = amount >= float(self.config.min_amount)
        else:
            amount_ok = pd.Series([self.config.min_amount <= 0] * len(out), index=out.index)

        drawdown_ok = drawdown_from_window_high >= self.config.min_drawdown_from_window_high
        low_position_ok = position_in_range <= self.config.max_position_in_bottom_range
        rebound_ok = rebound_from_recent_low >= self.config.min_rebound_from_recent_low
        not_overextended = rebound_from_recent_low <= self.config.max_rebound_from_recent_low
        ret_3d_ok = ret_3d >= self.config.min_ret_3d
        ret_10d_ok = ret_10d >= self.config.min_ret_10d
        ma_slope_ok = ma_slope >= self.config.min_ma_slope
        vol_3d_ok = pd.to_numeric(vol_ratio_3d, errors="coerce").fillna(0.0) >= self.config.min_vol_ratio_3d
        vol_not_extreme = pd.to_numeric(vol_ratio_1d, errors="coerce").fillna(0.0) <= self.config.max_vol_ratio_1d
        ret_not_extreme = ret_1d.abs() <= self.config.max_abs_ret_1d

        score = (
            drawdown_ok.astype(int) * 2
            + low_position_ok.astype(int)
            + rebound_ok.astype(int) * 2
            + not_overextended.astype(int)
            + ret_3d_ok.astype(int)
            + ret_10d_ok.astype(int)
            + ma_reclaim.astype(int)
            + ma_slope_ok.astype(int)
            + vol_3d_ok.astype(int)
            + vol_not_extreme.astype(int)
            + ret_not_extreme.astype(int)
            + amount_ok.astype(int)
        )

        candidate_mask = score >= int(self.config.min_candidate_score)
        if self.config.require_drawdown:
            candidate_mask &= drawdown_ok & low_position_ok
        if self.config.require_rebound:
            candidate_mask &= rebound_ok & (ret_3d_ok | ret_10d_ok)
        if self.config.require_not_overextended:
            candidate_mask &= not_overextended & ret_not_extreme & vol_not_extreme

        hit_df = pd.DataFrame(
            {
                "sample_id": "",
                "ts_code": ts_code,
                "asof_date": out["trade_date"],
                "label": pd.NA,
                "label_source": f"{self.name}_candidate",
                "confidence": 1.0,
                "event_id": "",
                "miner_name": self.name,
                "candidate_score": score,
                "close": close,
                "ret_1d": ret_1d,
                "ret_3d": ret_3d,
                "vol_ratio_1d": vol_ratio_1d,
                "vol_ratio_3d": vol_ratio_3d,
                "base_window_days": int(self.config.bottom_window),
                "base_range_pct": (window_high - window_low) / window_low,
                "breakout_flag": ma_reclaim.fillna(False),
                "rule_flags": "",
            }
        )
        hit_df = hit_df[candidate_mask].copy()
        if hit_df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        def _flags(idx: int) -> str:
            flags: list[str] = []
            if bool(drawdown_ok.loc[idx]):
                flags.append("drawdown_ok")
            if bool(low_position_ok.loc[idx]):
                flags.append("low_position_ok")
            if bool(rebound_ok.loc[idx]):
                flags.append("rebound_ok")
            if bool(not_overextended.loc[idx]):
                flags.append("not_overextended")
            if bool(ret_3d_ok.loc[idx]):
                flags.append("ret_3d_ok")
            if bool(ret_10d_ok.loc[idx]):
                flags.append("ret_10d_ok")
            if bool(ma_reclaim.loc[idx]):
                flags.append("ma_reclaim")
            if bool(ma_slope_ok.loc[idx]):
                flags.append("ma_slope_ok")
            if bool(vol_3d_ok.loc[idx]):
                flags.append("vol_3d_ok")
            if bool(amount_ok.loc[idx]):
                flags.append("amount_ok")
            flags.append(f"drawdown={drawdown_from_window_high.loc[idx]:.3f}")
            flags.append(f"rebound={rebound_from_recent_low.loc[idx]:.3f}")
            flags.append(f"position={position_in_range.loc[idx]:.3f}")
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


__all__ = ["BottomReboundConfig", "BottomReboundMiner"]
