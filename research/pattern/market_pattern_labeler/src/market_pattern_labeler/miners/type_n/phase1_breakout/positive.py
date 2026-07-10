from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.miners.type_n.phase1_breakout.rules.runup import RunupRule, RunupRuleConfig
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


@dataclass
class TypeNConfig:
    lookback_window: int = 60
    min_history: int = 80
    max_base_range_pct: float = 0.25
    min_ret_1d: float = 0.02
    min_ret_3d: float = 0.05
    min_vol_ratio_1d: float = 1.5
    min_vol_ratio_3d: float = 1.3
    breakout_tolerance: float = 0.01
    min_candidate_score: int = 4
    top_n_per_symbol: int = 10
    require_base_condition: bool = True
    enable_runup_rule: bool = False
    runup_window: int = 150
    max_runup_pct: float = 0.6
    runup_score_weight: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "TypeNConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class TypeNMiner(BaseMiner):
    name = "type_n"

    def __init__(self, config: TypeNConfig):
        self.config = config

    def scan_one(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        out = df.copy()
        if "trade_date" not in out.columns or "close" not in out.columns:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        out["trade_date"] = to_trade_datetime(out["trade_date"])
        out = out.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
        if len(out) < max(self.config.min_history, self.config.lookback_window + 3):
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        close = pd.to_numeric(out["close"], errors="coerce")
        base_high_prev = close.rolling(self.config.lookback_window).max().shift(1)
        base_low_prev = close.rolling(self.config.lookback_window).min().shift(1)
        base_range_pct = (base_high_prev - base_low_prev) / base_low_prev
        runup_rule = RunupRule(
            RunupRuleConfig(
                window=int(self.config.runup_window),
                max_runup_pct=float(self.config.max_runup_pct),
                score_weight=int(self.config.runup_score_weight),
            )
        )
        runup_result = runup_rule.evaluate(close)

        ret_1d = close.pct_change(1)
        ret_3d = close.pct_change(3)

        if "vol" in out.columns:
            vol = pd.to_numeric(out["vol"], errors="coerce")
            vol_base = vol.rolling(self.config.lookback_window).mean().shift(1)
            vol_ratio_1d = vol / vol_base
            vol_ratio_3d = vol.rolling(3).mean() / vol_base
            vol_ok_1d = vol_ratio_1d >= self.config.min_vol_ratio_1d
            vol_ok_3d = vol_ratio_3d >= self.config.min_vol_ratio_3d
        else:
            vol_ratio_1d = pd.Series([pd.NA] * len(out), index=out.index, dtype="object")
            vol_ratio_3d = pd.Series([pd.NA] * len(out), index=out.index, dtype="object")
            vol_ok_1d = pd.Series([False] * len(out), index=out.index)
            vol_ok_3d = pd.Series([False] * len(out), index=out.index)

        base_ok = base_range_pct <= self.config.max_base_range_pct
        ret_ok_1d = ret_1d >= self.config.min_ret_1d
        ret_ok_3d = ret_3d >= self.config.min_ret_3d
        breakout_flag = close >= base_high_prev * (1 - self.config.breakout_tolerance)

        score = (
            base_ok.astype(int) * 2
            + ret_ok_1d.astype(int)
            + ret_ok_3d.astype(int)
            + vol_ok_1d.astype(int)
            + vol_ok_3d.astype(int)
            + breakout_flag.astype(int)
        )
        if self.config.enable_runup_rule and int(self.config.runup_score_weight) > 0:
            score = score + runup_result.score_bonus

        candidate_mask = score >= int(self.config.min_candidate_score)
        if self.config.require_base_condition:
            candidate_mask &= base_ok
        if self.config.enable_runup_rule:
            candidate_mask &= runup_result.ok.fillna(False)

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
                "base_window_days": int(self.config.lookback_window),
                "base_range_pct": base_range_pct,
                "breakout_flag": breakout_flag.fillna(False),
                "rule_flags": "",
            }
        )
        hit_df = hit_df[candidate_mask].copy()
        if hit_df.empty:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        def _build_flags(row: pd.Series) -> str:
            flags: list[str] = []
            if bool(base_ok.loc[row.name]):
                flags.append("base_ok")
            if bool(ret_ok_1d.loc[row.name]):
                flags.append("ret_1d_ok")
            if bool(ret_ok_3d.loc[row.name]):
                flags.append("ret_3d_ok")
            if bool(vol_ok_1d.loc[row.name]):
                flags.append("vol_1d_ok")
            if bool(vol_ok_3d.loc[row.name]):
                flags.append("vol_3d_ok")
            if bool(breakout_flag.loc[row.name]):
                flags.append("breakout_ok")
            if self.config.enable_runup_rule and bool(runup_result.ok.loc[row.name]):
                flags.append(runup_rule.flag_name)
            return ";".join(flags)

        hit_df["rule_flags"] = hit_df.apply(_build_flags, axis=1)
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


__all__ = ["TypeNConfig", "TypeNMiner"]
