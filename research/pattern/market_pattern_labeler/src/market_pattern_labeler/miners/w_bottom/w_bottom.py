from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


W_BOTTOM_COLUMNS = CANDIDATE_COLUMNS + [
    "window",
    "pattern_stage",
    "left_bottom_date",
    "left_bottom_price",
    "middle_peak_date",
    "neckline_price",
    "right_bottom_date",
    "right_bottom_price",
    "current_close",
    "prior_high_date",
    "prior_high_price",
    "bottom_similarity_pct",
    "middle_rebound_pct",
    "prior_drawdown_pct",
    "neckline_distance_pct",
    "volume_ratio_20",
]


@dataclass
class WBottomLabelConfig:
    label: int = 1
    label_source: str = "rule_w_bottom"
    confidence: float = 0.6

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WBottomLabelConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class WBottomWindowConfig:
    name: str
    lookback: int


@dataclass
class WBottomRulesConfig:
    min_prior_drawdown_pct: float = 0.20
    min_middle_rebound_pct: float = 0.08
    max_bottom_price_diff_pct: float = 0.12
    max_right_bottom_break_pct: float = 0.10
    min_bottom_separation_days: int = 20
    max_bottom_separation_days: int = 300
    min_days_after_right_bottom: int = 5
    forming_neckline_distance_pct: float = 0.08
    breakout_neckline_buffer_pct: float = 0.00
    extrema_order: int = 5

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WBottomRulesConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class WBottomVolumeConfig:
    enable: bool = True
    ma_window: int = 20
    breakout_volume_ratio: float = 1.20

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WBottomVolumeConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class WBottomScoringConfig:
    weight_prior_drawdown: float = 0.20
    weight_bottom_similarity: float = 0.25
    weight_middle_rebound: float = 0.20
    weight_neckline_distance: float = 0.25
    weight_volume: float = 0.10

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WBottomScoringConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class WBottomOutputConfig:
    max_candidates_per_symbol: int = 20

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WBottomOutputConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class WBottomConfig:
    label: WBottomLabelConfig = field(default_factory=WBottomLabelConfig)
    windows: list[WBottomWindowConfig] = field(
        default_factory=lambda: [
            WBottomWindowConfig(name="short", lookback=120),
            WBottomWindowConfig(name="medium", lookback=252),
            WBottomWindowConfig(name="long", lookback=504),
        ]
    )
    rules: WBottomRulesConfig = field(default_factory=WBottomRulesConfig)
    volume: WBottomVolumeConfig = field(default_factory=WBottomVolumeConfig)
    scoring: WBottomScoringConfig = field(default_factory=WBottomScoringConfig)
    output: WBottomOutputConfig = field(default_factory=WBottomOutputConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WBottomConfig":
        windows_data = data.get("windows")
        if isinstance(windows_data, list):
            windows = [
                WBottomWindowConfig(
                    name=str(item.get("name", f"window_{idx}")),
                    lookback=int(item.get("lookback", 0)),
                )
                for idx, item in enumerate(windows_data)
                if isinstance(item, dict) and int(item.get("lookback", 0)) > 0
            ]
        else:
            windows = cls().windows

        return cls(
            label=WBottomLabelConfig.from_dict(_as_dict(data.get("label"))),
            windows=windows or cls().windows,
            rules=WBottomRulesConfig.from_dict(_as_dict(data.get("rules"))),
            volume=WBottomVolumeConfig.from_dict(_as_dict(data.get("volume"))),
            scoring=WBottomScoringConfig.from_dict(_as_dict(data.get("scoring"))),
            output=WBottomOutputConfig.from_dict(_as_dict(data.get("output"))),
        )


class WBottomMiner(BaseMiner):
    name = "w_bottom"
    output_columns = W_BOTTOM_COLUMNS

    def __init__(self, config: WBottomConfig):
        self.config = config

    def scan_one(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        out = self._prepare_daily(df)
        if out.empty:
            return pd.DataFrame(columns=self.output_columns)

        rows: list[dict[str, Any]] = []
        for window in self.config.windows:
            if len(out) < int(window.lookback):
                continue
            rows.extend(self._scan_window(ts_code, out.tail(int(window.lookback)).reset_index(drop=True), window))

        if not rows:
            return pd.DataFrame(columns=self.output_columns)

        hit_df = pd.DataFrame(rows)
        hit_df = hit_df.sort_values(["candidate_score", "asof_date"], ascending=[False, False])
        hit_df = hit_df.drop_duplicates(["ts_code", "window", "pattern_stage"], keep="first")
        hit_df = hit_df.sort_values(["candidate_score", "asof_date"], ascending=[False, False])
        max_per_symbol = int(self.config.output.max_candidates_per_symbol)
        if max_per_symbol > 0:
            hit_df = hit_df.head(max_per_symbol)

        for col in self.output_columns:
            if col not in hit_df.columns:
                hit_df[col] = pd.NA
        return hit_df[self.output_columns].reset_index(drop=True)

    def _prepare_daily(self, df: pd.DataFrame | None) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        required = {"trade_date", "open", "high", "low", "close"}
        if not required.issubset(df.columns):
            return pd.DataFrame()

        out = df.copy()
        out["trade_date"] = to_trade_datetime(out["trade_date"])
        for col in ["open", "high", "low", "close", "vol", "volume"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        if "vol" not in out.columns and "volume" in out.columns:
            out["vol"] = out["volume"]
        if "vol" not in out.columns:
            out["vol"] = 0.0

        out = out.dropna(subset=["trade_date", "open", "high", "low", "close"])
        out = out[out["close"] > 0]
        return out.sort_values("trade_date").reset_index(drop=True)

    def _scan_window(
        self,
        ts_code: str,
        window_df: pd.DataFrame,
        window: WBottomWindowConfig,
    ) -> list[dict[str, Any]]:
        close = pd.to_numeric(window_df["close"], errors="coerce").reset_index(drop=True)
        current_idx = len(window_df) - 1
        current_close = float(close.iloc[current_idx])
        if current_idx <= 0 or current_close <= 0:
            return []

        rules = self.config.rules
        lows = find_local_lows(close, order=int(rules.extrema_order))
        if not lows:
            return []
        highs = find_local_highs(close, order=int(rules.extrema_order))

        rows: list[dict[str, Any]] = []
        latest_right_bottom_idx = current_idx - int(rules.min_days_after_right_bottom)
        for l1_idx in lows:
            if l1_idx <= 0:
                continue
            l1_price = float(close.iloc[l1_idx])
            if l1_price <= 0:
                continue

            prior_slice = close.iloc[:l1_idx]
            if prior_slice.empty:
                continue
            h_idx = int(prior_slice.idxmax())
            h_price = float(close.iloc[h_idx])
            if h_price <= 0:
                continue

            prior_drawdown_pct = (h_price - l1_price) / h_price
            if prior_drawdown_pct < float(rules.min_prior_drawdown_pct):
                continue

            for l2_idx in lows:
                if l2_idx <= l1_idx or l2_idx > latest_right_bottom_idx:
                    continue
                separation = l2_idx - l1_idx
                if separation < int(rules.min_bottom_separation_days):
                    continue
                if separation > int(rules.max_bottom_separation_days):
                    continue

                l2_price = float(close.iloc[l2_idx])
                if l2_price <= 0:
                    continue
                bottom_similarity_pct = abs(l2_price / l1_price - 1.0)
                if bottom_similarity_pct > float(rules.max_bottom_price_diff_pct):
                    continue
                if l2_price < l1_price * (1.0 - float(rules.max_right_bottom_break_pct)):
                    continue

                middle = close.iloc[l1_idx + 1 : l2_idx]
                if middle.empty:
                    continue
                m_idx = _middle_peak_index(close, l1_idx, l2_idx, highs)
                m_price = float(close.iloc[m_idx])
                if m_price <= 0:
                    continue

                middle_rebound_pct = (m_price - l1_price) / l1_price
                if middle_rebound_pct < float(rules.min_middle_rebound_pct):
                    continue

                neckline_distance_pct = (m_price - current_close) / m_price
                breakout_flag = current_close >= m_price * (1.0 + float(rules.breakout_neckline_buffer_pct))
                if breakout_flag:
                    pattern_stage = "w_bottom_breakout"
                elif current_close >= m_price * (1.0 - float(rules.forming_neckline_distance_pct)):
                    pattern_stage = "w_bottom_forming"
                else:
                    continue

                volume_ratio_20 = self._volume_ratio(window_df)
                candidate_score = self._score(
                    prior_drawdown_pct=prior_drawdown_pct,
                    bottom_similarity_pct=bottom_similarity_pct,
                    middle_rebound_pct=middle_rebound_pct,
                    neckline_distance_pct=neckline_distance_pct,
                    breakout_flag=breakout_flag,
                    volume_ratio_20=volume_ratio_20,
                )

                asof_date = _date_str(window_df.loc[current_idx, "trade_date"])
                sample_id = f"{ts_code}_{asof_date}_{self.name}_{window.name}_{pattern_stage}"
                rows.append(
                    {
                        "sample_id": sample_id,
                        "ts_code": ts_code,
                        "asof_date": asof_date,
                        "label": int(self.config.label.label),
                        "label_source": self.config.label.label_source,
                        "confidence": float(self.config.label.confidence),
                        "event_id": sample_id,
                        "miner_name": self.name,
                        "candidate_score": candidate_score,
                        "close": current_close,
                        "ret_1d": _pct_change(close, current_idx, 1),
                        "ret_3d": _pct_change(close, current_idx, 3),
                        "vol_ratio_1d": volume_ratio_20,
                        "vol_ratio_3d": pd.NA,
                        "base_window_days": int(window.lookback),
                        "base_range_pct": (h_price - min(l1_price, l2_price)) / min(l1_price, l2_price),
                        "breakout_flag": bool(breakout_flag),
                        "rule_flags": _rule_flags(
                            pattern_stage=pattern_stage,
                            prior_drawdown_pct=prior_drawdown_pct,
                            bottom_similarity_pct=bottom_similarity_pct,
                            middle_rebound_pct=middle_rebound_pct,
                            neckline_distance_pct=neckline_distance_pct,
                            volume_ratio_20=volume_ratio_20,
                            volume_ok=self._volume_ok(breakout_flag, volume_ratio_20),
                        ),
                        "window": window.name,
                        "pattern_stage": pattern_stage,
                        "left_bottom_date": _date_str(window_df.loc[l1_idx, "trade_date"]),
                        "left_bottom_price": l1_price,
                        "middle_peak_date": _date_str(window_df.loc[m_idx, "trade_date"]),
                        "neckline_price": m_price,
                        "right_bottom_date": _date_str(window_df.loc[l2_idx, "trade_date"]),
                        "right_bottom_price": l2_price,
                        "current_close": current_close,
                        "prior_high_date": _date_str(window_df.loc[h_idx, "trade_date"]),
                        "prior_high_price": h_price,
                        "bottom_similarity_pct": bottom_similarity_pct,
                        "middle_rebound_pct": middle_rebound_pct,
                        "prior_drawdown_pct": prior_drawdown_pct,
                        "neckline_distance_pct": neckline_distance_pct,
                        "volume_ratio_20": volume_ratio_20,
                    }
                )
        return rows

    def _volume_ratio(self, window_df: pd.DataFrame) -> float:
        if not self.config.volume.enable or "vol" not in window_df.columns:
            return 0.0
        vol = pd.to_numeric(window_df["vol"], errors="coerce").fillna(0.0)
        ma_window = int(self.config.volume.ma_window)
        if len(vol) < ma_window or ma_window <= 0:
            return 0.0
        volume_ma = float(vol.rolling(ma_window).mean().iloc[-1])
        current_vol = float(vol.iloc[-1])
        if volume_ma <= 0:
            return 0.0
        return current_vol / volume_ma

    def _volume_ok(self, breakout_flag: bool, volume_ratio_20: float) -> bool:
        if not self.config.volume.enable:
            return False
        return bool(breakout_flag and volume_ratio_20 >= float(self.config.volume.breakout_volume_ratio))

    def _score(
        self,
        *,
        prior_drawdown_pct: float,
        bottom_similarity_pct: float,
        middle_rebound_pct: float,
        neckline_distance_pct: float,
        breakout_flag: bool,
        volume_ratio_20: float,
    ) -> float:
        rules = self.config.rules
        scoring = self.config.scoring
        prior_score = _clamp(prior_drawdown_pct / max(float(rules.min_prior_drawdown_pct) * 2.0, 1e-9))
        bottom_score = _clamp(1.0 - bottom_similarity_pct / max(float(rules.max_bottom_price_diff_pct), 1e-9))
        rebound_score = _clamp(middle_rebound_pct / max(float(rules.min_middle_rebound_pct) * 2.0, 1e-9))
        if breakout_flag:
            neckline_score = 1.0
        else:
            neckline_score = _clamp(
                1.0 - max(neckline_distance_pct, 0.0) / max(float(rules.forming_neckline_distance_pct), 1e-9)
            )
        volume_score = 1.0 if self._volume_ok(breakout_flag, volume_ratio_20) else 0.0

        weights = {
            "prior": float(scoring.weight_prior_drawdown),
            "bottom": float(scoring.weight_bottom_similarity),
            "rebound": float(scoring.weight_middle_rebound),
            "neckline": float(scoring.weight_neckline_distance),
            "volume": float(scoring.weight_volume) if self.config.volume.enable else 0.0,
        }
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return 0.0
        score = (
            prior_score * weights["prior"]
            + bottom_score * weights["bottom"]
            + rebound_score * weights["rebound"]
            + neckline_score * weights["neckline"]
            + volume_score * weights["volume"]
        ) / total_weight
        return round(_clamp(score), 6)


def find_local_lows(close: pd.Series, order: int = 5) -> list[int]:
    values = pd.to_numeric(close, errors="coerce").reset_index(drop=True)
    effective_order = _effective_order(len(values), order)
    lows: list[int] = []
    for idx in range(effective_order, len(values) - effective_order):
        current = values.iloc[idx]
        if pd.isna(current):
            continue
        window = values.iloc[idx - effective_order : idx + effective_order + 1].dropna()
        if not window.empty and current == window.min():
            lows.append(idx)
    return lows


def find_local_highs(close: pd.Series, order: int = 5) -> list[int]:
    values = pd.to_numeric(close, errors="coerce").reset_index(drop=True)
    effective_order = _effective_order(len(values), order)
    highs: list[int] = []
    for idx in range(effective_order, len(values) - effective_order):
        current = values.iloc[idx]
        if pd.isna(current):
            continue
        window = values.iloc[idx - effective_order : idx + effective_order + 1].dropna()
        if not window.empty and current == window.max():
            highs.append(idx)
    return highs


def _middle_peak_index(close: pd.Series, l1_idx: int, l2_idx: int, highs: list[int]) -> int:
    middle_highs = [idx for idx in highs if l1_idx < idx < l2_idx]
    if middle_highs:
        return max(middle_highs, key=lambda idx: float(close.iloc[idx]))
    return int(close.iloc[l1_idx + 1 : l2_idx].idxmax())


def _effective_order(length: int, order: int) -> int:
    if length < 3:
        return 1
    return max(1, min(int(order), (length - 1) // 2))


def _rule_flags(
    *,
    pattern_stage: str,
    prior_drawdown_pct: float,
    bottom_similarity_pct: float,
    middle_rebound_pct: float,
    neckline_distance_pct: float,
    volume_ratio_20: float,
    volume_ok: bool,
) -> str:
    flags = [
        "prior_drawdown_ok",
        "bottom_similarity_ok",
        "middle_rebound_ok",
        "neckline_ok",
        pattern_stage,
        f"prior_drawdown={prior_drawdown_pct:.3f}",
        f"bottom_similarity={bottom_similarity_pct:.3f}",
        f"middle_rebound={middle_rebound_pct:.3f}",
        f"neckline_distance={neckline_distance_pct:.3f}",
        f"volume_ratio_20={volume_ratio_20:.3f}",
    ]
    if volume_ok:
        flags.append("volume_breakout_ok")
    return ";".join(flags)


def _pct_change(close: pd.Series, idx: int, periods: int) -> float:
    prev_idx = idx - periods
    if prev_idx < 0:
        return float("nan")
    prev = float(close.iloc[prev_idx])
    if prev <= 0:
        return float("nan")
    return float(close.iloc[idx]) / prev - 1.0


def _date_str(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


__all__ = [
    "WBottomConfig",
    "WBottomMiner",
    "W_BOTTOM_COLUMNS",
    "find_local_highs",
    "find_local_lows",
]
