from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


BOTTOM_BASE_BREAKOUT_COLUMNS = CANDIDATE_COLUMNS + [
    "window",
    "pattern_stage",
    "prior_high_date",
    "prior_high_price",
    "base_low_date",
    "base_low_price",
    "base_high_price",
    "base_close_std_pct",
    "neckline_date",
    "neckline_price",
    "current_close",
    "breakout_date",
    "breakout_distance_pct",
    "breakout_recency_bars",
    "prior_drawdown_pct",
    "neckline_rebound_from_base_low_pct",
    "touches_in_base_zone",
    "volume_ratio_20",
    "left_bottom_date",
    "left_bottom_price",
    "middle_peak_date",
    "middle_peak_price",
    "right_bottom_date",
    "right_bottom_price",
]


@dataclass
class BottomBaseLabelConfig:
    label: int = 1
    label_source: str = "rule_bottom_base_breakout"
    confidence: float = 0.65

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BottomBaseLabelConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class BottomBaseScanConfig:
    mode: str = "historical"
    asof_stride: int = 5
    min_asof_date: str | None = "2016-01-01"
    max_asof_date: str | None = None
    max_candidates_per_symbol: int = 50
    min_days_between_candidates: int = 20

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BottomBaseScanConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class BottomBaseWindowConfig:
    name: str
    lookback: int


@dataclass
class BottomBaseRulesConfig:
    min_prior_drawdown_pct: float = 0.18
    min_base_duration_bars: int = 40
    max_base_range_pct: float = 0.50
    max_base_close_std_pct: float = 0.22
    min_neckline_rebound_from_base_low_pct: float = 0.08
    min_touches_in_base_zone: int = 2
    base_zone_pct: float = 0.12
    min_breakout_distance_pct: float = 0.00
    max_breakout_distance_pct: float = 0.08
    max_breakout_recency_bars: int = 15
    min_right_recovery_pct: float = 0.10
    min_close_vs_base_low_pct: float = 0.12

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BottomBaseRulesConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class BottomBaseVolumeConfig:
    enable: bool = True
    ma_window: int = 20
    breakout_volume_ratio: float = 1.10
    volume_as_bonus_only: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BottomBaseVolumeConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class BottomBaseScoringConfig:
    weight_prior_drawdown: float = 0.15
    weight_base_stability: float = 0.25
    weight_neckline_rebound: float = 0.15
    weight_breakout_freshness: float = 0.20
    weight_breakout_distance: float = 0.15
    weight_volume: float = 0.10

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BottomBaseScoringConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class BottomBaseOutputConfig:
    max_candidates_per_symbol: int = 50

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BottomBaseOutputConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class BottomBaseBreakoutConfig:
    label: BottomBaseLabelConfig = field(default_factory=BottomBaseLabelConfig)
    scan: BottomBaseScanConfig = field(default_factory=BottomBaseScanConfig)
    windows: list[BottomBaseWindowConfig] = field(
        default_factory=lambda: [
            BottomBaseWindowConfig(name="short", lookback=120),
            BottomBaseWindowConfig(name="medium", lookback=252),
            BottomBaseWindowConfig(name="long", lookback=504),
            BottomBaseWindowConfig(name="extra_long", lookback=756),
        ]
    )
    rules: BottomBaseRulesConfig = field(default_factory=BottomBaseRulesConfig)
    volume: BottomBaseVolumeConfig = field(default_factory=BottomBaseVolumeConfig)
    scoring: BottomBaseScoringConfig = field(default_factory=BottomBaseScoringConfig)
    output: BottomBaseOutputConfig = field(default_factory=BottomBaseOutputConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BottomBaseBreakoutConfig":
        windows_data = data.get("windows")
        if isinstance(windows_data, list):
            windows = [
                BottomBaseWindowConfig(
                    name=str(item.get("name", f"window_{idx}")),
                    lookback=int(item.get("lookback", 0)),
                )
                for idx, item in enumerate(windows_data)
                if isinstance(item, dict) and int(item.get("lookback", 0)) > 0
            ]
        else:
            windows = cls().windows
        return cls(
            label=BottomBaseLabelConfig.from_dict(_as_dict(data.get("label"))),
            scan=BottomBaseScanConfig.from_dict(_as_dict(data.get("scan"))),
            windows=windows or cls().windows,
            rules=BottomBaseRulesConfig.from_dict(_as_dict(data.get("rules"))),
            volume=BottomBaseVolumeConfig.from_dict(_as_dict(data.get("volume"))),
            scoring=BottomBaseScoringConfig.from_dict(_as_dict(data.get("scoring"))),
            output=BottomBaseOutputConfig.from_dict(_as_dict(data.get("output"))),
        )


class BottomBaseBreakoutMiner(BaseMiner):
    name = "bottom_base_breakout"
    output_columns = BOTTOM_BASE_BREAKOUT_COLUMNS

    def __init__(self, config: BottomBaseBreakoutConfig):
        self.config = config

    def scan_one(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        out = self._prepare_daily(df)
        if out.empty:
            return pd.DataFrame(columns=self.output_columns)

        rows: list[dict[str, Any]] = []
        max_lookback = max(int(window.lookback) for window in self.config.windows)
        asof_indices = self._asof_indices(out, max_lookback)
        close = pd.to_numeric(out["close"], errors="coerce")
        for window in self.config.windows:
            lookback = int(window.lookback)
            rules = self.config.rules
            base_duration = max(int(rules.min_base_duration_bars), int(lookback * 0.5))
            guard = max(1, int(rules.max_breakout_recency_bars))
            neckline_source_len = max(5, base_duration - guard)
            rolling_neckline = close.rolling(neckline_source_len).max().shift(guard)
            for asof_idx in asof_indices:
                if asof_idx + 1 < lookback:
                    continue
                if not self._passes_breakout_prefilter(close, rolling_neckline, asof_idx):
                    continue
                window_df = out.iloc[asof_idx - lookback + 1 : asof_idx + 1].reset_index(drop=True)
                row = self._evaluate_window(ts_code, window_df, window)
                if row:
                    rows.append(row)

        if not rows:
            return pd.DataFrame(columns=self.output_columns)

        candidates = pd.DataFrame(rows)
        candidates = self._dedupe_candidates(candidates)
        for col in self.output_columns:
            if col not in candidates.columns:
                candidates[col] = pd.NA
        return candidates[self.output_columns].reset_index(drop=True)

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

    def _passes_breakout_prefilter(
        self,
        close: pd.Series,
        rolling_neckline: pd.Series,
        asof_idx: int,
    ) -> bool:
        current = close.iloc[asof_idx]
        neckline = rolling_neckline.iloc[asof_idx]
        if pd.isna(current) or pd.isna(neckline) or float(neckline) <= 0:
            return False
        distance = float(current) / float(neckline) - 1.0
        return (
            distance > float(self.config.rules.min_breakout_distance_pct)
            and distance <= float(self.config.rules.max_breakout_distance_pct)
        )

    def _asof_indices(self, df: pd.DataFrame, max_lookback: int) -> list[int]:
        if self.config.scan.mode == "latest":
            return [len(df) - 1] if len(df) >= max_lookback else []
        if self.config.scan.mode != "historical":
            raise ValueError(f"unsupported scan mode: {self.config.scan.mode}")

        min_date = pd.to_datetime(self.config.scan.min_asof_date, errors="coerce")
        max_date = pd.to_datetime(self.config.scan.max_asof_date, errors="coerce")
        if pd.isna(min_date):
            min_date = None
        if pd.isna(max_date):
            max_date = None

        stride = max(1, int(self.config.scan.asof_stride))
        indices: list[int] = []
        for idx in range(max(0, max_lookback - 1), len(df), stride):
            date = pd.Timestamp(df.loc[idx, "trade_date"])
            if min_date is not None and date < min_date:
                continue
            if max_date is not None and date > max_date:
                continue
            indices.append(idx)
        return indices

    def _evaluate_window(
        self,
        ts_code: str,
        window_df: pd.DataFrame,
        window: BottomBaseWindowConfig,
    ) -> dict[str, Any] | None:
        rules = self.config.rules
        asof_idx = len(window_df) - 1
        base_duration = max(int(rules.min_base_duration_bars), int(int(window.lookback) * 0.5))
        if len(window_df) < base_duration + 2:
            return None

        base_start = len(window_df) - base_duration
        base_df = window_df.iloc[base_start:].reset_index(drop=True)
        neckline_date, neckline_price = find_neckline(
            base_df=base_df,
            max_breakout_recency_bars=int(rules.max_breakout_recency_bars),
        )
        if neckline_date is None or neckline_price is None or neckline_price <= 0:
            return None

        breakout_idx = _find_breakout_idx(
            window_df=window_df,
            neckline_price=neckline_price,
            start_date=neckline_date,
            min_breakout_distance_pct=float(rules.min_breakout_distance_pct),
        )
        if breakout_idx is None:
            return None

        breakout_recency_bars = asof_idx - breakout_idx
        if breakout_recency_bars < 0 or breakout_recency_bars > int(rules.max_breakout_recency_bars):
            return None

        current_close = float(window_df.loc[asof_idx, "close"])
        breakout_distance_pct = current_close / neckline_price - 1.0
        if breakout_distance_pct < float(rules.min_breakout_distance_pct):
            return None
        if breakout_distance_pct > float(rules.max_breakout_distance_pct):
            return None

        breakout_date = pd.Timestamp(window_df.loc[breakout_idx, "trade_date"])
        base_until_breakout = base_df[base_df["trade_date"] < breakout_date].copy()
        if len(base_until_breakout) < int(rules.min_base_duration_bars):
            return None

        low_series = pd.to_numeric(base_until_breakout["low"], errors="coerce")
        close_series = pd.to_numeric(base_until_breakout["close"], errors="coerce")
        if low_series.dropna().empty or close_series.dropna().empty:
            return None
        base_low_pos = int(low_series.idxmin())
        base_low_price = float(low_series.loc[base_low_pos])
        base_low_date = pd.Timestamp(base_until_breakout.loc[base_low_pos, "trade_date"])
        if base_low_price <= 0:
            return None

        base_high_price = float(close_series.max())
        base_range_pct = (base_high_price - base_low_price) / base_low_price
        base_close_std_pct = float(close_series.std(ddof=0) / close_series.mean()) if close_series.mean() > 0 else 999.0
        if base_range_pct > float(rules.max_base_range_pct):
            return None
        if base_close_std_pct > float(rules.max_base_close_std_pct):
            return None

        prior_df = window_df[window_df["trade_date"] < base_low_date]
        if prior_df.empty:
            return None
        high_series = pd.to_numeric(prior_df["high"], errors="coerce")
        if high_series.dropna().empty:
            return None
        prior_high_pos = int(high_series.idxmax())
        prior_high_price = float(window_df.loc[prior_high_pos, "high"])
        prior_high_date = pd.Timestamp(window_df.loc[prior_high_pos, "trade_date"])
        if prior_high_price <= 0:
            return None

        prior_drawdown_pct = (prior_high_price - base_low_price) / prior_high_price
        if prior_drawdown_pct < float(rules.min_prior_drawdown_pct):
            return None

        neckline_rebound_pct = neckline_price / base_low_price - 1.0
        if neckline_rebound_pct < float(rules.min_neckline_rebound_from_base_low_pct):
            return None

        right_recovery_pct = current_close / base_low_price - 1.0
        if right_recovery_pct < float(rules.min_right_recovery_pct):
            return None
        if right_recovery_pct < float(rules.min_close_vs_base_low_pct):
            return None

        touches = int((close_series <= base_low_price * (1.0 + float(rules.base_zone_pct))).sum())
        if touches < int(rules.min_touches_in_base_zone):
            return None

        volume_ratio_20 = self._volume_ratio(window_df)
        score = self._score(
            prior_drawdown_pct=prior_drawdown_pct,
            base_range_pct=base_range_pct,
            base_close_std_pct=base_close_std_pct,
            neckline_rebound_pct=neckline_rebound_pct,
            breakout_distance_pct=breakout_distance_pct,
            breakout_recency_bars=breakout_recency_bars,
            volume_ratio_20=volume_ratio_20,
        )

        asof_date = _date_str(window_df.loc[asof_idx, "trade_date"])
        sample_id = f"{ts_code}_{asof_date}_{self.name}_{window.name}"
        pattern_stage = "bottom_base_recent_breakout"
        return {
            "sample_id": sample_id,
            "ts_code": ts_code,
            "asof_date": asof_date,
            "label": int(self.config.label.label),
            "label_source": self.config.label.label_source,
            "confidence": float(self.config.label.confidence),
            "event_id": sample_id,
            "miner_name": self.name,
            "candidate_score": score,
            "close": current_close,
            "ret_1d": _pct_change(window_df["close"], asof_idx, 1),
            "ret_3d": _pct_change(window_df["close"], asof_idx, 3),
            "vol_ratio_1d": volume_ratio_20,
            "vol_ratio_3d": pd.NA,
            "base_window_days": int(window.lookback),
            "base_range_pct": base_range_pct,
            "breakout_flag": True,
            "rule_flags": _rule_flags(
                prior_drawdown_pct=prior_drawdown_pct,
                base_range_pct=base_range_pct,
                base_close_std_pct=base_close_std_pct,
                neckline_rebound_pct=neckline_rebound_pct,
                breakout_distance_pct=breakout_distance_pct,
                breakout_recency_bars=breakout_recency_bars,
                touches=touches,
                volume_ratio_20=volume_ratio_20,
                volume_ok=self._volume_ok(volume_ratio_20),
            ),
            "window": window.name,
            "pattern_stage": pattern_stage,
            "prior_high_date": _date_str(prior_high_date),
            "prior_high_price": prior_high_price,
            "base_low_date": _date_str(base_low_date),
            "base_low_price": base_low_price,
            "base_high_price": base_high_price,
            "base_close_std_pct": base_close_std_pct,
            "neckline_date": _date_str(neckline_date),
            "neckline_price": neckline_price,
            "current_close": current_close,
            "breakout_date": _date_str(breakout_date),
            "breakout_distance_pct": breakout_distance_pct,
            "breakout_recency_bars": breakout_recency_bars,
            "prior_drawdown_pct": prior_drawdown_pct,
            "neckline_rebound_from_base_low_pct": neckline_rebound_pct,
            "touches_in_base_zone": touches,
            "volume_ratio_20": volume_ratio_20,
            "left_bottom_date": _date_str(base_low_date),
            "left_bottom_price": base_low_price,
            "middle_peak_date": _date_str(neckline_date),
            "middle_peak_price": neckline_price,
            "right_bottom_date": _date_str(base_low_date),
            "right_bottom_price": base_low_price,
        }

    def _volume_ratio(self, window_df: pd.DataFrame) -> float:
        if not self.config.volume.enable or "vol" not in window_df.columns:
            return 0.0
        vol = pd.to_numeric(window_df["vol"], errors="coerce").fillna(0.0)
        ma_window = int(self.config.volume.ma_window)
        if ma_window <= 0 or len(vol) < ma_window:
            return 0.0
        volume_ma = float(vol.rolling(ma_window).mean().iloc[-1])
        current_vol = float(vol.iloc[-1])
        if volume_ma <= 0:
            return 0.0
        return current_vol / volume_ma

    def _volume_ok(self, volume_ratio_20: float) -> bool:
        return bool(
            self.config.volume.enable
            and volume_ratio_20 >= float(self.config.volume.breakout_volume_ratio)
        )

    def _score(
        self,
        *,
        prior_drawdown_pct: float,
        base_range_pct: float,
        base_close_std_pct: float,
        neckline_rebound_pct: float,
        breakout_distance_pct: float,
        breakout_recency_bars: int,
        volume_ratio_20: float,
    ) -> float:
        rules = self.config.rules
        scoring = self.config.scoring
        prior_score = _clamp(prior_drawdown_pct / max(float(rules.min_prior_drawdown_pct) * 2.0, 1e-9))
        range_score = _clamp(1.0 - base_range_pct / max(float(rules.max_base_range_pct), 1e-9))
        std_score = _clamp(1.0 - base_close_std_pct / max(float(rules.max_base_close_std_pct), 1e-9))
        base_stability_score = (range_score + std_score) / 2.0
        neckline_score = _clamp(
            neckline_rebound_pct / max(float(rules.min_neckline_rebound_from_base_low_pct) * 2.0, 1e-9)
        )
        freshness_score = _clamp(1.0 - breakout_recency_bars / max(float(rules.max_breakout_recency_bars), 1.0))
        distance_mid = max(float(rules.max_breakout_distance_pct) * 0.5, 1e-9)
        distance_score = _clamp(1.0 - abs(breakout_distance_pct - distance_mid) / max(distance_mid, 1e-9))
        volume_score = 1.0 if self._volume_ok(volume_ratio_20) else 0.0

        weights = {
            "prior": float(scoring.weight_prior_drawdown),
            "base": float(scoring.weight_base_stability),
            "neckline": float(scoring.weight_neckline_rebound),
            "freshness": float(scoring.weight_breakout_freshness),
            "distance": float(scoring.weight_breakout_distance),
            "volume": float(scoring.weight_volume) if self.config.volume.enable else 0.0,
        }
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return 0.0
        score = (
            prior_score * weights["prior"]
            + base_stability_score * weights["base"]
            + neckline_score * weights["neckline"]
            + freshness_score * weights["freshness"]
            + distance_score * weights["distance"]
            + volume_score * weights["volume"]
        ) / total_weight
        return round(_clamp(score), 6)

    def _dedupe_candidates(self, candidates: pd.DataFrame) -> pd.DataFrame:
        sorted_candidates = candidates.sort_values(["candidate_score", "asof_date"], ascending=[False, True])
        selected_rows: list[pd.Series] = []
        min_days = int(self.config.scan.min_days_between_candidates)
        for _, row in sorted_candidates.iterrows():
            row_date = pd.Timestamp(row["asof_date"])
            too_close = False
            for selected in selected_rows:
                if row["window"] != selected["window"]:
                    continue
                selected_date = pd.Timestamp(selected["asof_date"])
                if abs((row_date - selected_date).days) < min_days:
                    too_close = True
                    break
            if not too_close:
                selected_rows.append(row)

        if not selected_rows:
            return pd.DataFrame(columns=self.output_columns)
        out = pd.DataFrame(selected_rows)
        max_candidates = int(self.config.scan.max_candidates_per_symbol or self.config.output.max_candidates_per_symbol)
        if max_candidates > 0:
            out = out.head(max_candidates)
        return out.sort_values(["candidate_score", "asof_date"], ascending=[False, False]).reset_index(drop=True)


def find_neckline(
    *,
    base_df: pd.DataFrame,
    max_breakout_recency_bars: int,
) -> tuple[pd.Timestamp | None, float | None]:
    if base_df.empty or "close" not in base_df.columns:
        return None, None
    guard = max(1, int(max_breakout_recency_bars))
    if len(base_df) > guard + 5:
        source = base_df.iloc[:-guard].copy()
    else:
        source = base_df.iloc[:-1].copy()
    if source.empty:
        return None, None
    close = pd.to_numeric(source["close"], errors="coerce")
    if close.dropna().empty:
        return None, None
    idx = int(close.idxmax())
    return pd.Timestamp(source.loc[idx, "trade_date"]), float(close.loc[idx])


def _find_breakout_idx(
    *,
    window_df: pd.DataFrame,
    neckline_price: float,
    start_date: pd.Timestamp,
    min_breakout_distance_pct: float,
) -> int | None:
    threshold = neckline_price * (1.0 + min_breakout_distance_pct)
    close = pd.to_numeric(window_df["close"], errors="coerce")
    start_matches = window_df.index[window_df["trade_date"] >= start_date].tolist()
    if not start_matches:
        return None
    start_idx = int(start_matches[0]) + 1
    for idx in range(start_idx, len(window_df)):
        value = close.iloc[idx]
        if pd.isna(value) or float(value) <= threshold:
            continue
        prev_value = close.iloc[idx - 1] if idx > 0 else pd.NA
        if pd.isna(prev_value) or float(prev_value) <= threshold:
            return idx
    return None


def _rule_flags(
    *,
    prior_drawdown_pct: float,
    base_range_pct: float,
    base_close_std_pct: float,
    neckline_rebound_pct: float,
    breakout_distance_pct: float,
    breakout_recency_bars: int,
    touches: int,
    volume_ratio_20: float,
    volume_ok: bool,
) -> str:
    flags = [
        "prior_drawdown_ok",
        "base_stability_ok",
        "neckline_rebound_ok",
        "recent_breakout_ok",
        f"prior_drawdown={prior_drawdown_pct:.3f}",
        f"base_range={base_range_pct:.3f}",
        f"base_std={base_close_std_pct:.3f}",
        f"neckline_rebound={neckline_rebound_pct:.3f}",
        f"breakout_distance={breakout_distance_pct:.3f}",
        f"breakout_recency={breakout_recency_bars}",
        f"touches={touches}",
        f"volume_ratio_20={volume_ratio_20:.3f}",
    ]
    if volume_ok:
        flags.append("volume_breakout_ok")
    return ";".join(flags)


def _pct_change(close: pd.Series, idx: int, periods: int) -> float:
    prev_idx = idx - periods
    if prev_idx < 0:
        return float("nan")
    current = float(close.iloc[idx])
    prev = float(close.iloc[prev_idx])
    if prev <= 0:
        return float("nan")
    return current / prev - 1.0


def _date_str(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


__all__ = [
    "BOTTOM_BASE_BREAKOUT_COLUMNS",
    "BottomBaseBreakoutConfig",
    "BottomBaseBreakoutMiner",
    "find_neckline",
]
