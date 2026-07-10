from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from market_pattern_labeler.miners.base import BaseMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS
from market_pattern_labeler.utils.dates import to_trade_datetime


LONG_BASE_BREAKOUT_COLUMNS = CANDIDATE_COLUMNS + [
    "window",
    "pattern_stage",
    "prior_high_date",
    "prior_high_price",
    "support_price",
    "support_zone_upper",
    "support_touch_count",
    "support_touch_dates",
    "support_touch_span_bars",
    "support_zone_std_pct",
    "base_start_date",
    "base_end_date",
    "base_duration_bars",
    "neckline_date",
    "neckline_price",
    "neckline_rebound_from_support_pct",
    "neckline_to_prior_high_ratio",
    "breakout_date",
    "breakout_price",
    "breakout_distance_pct",
    "breakout_recency_bars",
    "right_side_duration_bars",
    "monthly_trend_ok",
    "monthly_trend_months",
    "monthly_trend_return_pct",
    "monthly_trend_ma_slope_pct",
    "monthly_close_vs_ma_pct",
    "current_close",
    "prior_drawdown_pct",
    "volume_ratio_20",
    "base_low_date",
    "base_low_price",
    "middle_peak_date",
    "middle_peak_price",
    "left_bottom_date",
    "left_bottom_price",
    "right_bottom_date",
    "right_bottom_price",
]


@dataclass
class LongBaseLabelConfig:
    label: int = 1
    label_source: str = "rule_long_base_breakout"
    confidence: float = 0.70

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongBaseLabelConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class LongBaseScanConfig:
    mode: str = "historical"
    asof_stride: int = 10
    min_asof_date: str | None = "2016-01-01"
    max_asof_date: str | None = None
    max_candidates_per_symbol: int = 80
    min_days_between_candidates: int = 60

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongBaseScanConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class LongBaseWindowConfig:
    name: str
    lookback: int


@dataclass
class LongBaseRulesConfig:
    min_prior_drawdown_pct: float = 0.20
    min_base_duration_bars: int = 252
    support_zone_tolerance_pct: float = 0.15
    min_support_touches: int = 2
    min_support_touch_separation_bars: int = 40
    max_support_zone_std_pct: float = 0.12
    min_neckline_rebound_from_support_pct: float = 0.15
    max_neckline_to_prior_high_ratio: float = 0.90
    min_breakout_distance_pct: float = 0.00
    max_breakout_distance_pct: float = 0.10
    max_breakout_recency_bars: int = 20
    min_right_side_duration_bars: int = 40

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongBaseRulesConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class LongBaseVolumeConfig:
    enable: bool = True
    ma_window: int = 20
    breakout_volume_ratio: float = 1.10
    volume_as_bonus_only: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongBaseVolumeConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class LongBaseMonthlyTrendConfig:
    enable: bool = False
    min_months: int = 36
    ma_window_months: int = 12
    slope_months: int = 6
    lookback_months: int = 24
    min_ma_slope_pct: float = 0.02
    min_lookback_return_pct: float = 0.00
    min_close_vs_ma_pct: float = -0.05

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongBaseMonthlyTrendConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class LongBaseScoringConfig:
    weight_prior_drawdown: float = 0.15
    weight_support_stability: float = 0.25
    weight_neckline_quality: float = 0.15
    weight_breakout_freshness: float = 0.15
    weight_breakout_distance: float = 0.10
    weight_base_duration: float = 0.15
    weight_volume: float = 0.05

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongBaseScoringConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class LongBaseOutputConfig:
    max_candidates_per_symbol: int = 80

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongBaseOutputConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class LongBaseBreakoutConfig:
    label: LongBaseLabelConfig = field(default_factory=LongBaseLabelConfig)
    scan: LongBaseScanConfig = field(default_factory=LongBaseScanConfig)
    windows: list[LongBaseWindowConfig] = field(
        default_factory=lambda: [
            LongBaseWindowConfig(name="one_year", lookback=252),
            LongBaseWindowConfig(name="two_year", lookback=504),
            LongBaseWindowConfig(name="three_year", lookback=756),
            LongBaseWindowConfig(name="four_year", lookback=1008),
        ]
    )
    rules: LongBaseRulesConfig = field(default_factory=LongBaseRulesConfig)
    volume: LongBaseVolumeConfig = field(default_factory=LongBaseVolumeConfig)
    monthly_trend: LongBaseMonthlyTrendConfig = field(default_factory=LongBaseMonthlyTrendConfig)
    scoring: LongBaseScoringConfig = field(default_factory=LongBaseScoringConfig)
    output: LongBaseOutputConfig = field(default_factory=LongBaseOutputConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongBaseBreakoutConfig":
        windows_data = data.get("windows")
        if isinstance(windows_data, list):
            windows = [
                LongBaseWindowConfig(
                    name=str(item.get("name", f"window_{idx}")),
                    lookback=int(item.get("lookback", 0)),
                )
                for idx, item in enumerate(windows_data)
                if isinstance(item, dict) and int(item.get("lookback", 0)) > 0
            ]
        else:
            windows = cls().windows
        return cls(
            label=LongBaseLabelConfig.from_dict(_as_dict(data.get("label"))),
            scan=LongBaseScanConfig.from_dict(_as_dict(data.get("scan"))),
            windows=windows or cls().windows,
            rules=LongBaseRulesConfig.from_dict(_as_dict(data.get("rules"))),
            volume=LongBaseVolumeConfig.from_dict(_as_dict(data.get("volume"))),
            monthly_trend=LongBaseMonthlyTrendConfig.from_dict(_as_dict(data.get("monthly_trend"))),
            scoring=LongBaseScoringConfig.from_dict(_as_dict(data.get("scoring"))),
            output=LongBaseOutputConfig.from_dict(_as_dict(data.get("output"))),
        )


class LongBaseBreakoutMiner(BaseMiner):
    name = "long_base_breakout"
    output_columns = LONG_BASE_BREAKOUT_COLUMNS

    def __init__(self, config: LongBaseBreakoutConfig):
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
            rolling_neckline = close.rolling(max(20, int(lookback * 0.45))).max().shift(
                max(1, int(self.config.rules.max_breakout_recency_bars))
            )
            for asof_idx in asof_indices:
                if asof_idx + 1 < lookback:
                    continue
                if not self._passes_breakout_prefilter(close, rolling_neckline, asof_idx):
                    continue
                window_df = out.iloc[asof_idx - lookback + 1 : asof_idx + 1].reset_index(drop=True)
                row = self._evaluate_window(
                    ts_code,
                    window_df,
                    window,
                    full_df=out,
                    asof_idx_global=asof_idx,
                )
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

    def _asof_indices(self, df: pd.DataFrame, max_lookback: int) -> list[int]:
        if self.config.scan.mode == "latest":
            return [len(df) - 1] if len(df) >= max_lookback else []
        if self.config.scan.mode != "historical":
            raise ValueError(f"unsupported scan mode: {self.config.scan.mode}")

        min_date = pd.to_datetime(self.config.scan.min_asof_date, errors="coerce")
        max_date = pd.to_datetime(self.config.scan.max_asof_date, errors="coerce")
        min_date = None if pd.isna(min_date) else min_date
        max_date = None if pd.isna(max_date) else max_date
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

    def _passes_breakout_prefilter(self, close: pd.Series, rolling_neckline: pd.Series, asof_idx: int) -> bool:
        current = close.iloc[asof_idx]
        neckline = rolling_neckline.iloc[asof_idx]
        if pd.isna(current) or pd.isna(neckline) or float(neckline) <= 0:
            return False
        distance = float(current) / float(neckline) - 1.0
        return (
            distance > float(self.config.rules.min_breakout_distance_pct)
            and distance <= float(self.config.rules.max_breakout_distance_pct)
        )

    def _evaluate_window(
        self,
        ts_code: str,
        window_df: pd.DataFrame,
        window: LongBaseWindowConfig,
        full_df: pd.DataFrame | None = None,
        asof_idx_global: int | None = None,
    ) -> dict[str, Any] | None:
        rules = self.config.rules
        asof_idx = len(window_df) - 1
        lookback = int(window.lookback)
        recent_bars = max(1, int(rules.max_breakout_recency_bars))
        target_base_duration = max(int(rules.min_base_duration_bars), int(lookback * 0.75))
        if lookback >= int(rules.min_base_duration_bars) + recent_bars:
            target_base_duration = max(target_base_duration, int(rules.min_base_duration_bars) + recent_bars)
        base_duration = min(lookback, target_base_duration)
        if base_duration < int(rules.min_base_duration_bars) or len(window_df) < base_duration:
            return None

        base_start = len(window_df) - base_duration
        base_df = window_df.iloc[base_start:].reset_index(drop=True)
        pre_breakout_base = base_df.iloc[:-recent_bars].copy()
        min_pre_breakout_bars = max(
            int(int(rules.min_base_duration_bars) * 0.75),
            int(rules.min_support_touch_separation_bars) * max(1, int(rules.min_support_touches) - 1) + 1,
        )
        if len(pre_breakout_base) < min_pre_breakout_bars:
            return None

        prior_df = window_df.iloc[: max(1, int(lookback * 0.45))].copy()
        prior_high_pos = int(pd.to_numeric(prior_df["high"], errors="coerce").idxmax())
        prior_high_price = float(window_df.loc[prior_high_pos, "high"])
        prior_high_date = pd.Timestamp(window_df.loc[prior_high_pos, "trade_date"])
        if prior_high_price <= 0:
            return None

        close = pd.to_numeric(pre_breakout_base["close"], errors="coerce")
        low = pd.to_numeric(pre_breakout_base["low"], errors="coerce")
        support_price = float(pd.concat([close, low], ignore_index=True).quantile(0.10))
        if support_price <= 0:
            return None
        support_zone_upper = support_price * (1.0 + float(rules.support_zone_tolerance_pct))
        touch_count, touch_indices = count_separated_support_touches(
            close=close,
            support_zone_upper=support_zone_upper,
            min_separation_bars=int(rules.min_support_touch_separation_bars),
        )
        if touch_count < int(rules.min_support_touches):
            return None
        touch_prices = close.iloc[touch_indices]
        support_zone_std_pct = float(touch_prices.std(ddof=0) / touch_prices.mean()) if touch_prices.mean() > 0 else 999.0
        if support_zone_std_pct > float(rules.max_support_zone_std_pct):
            return None

        support_touch_span_bars = int(touch_indices[-1] - touch_indices[0])
        first_touch_idx = int(touch_indices[0])
        last_touch_idx = int(touch_indices[-1])
        first_touch_date = pd.Timestamp(pre_breakout_base.loc[first_touch_idx, "trade_date"])
        last_touch_date = pd.Timestamp(pre_breakout_base.loc[last_touch_idx, "trade_date"])

        prior_drawdown_pct = (prior_high_price - support_price) / prior_high_price
        if prior_drawdown_pct < float(rules.min_prior_drawdown_pct):
            return None

        neckline = self._find_neckline(
            pre_breakout_base=pre_breakout_base,
            support_price=support_price,
            prior_high_price=prior_high_price,
            first_touch_idx=first_touch_idx,
        )
        if neckline is None:
            return None
        neckline_idx, neckline_date, neckline_price = neckline
        neckline_rebound_pct = neckline_price / support_price - 1.0
        neckline_to_prior_high_ratio = neckline_price / prior_high_price
        if neckline_rebound_pct < float(rules.min_neckline_rebound_from_support_pct):
            return None
        if neckline_to_prior_high_ratio > float(rules.max_neckline_to_prior_high_ratio):
            return None

        breakout_idx = _find_breakout_idx(
            base_df=base_df,
            neckline_price=neckline_price,
            neckline_date=neckline_date,
            min_breakout_distance_pct=float(rules.min_breakout_distance_pct),
        )
        if breakout_idx is None:
            return None
        breakout_global_idx = base_start + breakout_idx
        breakout_recency_bars = asof_idx - breakout_global_idx
        if breakout_recency_bars < 0 or breakout_recency_bars > int(rules.max_breakout_recency_bars):
            return None

        current_close = float(window_df.loc[asof_idx, "close"])
        breakout_distance_pct = current_close / neckline_price - 1.0
        if breakout_distance_pct <= float(rules.min_breakout_distance_pct):
            return None
        if breakout_distance_pct > float(rules.max_breakout_distance_pct):
            return None

        right_side_duration_bars = breakout_idx - last_touch_idx
        if right_side_duration_bars < int(rules.min_right_side_duration_bars):
            return None

        monthly_trend = self._monthly_trend_metrics(full_df=full_df, asof_idx_global=asof_idx_global)
        if monthly_trend is None:
            return None

        volume_ratio_20 = self._volume_ratio(window_df)
        score = self._score(
            prior_drawdown_pct=prior_drawdown_pct,
            support_zone_std_pct=support_zone_std_pct,
            neckline_rebound_pct=neckline_rebound_pct,
            neckline_to_prior_high_ratio=neckline_to_prior_high_ratio,
            breakout_recency_bars=breakout_recency_bars,
            breakout_distance_pct=breakout_distance_pct,
            base_duration_bars=base_duration,
            volume_ratio_20=volume_ratio_20,
        )
        asof_date = _date_str(window_df.loc[asof_idx, "trade_date"])
        breakout_date = pd.Timestamp(base_df.loc[breakout_idx, "trade_date"])
        breakout_price = float(base_df.loc[breakout_idx, "close"])
        support_touch_dates = ",".join(_date_str(pre_breakout_base.loc[idx, "trade_date"]) for idx in touch_indices)
        sample_id = f"{ts_code}_{asof_date}_{self.name}_{window.name}"
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
            "base_range_pct": pd.NA,
            "breakout_flag": True,
            "rule_flags": _rule_flags(
                prior_drawdown_pct=prior_drawdown_pct,
                support_touch_count=touch_count,
                support_zone_std_pct=support_zone_std_pct,
                neckline_rebound_pct=neckline_rebound_pct,
                neckline_to_prior_high_ratio=neckline_to_prior_high_ratio,
                breakout_distance_pct=breakout_distance_pct,
                breakout_recency_bars=breakout_recency_bars,
                right_side_duration_bars=right_side_duration_bars,
                base_duration_bars=base_duration,
                volume_ratio_20=volume_ratio_20,
                volume_ok=self._volume_ok(volume_ratio_20),
                monthly_trend_ok=bool(monthly_trend["monthly_trend_ok"]),
                monthly_trend_return_pct=monthly_trend["monthly_trend_return_pct"],
                monthly_trend_ma_slope_pct=monthly_trend["monthly_trend_ma_slope_pct"],
            ),
            "window": window.name,
            "pattern_stage": "long_base_recent_breakout",
            "prior_high_date": _date_str(prior_high_date),
            "prior_high_price": prior_high_price,
            "support_price": support_price,
            "support_zone_upper": support_zone_upper,
            "support_touch_count": touch_count,
            "support_touch_dates": support_touch_dates,
            "support_touch_span_bars": support_touch_span_bars,
            "support_zone_std_pct": support_zone_std_pct,
            "base_start_date": _date_str(base_df.loc[0, "trade_date"]),
            "base_end_date": _date_str(base_df.loc[len(base_df) - 1, "trade_date"]),
            "base_duration_bars": base_duration,
            "neckline_date": _date_str(neckline_date),
            "neckline_price": neckline_price,
            "neckline_rebound_from_support_pct": neckline_rebound_pct,
            "neckline_to_prior_high_ratio": neckline_to_prior_high_ratio,
            "breakout_date": _date_str(breakout_date),
            "breakout_price": breakout_price,
            "breakout_distance_pct": breakout_distance_pct,
            "breakout_recency_bars": breakout_recency_bars,
            "right_side_duration_bars": right_side_duration_bars,
            **monthly_trend,
            "current_close": current_close,
            "prior_drawdown_pct": prior_drawdown_pct,
            "volume_ratio_20": volume_ratio_20,
            "base_low_date": _date_str(first_touch_date),
            "base_low_price": support_price,
            "middle_peak_date": _date_str(neckline_date),
            "middle_peak_price": neckline_price,
            "left_bottom_date": _date_str(first_touch_date),
            "left_bottom_price": support_price,
            "right_bottom_date": _date_str(last_touch_date),
            "right_bottom_price": support_price,
        }

    def _find_neckline(
        self,
        *,
        pre_breakout_base: pd.DataFrame,
        support_price: float,
        prior_high_price: float,
        first_touch_idx: int,
    ) -> tuple[int, pd.Timestamp, float] | None:
        rules = self.config.rules
        source = pre_breakout_base.iloc[first_touch_idx + 1 :].copy()
        if len(source) < 5:
            return None
        close = pd.to_numeric(source["close"], errors="coerce")
        min_price = support_price * (1.0 + float(rules.min_neckline_rebound_from_support_pct))
        max_price = prior_high_price * float(rules.max_neckline_to_prior_high_ratio)
        valid = close[(close >= min_price) & (close <= max_price)]
        if valid.dropna().empty:
            q85 = float(close.quantile(0.85))
            if min_price <= q85 <= max_price:
                rel_idx = int((close - q85).abs().idxmin())
            else:
                return None
        else:
            rel_idx = int(valid.idxmax())
        return rel_idx, pd.Timestamp(pre_breakout_base.loc[rel_idx, "trade_date"]), float(pre_breakout_base.loc[rel_idx, "close"])

    def _monthly_trend_metrics(
        self,
        *,
        full_df: pd.DataFrame | None,
        asof_idx_global: int | None,
    ) -> dict[str, Any] | None:
        cfg = self.config.monthly_trend
        if not cfg.enable:
            return {
                "monthly_trend_ok": True,
                "monthly_trend_months": pd.NA,
                "monthly_trend_return_pct": pd.NA,
                "monthly_trend_ma_slope_pct": pd.NA,
                "monthly_close_vs_ma_pct": pd.NA,
            }
        if full_df is None or asof_idx_global is None or asof_idx_global < 0:
            return None

        history = full_df.iloc[: asof_idx_global + 1][["trade_date", "close"]].copy()
        history["trade_date"] = to_trade_datetime(history["trade_date"])
        history["close"] = pd.to_numeric(history["close"], errors="coerce")
        history = history.dropna(subset=["trade_date", "close"])
        if history.empty:
            return None

        history["month"] = history["trade_date"].dt.to_period("M")
        monthly = history.groupby("month", sort=True)["close"].last().dropna()
        ma_window = max(1, int(cfg.ma_window_months))
        slope_months = max(1, int(cfg.slope_months))
        lookback_months = max(1, int(cfg.lookback_months))
        min_months = max(
            int(cfg.min_months),
            ma_window + slope_months + 1,
            lookback_months + 1,
        )
        if len(monthly) < min_months:
            return None

        ma = monthly.rolling(ma_window).mean()
        current_ma = float(ma.iloc[-1])
        prior_ma = float(ma.iloc[-1 - slope_months])
        current_close = float(monthly.iloc[-1])
        prior_close = float(monthly.iloc[-1 - lookback_months])
        if current_ma <= 0 or prior_ma <= 0 or prior_close <= 0:
            return None

        ma_slope_pct = current_ma / prior_ma - 1.0
        trend_return_pct = current_close / prior_close - 1.0
        close_vs_ma_pct = current_close / current_ma - 1.0
        if ma_slope_pct < float(cfg.min_ma_slope_pct):
            return None
        if trend_return_pct < float(cfg.min_lookback_return_pct):
            return None
        if close_vs_ma_pct < float(cfg.min_close_vs_ma_pct):
            return None

        return {
            "monthly_trend_ok": True,
            "monthly_trend_months": int(len(monthly)),
            "monthly_trend_return_pct": trend_return_pct,
            "monthly_trend_ma_slope_pct": ma_slope_pct,
            "monthly_close_vs_ma_pct": close_vs_ma_pct,
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
        support_zone_std_pct: float,
        neckline_rebound_pct: float,
        neckline_to_prior_high_ratio: float,
        breakout_recency_bars: int,
        breakout_distance_pct: float,
        base_duration_bars: int,
        volume_ratio_20: float,
    ) -> float:
        rules = self.config.rules
        scoring = self.config.scoring
        prior_score = _clamp(prior_drawdown_pct / max(float(rules.min_prior_drawdown_pct) * 2.0, 1e-9))
        support_score = _clamp(1.0 - support_zone_std_pct / max(float(rules.max_support_zone_std_pct), 1e-9))
        neckline_rebound_score = _clamp(
            neckline_rebound_pct / max(float(rules.min_neckline_rebound_from_support_pct) * 2.0, 1e-9)
        )
        neckline_ratio_score = _clamp(
            1.0 - neckline_to_prior_high_ratio / max(float(rules.max_neckline_to_prior_high_ratio), 1e-9)
        )
        neckline_score = (neckline_rebound_score + neckline_ratio_score) / 2.0
        freshness_score = _clamp(1.0 - breakout_recency_bars / max(float(rules.max_breakout_recency_bars), 1.0))
        distance_mid = max(float(rules.max_breakout_distance_pct) * 0.4, 1e-9)
        distance_score = _clamp(1.0 - abs(breakout_distance_pct - distance_mid) / distance_mid)
        duration_score = _clamp(base_duration_bars / 756.0)
        volume_score = 1.0 if self._volume_ok(volume_ratio_20) else 0.0

        weights = {
            "prior": float(scoring.weight_prior_drawdown),
            "support": float(scoring.weight_support_stability),
            "neckline": float(scoring.weight_neckline_quality),
            "freshness": float(scoring.weight_breakout_freshness),
            "distance": float(scoring.weight_breakout_distance),
            "duration": float(scoring.weight_base_duration),
            "volume": float(scoring.weight_volume) if self.config.volume.enable else 0.0,
        }
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return 0.0
        score = (
            prior_score * weights["prior"]
            + support_score * weights["support"]
            + neckline_score * weights["neckline"]
            + freshness_score * weights["freshness"]
            + distance_score * weights["distance"]
            + duration_score * weights["duration"]
            + volume_score * weights["volume"]
        ) / total_weight
        return round(_clamp(score), 6)

    def _dedupe_candidates(self, candidates: pd.DataFrame) -> pd.DataFrame:
        sorted_candidates = candidates.sort_values(["candidate_score", "asof_date"], ascending=[False, True])
        selected_rows: list[pd.Series] = []
        min_days = int(self.config.scan.min_days_between_candidates)
        for _, row in sorted_candidates.iterrows():
            row_date = pd.Timestamp(row["asof_date"])
            if any(abs((row_date - pd.Timestamp(selected["asof_date"])).days) < min_days for selected in selected_rows):
                continue
            selected_rows.append(row)
        if not selected_rows:
            return pd.DataFrame(columns=self.output_columns)
        out = pd.DataFrame(selected_rows)
        max_candidates = int(self.config.scan.max_candidates_per_symbol or self.config.output.max_candidates_per_symbol)
        if max_candidates > 0:
            out = out.head(max_candidates)
        return out.sort_values(["candidate_score", "asof_date"], ascending=[False, False]).reset_index(drop=True)


def count_separated_support_touches(
    *,
    close: pd.Series,
    support_zone_upper: float,
    min_separation_bars: int,
) -> tuple[int, list[int]]:
    touch_indices = [int(idx) for idx, value in close.items() if pd.notna(value) and float(value) <= support_zone_upper]
    selected: list[int] = []
    for idx in touch_indices:
        if not selected or idx - selected[-1] >= int(min_separation_bars):
            selected.append(idx)
    return len(selected), selected


def _find_breakout_idx(
    *,
    base_df: pd.DataFrame,
    neckline_price: float,
    neckline_date: pd.Timestamp,
    min_breakout_distance_pct: float,
) -> int | None:
    threshold = neckline_price * (1.0 + min_breakout_distance_pct)
    close = pd.to_numeric(base_df["close"], errors="coerce")
    start_matches = base_df.index[base_df["trade_date"] >= neckline_date].tolist()
    if not start_matches:
        return None
    for idx in range(int(start_matches[0]) + 1, len(base_df)):
        value = close.iloc[idx]
        if pd.isna(value) or float(value) <= threshold:
            continue
        prev = close.iloc[idx - 1] if idx > 0 else pd.NA
        if pd.isna(prev) or float(prev) <= threshold:
            return idx
    return None


def _rule_flags(
    *,
    prior_drawdown_pct: float,
    support_touch_count: int,
    support_zone_std_pct: float,
    neckline_rebound_pct: float,
    neckline_to_prior_high_ratio: float,
    breakout_distance_pct: float,
    breakout_recency_bars: int,
    right_side_duration_bars: int,
    base_duration_bars: int,
    volume_ratio_20: float,
    volume_ok: bool,
    monthly_trend_ok: bool,
    monthly_trend_return_pct: Any,
    monthly_trend_ma_slope_pct: Any,
) -> str:
    flags = [
        "prior_drawdown_ok",
        "support_stability_ok",
        "neckline_quality_ok",
        "recent_breakout_ok",
        "monthly_trend_ok" if monthly_trend_ok else "monthly_trend_unchecked",
        f"prior_drawdown={prior_drawdown_pct:.3f}",
        f"support_touches={support_touch_count}",
        f"support_std={support_zone_std_pct:.3f}",
        f"neckline_rebound={neckline_rebound_pct:.3f}",
        f"neckline_to_prior_high={neckline_to_prior_high_ratio:.3f}",
        f"breakout_distance={breakout_distance_pct:.3f}",
        f"breakout_recency={breakout_recency_bars}",
        f"right_side_duration={right_side_duration_bars}",
        f"base_duration={base_duration_bars}",
        f"volume_ratio_20={volume_ratio_20:.3f}",
    ]
    if pd.notna(monthly_trend_return_pct):
        flags.append(f"monthly_return={float(monthly_trend_return_pct):.3f}")
    if pd.notna(monthly_trend_ma_slope_pct):
        flags.append(f"monthly_ma_slope={float(monthly_trend_ma_slope_pct):.3f}")
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
    "LONG_BASE_BREAKOUT_COLUMNS",
    "LongBaseBreakoutConfig",
    "LongBaseBreakoutMiner",
    "count_separated_support_touches",
]
