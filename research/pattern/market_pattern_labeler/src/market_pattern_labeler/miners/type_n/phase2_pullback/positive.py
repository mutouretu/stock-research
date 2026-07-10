from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


BASE_COLUMNS = [
    "sample_id",
    "ts_code",
    "asof_date",
    "label",
    "label_type",
    "label_source",
    "label_subtype",
    "confidence",
    "event_id",
    "recent_high_date",
    "recent_high",
    "days_since_high",
    "lookback_low",
    "rise_into_high_pct",
    "current_close",
    "current_volume",
    "drawdown_from_high",
    "pullback_depth_pct",
    "pullback_speed_pct_per_day",
    "ma5_distance",
    "ma20_distance",
    "ma60_distance",
    "volatility_20d",
    "volume_ratio_20",
    "turnover_ratio",
    "rule_flags",
]


@dataclass
class PullbackConfig:
    lookback_days: int = 90
    min_rise_into_high_pct: float = 0.10
    min_drawdown_pct: float = 0.03
    max_drawdown_pct: float = 0.25
    min_pullback_speed_pct_per_day: float = 0.0
    min_days_since_high: int = 1
    max_days_since_high: int = 40
    positive_label_subtype: str = "simple_pullback"


@dataclass
class DiagnosticsConfig:
    compute_future_returns: bool = True
    future_windows: list[int] = field(default_factory=lambda: [5, 10, 20])
    prefix: str = "diagnostic_"


@dataclass
class PullbackPatternConfig:
    label_source: str = "pullback_pattern"
    pullback: PullbackConfig = field(default_factory=PullbackConfig)
    diagnostics: DiagnosticsConfig = field(default_factory=DiagnosticsConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PullbackPatternConfig":
        payload = dict(data or {})
        # Backward compatible: allow either top-level parameters or a pullback block.
        pullback_payload = dict(payload.get("pullback", {}))
        for key in [
            "lookback_days",
            "min_rise_into_high_pct",
            "min_drawdown_pct",
            "max_drawdown_pct",
            "min_days_since_high",
            "max_days_since_high",
        ]:
            if key in payload and key not in pullback_payload:
                pullback_payload[key] = payload[key]
        return cls(
            label_source=str(payload.get("label_source", "pullback_pattern")),
            pullback=PullbackConfig(**pullback_payload),
            diagnostics=DiagnosticsConfig(**payload.get("diagnostics", {})),
        )


class PullbackPatternMiner:
    """Independent Phase 2 miner: recall stocks that rose and then pulled back.

    This miner intentionally does not detect Phase 1 breakout anchors. It only labels
    whether the current asof date is in a simple pullback state after a recent rise.
    """

    name = "pullback_pattern"

    def __init__(self, config: PullbackPatternConfig):
        self.config = config

    def scan_one(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        return self.generate_samples(ts_code, df)

    def generate_samples(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        daily = self._prepare_daily(df)
        min_rows = self.config.pullback.lookback_days
        if len(daily) < min_rows:
            return self._empty_frame()
        daily = self._add_derived_features(daily)

        rows = [self._build_sample(ts_code, daily, asof_idx) for asof_idx in range(min_rows - 1, len(daily))]
        return self._frame(rows)

    def generate_sample_for_asof(
        self,
        ts_code: str,
        df: pd.DataFrame,
        asof_date: str | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        daily = self._prepare_daily(df)
        min_rows = self.config.pullback.lookback_days
        if len(daily) < min_rows:
            return self._empty_frame()
        daily = self._add_derived_features(daily)

        if asof_date is None:
            asof_idx = len(daily) - 1
        else:
            target = pd.to_datetime(asof_date, errors="coerce")
            if pd.isna(target):
                return self._empty_frame()
            matched = daily.index[daily["trade_date"] == target]
            if len(matched) == 0:
                return self._empty_frame()
            asof_idx = int(matched[-1])

        if asof_idx < min_rows - 1:
            return self._empty_frame()
        return self._frame([self._build_sample(ts_code, daily, asof_idx)])

    def generate_samples_for_range(
        self,
        ts_code: str,
        df: pd.DataFrame,
        start_date: str | pd.Timestamp | None = None,
        end_date: str | pd.Timestamp | None = None,
        date_stride: int = 1,
    ) -> pd.DataFrame:
        daily = self._prepare_daily(df)
        min_rows = self.config.pullback.lookback_days
        if len(daily) < min_rows:
            return self._empty_frame()
        daily = self._add_derived_features(daily)

        start_ts = pd.to_datetime(start_date, errors="coerce") if start_date else None
        end_ts = pd.to_datetime(end_date, errors="coerce") if end_date else None
        if start_ts is not None and pd.isna(start_ts):
            return self._empty_frame()
        if end_ts is not None and pd.isna(end_ts):
            return self._empty_frame()

        mask = daily.index >= min_rows - 1
        if start_ts is not None:
            mask &= daily["trade_date"] >= start_ts
        if end_ts is not None:
            mask &= daily["trade_date"] <= end_ts

        asof_indices = daily.index[mask]
        stride = max(1, int(date_stride))
        if stride > 1:
            asof_indices = asof_indices[::stride]

        rows = [self._build_sample(ts_code, daily, int(asof_idx)) for asof_idx in asof_indices]
        return self._frame(rows)

    @property
    def output_columns(self) -> list[str]:
        cols = list(BASE_COLUMNS)
        if self.config.diagnostics.compute_future_returns:
            for window in self.config.diagnostics.future_windows:
                cols.extend(
                    [
                        f"{self.config.diagnostics.prefix}future_max_return_{window}d",
                        f"{self.config.diagnostics.prefix}future_min_return_{window}d",
                        f"{self.config.diagnostics.prefix}future_close_return_{window}d",
                    ]
                )
        return cols

    def _empty_frame(self) -> pd.DataFrame:
        return pd.DataFrame(columns=self.output_columns)

    def _frame(self, rows: list[dict[str, Any]]) -> pd.DataFrame:
        if not rows:
            return self._empty_frame()
        out = pd.DataFrame(rows)
        for col in self.output_columns:
            if col not in out.columns:
                out[col] = pd.NA
        return out[self.output_columns].reset_index(drop=True)

    def _prepare_daily(self, df: pd.DataFrame) -> pd.DataFrame:
        required = {"trade_date", "close"}
        missing = required - set(df.columns)
        if missing:
            return pd.DataFrame(columns=["trade_date", "close", "high", "low", "vol"])
        out = df.copy()
        out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce")
        out = out.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
        for col in ["open", "high", "low", "close", "vol", "amount", "turnover_ratio"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        if "high" not in out.columns:
            out["high"] = out["close"]
        if "low" not in out.columns:
            out["low"] = out["close"]
        if "vol" not in out.columns:
            out["vol"] = pd.NA
        return out

    def _add_derived_features(self, daily: pd.DataFrame) -> pd.DataFrame:
        out = daily.copy()
        close = pd.to_numeric(out["close"], errors="coerce")
        vol = pd.to_numeric(out["vol"], errors="coerce")
        for window in [5, 20, 60]:
            ma = close.rolling(window).mean()
            out[f"_ma{window}_distance"] = close / ma - 1.0
        out["_volatility_20d"] = close.pct_change().rolling(20).std()
        out["_volume_ratio_20"] = vol / vol.rolling(20).mean()
        return out

    def _build_sample(self, ts_code: str, daily: pd.DataFrame, asof_idx: int) -> dict[str, Any]:
        cfg = self.config.pullback
        asof_date = daily.loc[asof_idx, "trade_date"]
        current_close = self._to_float(daily.loc[asof_idx, "close"])
        current_volume = self._to_float(daily.loc[asof_idx, "vol"])
        start_idx = asof_idx - cfg.lookback_days + 1
        window = daily.iloc[start_idx : asof_idx + 1]
        close = pd.to_numeric(window["close"], errors="coerce")

        if close.dropna().empty or pd.isna(current_close) or current_close <= 0:
            row = self._base_row(ts_code, asof_date, 0, "invalid_price")
            row.update(self._future_diagnostics(daily, asof_idx, current_close))
            return row

        high_pos = int(close.reset_index(drop=True).idxmax())
        high_idx = start_idx + high_pos
        recent_high = self._to_float(daily.loc[high_idx, "close"])
        recent_high_date = daily.loc[high_idx, "trade_date"]
        pre_high_close = close.iloc[: high_pos + 1]
        lookback_low = self._to_float(pre_high_close.min())
        days_since_high = asof_idx - high_idx

        rise_into_high_pct = recent_high / lookback_low - 1.0 if lookback_low and lookback_low > 0 else float("nan")
        drawdown_from_high = current_close / recent_high - 1.0 if recent_high and recent_high > 0 else float("nan")
        pullback_depth_pct = -drawdown_from_high if pd.notna(drawdown_from_high) else float("nan")

        subtype, flags = self._classify(
            rise_into_high_pct=rise_into_high_pct,
            pullback_depth_pct=pullback_depth_pct,
            days_since_high=days_since_high,
        )
        label = 1 if subtype == cfg.positive_label_subtype else 0

        row = self._base_row(ts_code, asof_date, label, subtype)
        row.update(
            {
                "event_id": f"{ts_code}_{asof_date.strftime('%Y-%m-%d')}_pullback",
                "recent_high_date": recent_high_date.strftime("%Y-%m-%d"),
                "recent_high": recent_high,
                "days_since_high": days_since_high,
                "lookback_low": lookback_low,
                "rise_into_high_pct": rise_into_high_pct,
                "current_close": current_close,
                "current_volume": current_volume,
                "drawdown_from_high": drawdown_from_high,
                "pullback_depth_pct": pullback_depth_pct,
                "pullback_speed_pct_per_day": self._pullback_speed(pullback_depth_pct, days_since_high),
                "rule_flags": ";".join(flags),
            }
        )
        row.update(self._current_metrics(daily, asof_idx))
        row.update(self._future_diagnostics(daily, asof_idx, current_close))
        return row

    def _base_row(self, ts_code: str, asof_date: pd.Timestamp, label: int, subtype: str) -> dict[str, Any]:
        asof = asof_date.strftime("%Y-%m-%d")
        return {
            "sample_id": f"{ts_code}_{asof}",
            "ts_code": ts_code,
            "asof_date": asof,
            "label": label,
            "label_type": "pattern",
            "label_source": self.config.label_source,
            "label_subtype": subtype,
            "confidence": 1.0,
            "rule_flags": "",
        }

    def _classify(self, *, rise_into_high_pct: float, pullback_depth_pct: float, days_since_high: int) -> tuple[str, list[str]]:
        cfg = self.config.pullback
        flags: list[str] = []
        if pd.isna(rise_into_high_pct) or rise_into_high_pct < cfg.min_rise_into_high_pct:
            return "no_prior_rise", flags + ["no_prior_rise"]
        flags.append("prior_rise")
        if days_since_high < cfg.min_days_since_high or pd.isna(pullback_depth_pct) or pullback_depth_pct < cfg.min_drawdown_pct:
            return "no_pullback", flags + ["no_meaningful_pullback"]
        flags.append("has_pullback")
        if days_since_high > cfg.max_days_since_high:
            return "stale_pullback", flags + ["stale_pullback"]
        if pullback_depth_pct > cfg.max_drawdown_pct:
            return "too_deep_drawdown", flags + ["too_deep_drawdown"]
        speed = self._pullback_speed(pullback_depth_pct, days_since_high)
        if pd.isna(speed) or speed < cfg.min_pullback_speed_pct_per_day:
            return "slow_pullback", flags + ["slow_pullback"]
        return cfg.positive_label_subtype, flags + ["pullback_depth_ok", "days_since_high_ok", "pullback_speed_ok"]

    @staticmethod
    def _pullback_speed(pullback_depth_pct: float, days_since_high: int) -> float:
        if pd.isna(pullback_depth_pct) or days_since_high <= 0:
            return float("nan")
        return float(pullback_depth_pct / days_since_high)

    def _current_metrics(self, daily: pd.DataFrame, asof_idx: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for window in [5, 20, 60]:
            result[f"ma{window}_distance"] = self._to_float(daily.loc[asof_idx, f"_ma{window}_distance"])
        result["volatility_20d"] = self._to_float(daily.loc[asof_idx, "_volatility_20d"])
        result["volume_ratio_20"] = self._to_float(daily.loc[asof_idx, "_volume_ratio_20"])
        result["turnover_ratio"] = self._to_float(daily.loc[asof_idx, "turnover_ratio"]) if "turnover_ratio" in daily.columns else pd.NA
        return result

    def _future_diagnostics(self, daily: pd.DataFrame, asof_idx: int, current_close: float) -> dict[str, Any]:
        if not self.config.diagnostics.compute_future_returns or pd.isna(current_close) or current_close <= 0:
            return {}
        close = pd.to_numeric(daily["close"], errors="coerce")
        high = pd.to_numeric(daily["high"], errors="coerce")
        low = pd.to_numeric(daily["low"], errors="coerce")
        result: dict[str, Any] = {}
        for window in self.config.diagnostics.future_windows:
            future = slice(asof_idx + 1, asof_idx + 1 + int(window))
            future_close = close.iloc[future]
            future_high = high.iloc[future]
            future_low = low.iloc[future]
            prefix = self.config.diagnostics.prefix
            result[f"{prefix}future_max_return_{window}d"] = (
                self._to_float(future_high.max()) / current_close - 1.0 if not future_high.dropna().empty else pd.NA
            )
            result[f"{prefix}future_min_return_{window}d"] = (
                self._to_float(future_low.min()) / current_close - 1.0 if not future_low.dropna().empty else pd.NA
            )
            result[f"{prefix}future_close_return_{window}d"] = (
                self._to_float(future_close.iloc[-1]) / current_close - 1.0 if len(future_close.dropna()) >= window else pd.NA
            )
        return result

    @staticmethod
    def _to_float(value: Any) -> float:
        if pd.isna(value):
            return float("nan")
        return float(value)


__all__ = [
    "BASE_COLUMNS",
    "DiagnosticsConfig",
    "PullbackConfig",
    "PullbackPatternConfig",
    "PullbackPatternMiner",
]
