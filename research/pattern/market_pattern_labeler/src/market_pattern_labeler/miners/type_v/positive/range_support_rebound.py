from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


@dataclass
class RangeSupportReboundConfig:
    total_window: int = 150
    range_window: int = 90
    recent_touch_window: int = 15
    min_history: int = 180
    max_range_pct: float = 0.30
    max_abs_ret_60d: float = 0.15
    support_tolerance: float = 0.04
    min_support_touches: int = 2
    max_position_in_range: float = 0.55
    breakdown_tolerance: float = 0.03
    min_rebound_from_recent_low: float = 0.03
    max_rebound_from_recent_low: float = 0.18
    min_ret_3d: float = 0.015
    min_ret_10d: float = 0.03
    max_abs_ret_1d: float = 0.08
    min_vol_ratio_3d: float = 1.05
    max_vol_ratio_1d: float = 4.0
    min_candidate_score: int = 8
    top_n_per_symbol: int = 5
    max_candidates_total: int = 8000

    @classmethod
    def from_dict(cls, data: dict) -> "RangeSupportReboundConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class RangeSupportReboundMiner(BaseMiner):
    name = "range_support_rebound"

    def __init__(self, config: RangeSupportReboundConfig):
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
            self.config.total_window + 1,
            self.config.range_window + self.config.recent_touch_window + 1,
        )
        if len(out) < min_required:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        close = pd.to_numeric(out["close"], errors="coerce")
        high = pd.to_numeric(out["high"], errors="coerce") if "high" in out.columns else close
        low = pd.to_numeric(out["low"], errors="coerce") if "low" in out.columns else close

        range_high = high.rolling(self.config.range_window).max().shift(1)
        range_low = low.rolling(self.config.range_window).min().shift(1)
        range_width = (range_high - range_low).where((range_high - range_low) > 0)
        range_pct = range_width / range_low
        position_in_range = (close - range_low) / range_width

        total_high = high.rolling(self.config.total_window).max().shift(1)
        total_low = low.rolling(self.config.total_window).min().shift(1)
        total_range_pct = (total_high - total_low) / total_low

        support_zone_top = range_low * (1.0 + self.config.support_tolerance)
        prior_support_touches = (low <= support_zone_top).rolling(self.config.range_window).sum().shift(1)
        recent_low = low.rolling(self.config.recent_touch_window).min().shift(1)
        rebound_from_recent_low = close / recent_low - 1.0

        ret_1d = close.pct_change(1)
        ret_3d = close.pct_change(3)
        ret_10d = close.pct_change(10)
        ret_60d = close.pct_change(60)

        if "vol" in out.columns:
            vol = pd.to_numeric(out["vol"], errors="coerce")
            vol_base = vol.rolling(self.config.range_window).mean().shift(1)
            vol_ratio_1d = vol / vol_base
            vol_ratio_3d = vol.rolling(3).mean() / vol_base
        else:
            vol_ratio_1d = pd.Series([pd.NA] * len(out), index=out.index, dtype="object")
            vol_ratio_3d = pd.Series([pd.NA] * len(out), index=out.index, dtype="object")

        range_sideways = range_pct <= self.config.max_range_pct
        trend_not_strong = ret_60d.abs() <= self.config.max_abs_ret_60d
        support_touches_ok = prior_support_touches >= self.config.min_support_touches
        recent_support_touch = recent_low <= support_zone_top
        support_not_broken = close >= range_low * (1.0 - self.config.breakdown_tolerance)
        still_near_lower_range = position_in_range <= self.config.max_position_in_range
        rebound_ok = rebound_from_recent_low >= self.config.min_rebound_from_recent_low
        not_overextended = rebound_from_recent_low <= self.config.max_rebound_from_recent_low
        ret_3d_ok = ret_3d >= self.config.min_ret_3d
        ret_10d_ok = ret_10d >= self.config.min_ret_10d
        ret_not_extreme = ret_1d.abs() <= self.config.max_abs_ret_1d
        vol_3d_ok = pd.to_numeric(vol_ratio_3d, errors="coerce").fillna(0.0) >= self.config.min_vol_ratio_3d
        vol_not_extreme = pd.to_numeric(vol_ratio_1d, errors="coerce").fillna(0.0) <= self.config.max_vol_ratio_1d

        score = (
            range_sideways.astype(int) * 2
            + trend_not_strong.astype(int)
            + support_touches_ok.astype(int) * 2
            + recent_support_touch.astype(int) * 2
            + support_not_broken.astype(int)
            + still_near_lower_range.astype(int)
            + rebound_ok.astype(int) * 2
            + not_overextended.astype(int)
            + ret_3d_ok.astype(int)
            + ret_10d_ok.astype(int)
            + ret_not_extreme.astype(int)
            + vol_3d_ok.astype(int)
            + vol_not_extreme.astype(int)
        )

        candidate_mask = (
            (score >= int(self.config.min_candidate_score))
            & range_sideways
            & support_touches_ok
            & recent_support_touch
            & support_not_broken
            & still_near_lower_range
            & rebound_ok
            & not_overextended
            & ret_not_extreme
            & vol_not_extreme
            & (ret_3d_ok | ret_10d_ok)
        )

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
                "base_window_days": int(self.config.range_window),
                "base_range_pct": range_pct,
                "breakout_flag": False,
                "rule_flags": "",
            }
        )
        hit_df = hit_df[candidate_mask].copy()
        if hit_df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        def _flags(idx: int) -> str:
            flags: list[str] = []
            if bool(range_sideways.loc[idx]):
                flags.append("range_sideways")
            if bool(trend_not_strong.loc[idx]):
                flags.append("trend_not_strong")
            if bool(support_touches_ok.loc[idx]):
                flags.append("support_touches_ok")
            if bool(recent_support_touch.loc[idx]):
                flags.append("recent_support_touch")
            if bool(support_not_broken.loc[idx]):
                flags.append("support_not_broken")
            if bool(still_near_lower_range.loc[idx]):
                flags.append("near_lower_range")
            if bool(rebound_ok.loc[idx]):
                flags.append("rebound_ok")
            if bool(not_overextended.loc[idx]):
                flags.append("not_overextended")
            if bool(ret_3d_ok.loc[idx]):
                flags.append("ret_3d_ok")
            if bool(ret_10d_ok.loc[idx]):
                flags.append("ret_10d_ok")
            if bool(vol_3d_ok.loc[idx]):
                flags.append("vol_3d_ok")
            flags.append(f"support_touches={prior_support_touches.loc[idx]:.0f}")
            flags.append(f"position={position_in_range.loc[idx]:.3f}")
            flags.append(f"rebound={rebound_from_recent_low.loc[idx]:.3f}")
            flags.append(f"range_pct={range_pct.loc[idx]:.3f}")
            flags.append(f"total_range_pct={total_range_pct.loc[idx]:.3f}")
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


__all__ = ["RangeSupportReboundConfig", "RangeSupportReboundMiner"]
