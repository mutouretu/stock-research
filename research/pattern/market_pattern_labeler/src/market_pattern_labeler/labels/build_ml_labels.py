from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from market_pattern_labeler.data.daily_loader import iter_daily_frames


BASE_LABEL_COLUMNS = [
    "sample_id",
    "ts_code",
    "asof_date",
    "label",
    "label_source",
    "confidence",
    "pattern_type",
    "source_miner",
    "candidate_score",
    "split",
]

PASSTHROUGH_COLUMNS = [
    "miner_name",
    "pattern_stage",
    "window",
    "prior_drawdown_pct",
    "base_duration_bars",
    "support_touch_count",
    "neckline_price",
    "breakout_distance_pct",
    "breakout_recency_bars",
    "right_side_duration_bars",
    "volume_ratio_20",
    "monthly_trend_months",
    "monthly_trend_return_pct",
    "monthly_trend_ma_slope_pct",
    "monthly_close_vs_ma_pct",
    "rule_flags",
]

NEGATIVE_SOURCE_SPECS = {
    "random_non_event": 0.60,
    "downtrend_continuation": 0.70,
    "weak_base_non_breakout": 0.65,
}


@dataclass
class BuildMLLabelsSummary:
    positive_samples: int
    negative_samples: int
    total_samples: int
    requested_negative_samples: int
    output_csv: Path
    report_path: Path
    label_distribution: dict[Any, int]
    split_distribution: dict[str, int]
    label_source_distribution: dict[str, int]
    daily_date_range: tuple[str | None, str | None]
    labels_date_range: tuple[str | None, str | None]
    labels_outside_daily_range: int
    warnings: list[str] = field(default_factory=list)

    def summary_text(self) -> str:
        return "\n".join(
            [
                f"positive_samples={self.positive_samples}",
                f"negative_samples={self.negative_samples}",
                f"total_samples={self.total_samples}",
                f"requested_negative_samples={self.requested_negative_samples}",
                f"label_distribution={self.label_distribution}",
                f"split_distribution={self.split_distribution}",
                f"label_source_distribution={self.label_source_distribution}",
                f"daily_date_range={self.daily_date_range[0] or 'N/A'} to {self.daily_date_range[1] or 'N/A'}",
                f"labels_date_range={self.labels_date_range[0] or 'N/A'} to {self.labels_date_range[1] or 'N/A'}",
                f"labels_outside_daily_range={self.labels_outside_daily_range}",
                f"output_csv={self.output_csv}",
                f"report_path={self.report_path}",
                f"warnings={len(self.warnings)}",
            ]
        )


class NegativeAcceptance:
    def __init__(
        self,
        *,
        positive_dates_by_symbol: dict[str, list[pd.Timestamp]],
        positive_exclusion_days: int,
        max_negative_per_symbol: int,
        min_negative_separation_days: int = 20,
        min_asof_date: str | pd.Timestamp | None = None,
    ):
        self.positive_dates_by_symbol = positive_dates_by_symbol
        self.positive_exclusion = pd.Timedelta(days=max(0, int(positive_exclusion_days)))
        self.max_negative_per_symbol = max(1, int(max_negative_per_symbol))
        self.min_negative_separation = pd.Timedelta(days=max(0, int(min_negative_separation_days)))
        self.min_asof_date = _optional_timestamp(min_asof_date)
        self.selected_keys: set[tuple[str, str]] = set()
        self.selected_dates_by_symbol: dict[str, list[pd.Timestamp]] = {}

    def accept(self, ts_code: str, asof_date: pd.Timestamp) -> bool:
        symbol = str(ts_code).upper()
        date = pd.Timestamp(asof_date).normalize()
        if self.min_asof_date is not None and date < self.min_asof_date:
            return False
        key = (symbol, date.strftime("%Y-%m-%d"))
        if key in self.selected_keys:
            return False
        selected_dates = self.selected_dates_by_symbol.setdefault(symbol, [])
        if len(selected_dates) >= self.max_negative_per_symbol:
            return False
        for positive_date in self.positive_dates_by_symbol.get(symbol, []):
            if abs(date - positive_date) <= self.positive_exclusion:
                return False
        for selected_date in selected_dates:
            if abs(date - selected_date) < self.min_negative_separation:
                return False
        self.selected_keys.add(key)
        selected_dates.append(date)
        return True


def load_positive_candidates(path: str | Path) -> pd.DataFrame:
    candidate_path = Path(path)
    if not candidate_path.exists():
        raise FileNotFoundError(f"positive candidates CSV not found: {candidate_path}")
    candidates = pd.read_csv(candidate_path)
    if candidates.empty:
        raise ValueError(f"positive candidates CSV is empty: {candidate_path}")
    return candidates


def build_positive_labels(candidates: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    required = ["ts_code", "asof_date"]
    missing_required = [col for col in required if col not in candidates.columns]
    if missing_required:
        raise ValueError("positive candidates missing required columns: " + ", ".join(missing_required))

    for col in ["candidate_score", "miner_name", "pattern_stage", "confidence"]:
        if col not in candidates.columns:
            warnings.append(f"positive candidates missing optional column: {col}")

    out = candidates.copy()
    out["ts_code"] = out["ts_code"].astype(str).str.upper().str.strip()
    out["asof_date"] = pd.to_datetime(out["asof_date"], errors="coerce")
    bad_dates = int(out["asof_date"].isna().sum())
    if bad_dates:
        warnings.append(f"drop positive rows with invalid asof_date: {bad_dates}")
    out = out.dropna(subset=["ts_code", "asof_date"]).copy()
    out = out[out["ts_code"] != ""].copy()

    if "candidate_score" in out.columns:
        out["candidate_score"] = pd.to_numeric(out["candidate_score"], errors="coerce")
    else:
        out["candidate_score"] = pd.NA
    if "confidence" in out.columns:
        out["confidence"] = pd.to_numeric(out["confidence"], errors="coerce").fillna(0.70)
    else:
        out["confidence"] = 0.70
    out["label"] = 1
    out["label_source"] = "rule_long_base_breakout"
    out["pattern_type"] = "long_base_breakout"
    out["source_miner"] = "long_base_breakout"
    out["asof_date"] = out["asof_date"].dt.strftime("%Y-%m-%d")

    out = out.sort_values("candidate_score", ascending=False, na_position="last")
    before_dedupe = len(out)
    out = out.drop_duplicates(["ts_code", "asof_date", "pattern_type"], keep="first").copy()
    if len(out) < before_dedupe:
        warnings.append(f"deduped positive samples: {before_dedupe - len(out)}")

    out["sample_id"] = out["ts_code"] + "_" + out["asof_date"] + "_long_base_breakout_pos"
    for col in BASE_LABEL_COLUMNS + PASSTHROUGH_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    return out[BASE_LABEL_COLUMNS + PASSTHROUGH_COLUMNS], warnings


def load_daily_index(data_dir: str | Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    base = Path(data_dir)
    if not base.exists():
        raise FileNotFoundError(f"daily data directory not found: {base}")

    warnings: list[str] = []
    daily_by_symbol: dict[str, pd.DataFrame] = {}
    for ts_code, df in iter_daily_frames(base):
        symbol = str(ts_code).upper().strip()
        if not symbol:
            continue
        prepared = df.copy()
        prepared["trade_date"] = pd.to_datetime(prepared["trade_date"], errors="coerce")
        prepared["close"] = pd.to_numeric(prepared["close"], errors="coerce")
        prepared = prepared.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)
        if len(prepared) < 120:
            warnings.append(f"skip {symbol}: insufficient daily rows={len(prepared)}")
            continue
        daily_by_symbol[symbol] = prepared
    if not daily_by_symbol:
        raise FileNotFoundError(f"no usable daily parquet files found in {base}")
    return daily_by_symbol, warnings


def sample_random_non_events(
    *,
    daily_by_symbol: dict[str, pd.DataFrame],
    target_count: int,
    acceptance: NegativeAcceptance,
    rng: np.random.Generator,
    max_attempts: int | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    symbols = [symbol for symbol, df in daily_by_symbol.items() if len(df) >= 505]
    if not symbols or target_count <= 0:
        return _negative_frame(rows), warnings

    attempts = 0
    max_attempts = max_attempts or max(5000, int(target_count) * 80)
    while len(rows) < target_count and attempts < max_attempts:
        attempts += 1
        symbol = str(rng.choice(symbols))
        df = daily_by_symbol[symbol]
        idx = int(rng.integers(504, len(df)))
        date = pd.Timestamp(df.loc[idx, "trade_date"])
        if not acceptance.accept(symbol, date):
            continue
        rows.append(_negative_row(symbol, date, "random_non_event", NEGATIVE_SOURCE_SPECS["random_non_event"]))
    if len(rows) < target_count:
        warnings.append(f"random_non_event shortfall: requested={target_count}, generated={len(rows)}")
    return _negative_frame(rows), warnings


def sample_downtrend_continuation(
    *,
    daily_by_symbol: dict[str, pd.DataFrame],
    target_count: int,
    acceptance: NegativeAcceptance,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, list[str]]:
    pool = _downtrend_candidate_pool(daily_by_symbol, rng, per_symbol_limit=max(20, target_count // 20 + 5))
    return _sample_negative_pool(
        pool=pool,
        target_count=target_count,
        acceptance=acceptance,
        rng=rng,
        label_source="downtrend_continuation",
        confidence=NEGATIVE_SOURCE_SPECS["downtrend_continuation"],
    )


def sample_weak_base_non_breakout(
    *,
    daily_by_symbol: dict[str, pd.DataFrame],
    target_count: int,
    acceptance: NegativeAcceptance,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, list[str]]:
    pool = _weak_base_candidate_pool(daily_by_symbol, rng, per_symbol_limit=max(20, target_count // 20 + 5))
    return _sample_negative_pool(
        pool=pool,
        target_count=target_count,
        acceptance=acceptance,
        rng=rng,
        label_source="weak_base_non_breakout",
        confidence=NEGATIVE_SOURCE_SPECS["weak_base_non_breakout"],
    )


def assign_time_split(labels: pd.DataFrame, train_end: str, valid_end: str) -> pd.DataFrame:
    out = labels.copy()
    dates = pd.to_datetime(out["asof_date"], errors="coerce")
    train_end_ts = pd.Timestamp(train_end)
    valid_end_ts = pd.Timestamp(valid_end)
    out["split"] = np.where(dates <= train_end_ts, "train", np.where(dates <= valid_end_ts, "valid", "test"))
    return out


def build_ml_labels(
    *,
    positive_candidates: str | Path = "outputs/w_bottom/candidates/us_long_base_breakout_candidates.csv",
    data_dir: str | Path = "../shared_data/us/raw/daily/parquet_by_symbol",
    output: str | Path = "outputs/w_bottom/labels/labels_long_base_breakout.csv",
    report: str | Path | None = None,
    negative_ratio: int | float = 3,
    positive_exclusion_days: int = 60,
    max_negative_per_symbol: int = 50,
    train_end: str = "2022-12-31",
    valid_end: str = "2024-12-31",
    min_asof_date: str | None = None,
    random_seed: int = 42,
) -> BuildMLLabelsSummary:
    warnings: list[str] = []
    candidates = load_positive_candidates(positive_candidates)
    positives, positive_warnings = build_positive_labels(candidates)
    warnings.extend(positive_warnings)
    daily_by_symbol, daily_warnings = load_daily_index(data_dir)
    warnings.extend(daily_warnings)
    daily_range = _daily_date_range(daily_by_symbol)
    positives, filter_warnings = _filter_labels_for_data_availability(
        positives,
        daily_by_symbol=daily_by_symbol,
        min_asof_date=min_asof_date,
        label_name="positive",
    )
    warnings.extend(filter_warnings)
    if positives.empty:
        raise ValueError("no positive labels remain after date/data availability filtering")

    positive_dates_by_symbol = _positive_dates_by_symbol(positives)
    acceptance = NegativeAcceptance(
        positive_dates_by_symbol=positive_dates_by_symbol,
        positive_exclusion_days=positive_exclusion_days,
        max_negative_per_symbol=max_negative_per_symbol,
        min_asof_date=min_asof_date,
    )
    rng = np.random.default_rng(int(random_seed))

    positive_count = len(positives)
    requested_negative_count = int(round(positive_count * float(negative_ratio)))
    per_source_targets = _split_negative_targets(requested_negative_count)

    negative_frames: list[pd.DataFrame] = []
    for source, target in per_source_targets.items():
        frame, source_warnings = _sample_negative_source(
            source=source,
            target=target,
            daily_by_symbol=daily_by_symbol,
            acceptance=acceptance,
            rng=rng,
        )
        negative_frames.append(frame)
        warnings.extend(source_warnings)

    negatives = _concat_frames(negative_frames)
    if len(negatives) < requested_negative_count:
        shortfall = requested_negative_count - len(negatives)
        warnings.append(f"initial negative shortfall={shortfall}; attempting supplemental sampling")
        supplements: list[pd.DataFrame] = []
        for source in ["random_non_event", "downtrend_continuation", "weak_base_non_breakout"]:
            if len(negatives) + sum(len(frame) for frame in supplements) >= requested_negative_count:
                break
            target = requested_negative_count - len(negatives) - sum(len(frame) for frame in supplements)
            frame, source_warnings = _sample_negative_source(
                source=source,
                target=target,
                daily_by_symbol=daily_by_symbol,
                acceptance=acceptance,
                rng=rng,
            )
            supplements.append(frame)
            warnings.extend(source_warnings)
        negatives = _concat_frames([negatives, *supplements])

    if len(negatives) > requested_negative_count:
        negatives = negatives.sample(n=requested_negative_count, random_state=int(random_seed)).reset_index(drop=True)
    if len(negatives) < requested_negative_count:
        warnings.append(f"final negative shortfall={requested_negative_count - len(negatives)}")

    labels = _concat_frames([positives, negatives])
    labels = labels.drop_duplicates(["ts_code", "asof_date", "pattern_type", "label_source"], keep="first")
    labels, availability_warnings = _filter_labels_for_data_availability(
        labels,
        daily_by_symbol=daily_by_symbol,
        min_asof_date=min_asof_date,
        label_name="label",
    )
    warnings.extend(availability_warnings)
    labels = assign_time_split(labels, train_end=train_end, valid_end=valid_end)
    labels = _finalize_columns(labels)
    validation = _validate_label_date_ranges(labels, daily_by_symbol=daily_by_symbol)
    warnings.extend(validation["warnings"])

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    labels.to_csv(output_path, index=False)

    report_path = Path(report) if report else output_path.with_name(output_path.stem + "_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _build_report(
            labels=labels,
            positive_candidates=Path(positive_candidates),
            data_dir=Path(data_dir),
            output=output_path,
            requested_negative_count=requested_negative_count,
            negative_ratio=float(negative_ratio),
            min_asof_date=min_asof_date,
            daily_range=daily_range,
            validation=validation,
            warnings=warnings,
        ),
        encoding="utf-8",
    )

    return BuildMLLabelsSummary(
        positive_samples=int((labels["label"] == 1).sum()),
        negative_samples=int((labels["label"] == 0).sum()),
        total_samples=len(labels),
        requested_negative_samples=requested_negative_count,
        output_csv=output_path,
        report_path=report_path,
        label_distribution=_value_counts(labels, "label"),
        split_distribution=_value_counts(labels, "split"),
        label_source_distribution=_value_counts(labels, "label_source"),
        daily_date_range=daily_range,
        labels_date_range=(validation["labels_min_date"], validation["labels_max_date"]),
        labels_outside_daily_range=int(validation["outside_symbol_daily_range"]),
        warnings=warnings,
    )


def _sample_negative_source(
    *,
    source: str,
    target: int,
    daily_by_symbol: dict[str, pd.DataFrame],
    acceptance: NegativeAcceptance,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, list[str]]:
    if source == "random_non_event":
        return sample_random_non_events(
            daily_by_symbol=daily_by_symbol,
            target_count=target,
            acceptance=acceptance,
            rng=rng,
        )
    if source == "downtrend_continuation":
        return sample_downtrend_continuation(
            daily_by_symbol=daily_by_symbol,
            target_count=target,
            acceptance=acceptance,
            rng=rng,
        )
    if source == "weak_base_non_breakout":
        return sample_weak_base_non_breakout(
            daily_by_symbol=daily_by_symbol,
            target_count=target,
            acceptance=acceptance,
            rng=rng,
        )
    raise ValueError(f"unsupported negative source: {source}")


def _split_negative_targets(total: int) -> dict[str, int]:
    sources = list(NEGATIVE_SOURCE_SPECS)
    base = total // len(sources)
    remainder = total % len(sources)
    return {source: base + (1 if idx < remainder else 0) for idx, source in enumerate(sources)}


def _positive_dates_by_symbol(positives: pd.DataFrame) -> dict[str, list[pd.Timestamp]]:
    grouped: dict[str, list[pd.Timestamp]] = {}
    for symbol, group in positives.groupby("ts_code"):
        dates = pd.to_datetime(group["asof_date"], errors="coerce").dropna()
        grouped[str(symbol).upper()] = [pd.Timestamp(date).normalize() for date in dates]
    return grouped


def _optional_timestamp(value: str | pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None or str(value).strip() == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"invalid date: {value}")
    return pd.Timestamp(parsed).normalize()


def _daily_date_range(daily_by_symbol: dict[str, pd.DataFrame]) -> tuple[str | None, str | None]:
    mins: list[pd.Timestamp] = []
    maxes: list[pd.Timestamp] = []
    for df in daily_by_symbol.values():
        dates = pd.to_datetime(df["trade_date"], errors="coerce").dropna()
        if dates.empty:
            continue
        mins.append(pd.Timestamp(dates.min()).normalize())
        maxes.append(pd.Timestamp(dates.max()).normalize())
    if not mins or not maxes:
        return None, None
    return min(mins).strftime("%Y-%m-%d"), max(maxes).strftime("%Y-%m-%d")


def _symbol_date_ranges(daily_by_symbol: dict[str, pd.DataFrame]) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    ranges: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for symbol, df in daily_by_symbol.items():
        dates = pd.to_datetime(df["trade_date"], errors="coerce").dropna()
        if dates.empty:
            continue
        ranges[str(symbol).upper()] = (
            pd.Timestamp(dates.min()).normalize(),
            pd.Timestamp(dates.max()).normalize(),
        )
    return ranges


def _filter_labels_for_data_availability(
    labels: pd.DataFrame,
    *,
    daily_by_symbol: dict[str, pd.DataFrame],
    min_asof_date: str | pd.Timestamp | None,
    label_name: str,
) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    if labels.empty:
        return labels.copy(), warnings

    out = labels.copy()
    out["ts_code"] = out["ts_code"].astype(str).str.upper().str.strip()
    dates = pd.to_datetime(out["asof_date"], errors="coerce")
    keep = dates.notna()
    dropped_bad_dates = int((~keep).sum())
    if dropped_bad_dates:
        warnings.append(f"drop {label_name} rows with invalid asof_date: {dropped_bad_dates}")

    min_date = _optional_timestamp(min_asof_date)
    if min_date is not None:
        before_min = keep & (dates.dt.normalize() < min_date)
        count = int(before_min.sum())
        if count:
            warnings.append(f"drop {label_name} rows before min_asof_date={min_date.strftime('%Y-%m-%d')}: {count}")
        keep &= ~before_min

    ranges = _symbol_date_ranges(daily_by_symbol)
    missing_symbol = 0
    outside_symbol_range = 0
    for idx, row in out.iterrows():
        if not keep.loc[idx]:
            continue
        symbol = str(row["ts_code"]).upper()
        date = pd.Timestamp(dates.loc[idx]).normalize()
        if symbol not in ranges:
            keep.loc[idx] = False
            missing_symbol += 1
            continue
        start, end = ranges[symbol]
        if date < start or date > end:
            keep.loc[idx] = False
            outside_symbol_range += 1
    if missing_symbol:
        warnings.append(f"drop {label_name} rows with no matching daily parquet symbol: {missing_symbol}")
    if outside_symbol_range:
        warnings.append(f"drop {label_name} rows outside symbol daily date range: {outside_symbol_range}")

    out = out.loc[keep].copy()
    out["asof_date"] = pd.to_datetime(out["asof_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return out, warnings


def _validate_label_date_ranges(
    labels: pd.DataFrame,
    *,
    daily_by_symbol: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    warnings: list[str] = []
    daily_min, daily_max = _daily_date_range(daily_by_symbol)
    label_dates = pd.to_datetime(labels["asof_date"], errors="coerce") if not labels.empty else pd.Series(dtype="datetime64[ns]")
    labels_min = pd.Timestamp(label_dates.min()).strftime("%Y-%m-%d") if not label_dates.dropna().empty else None
    labels_max = pd.Timestamp(label_dates.max()).strftime("%Y-%m-%d") if not label_dates.dropna().empty else None
    outside_global = 0
    if daily_min is not None and daily_max is not None and not label_dates.dropna().empty:
        outside_global = int(((label_dates < pd.Timestamp(daily_min)) | (label_dates > pd.Timestamp(daily_max))).sum())
    ranges = _symbol_date_ranges(daily_by_symbol)
    outside_symbol = 0
    missing_symbol = 0
    for _, row in labels.iterrows():
        symbol = str(row["ts_code"]).upper()
        date = pd.to_datetime(row["asof_date"], errors="coerce")
        if pd.isna(date):
            outside_symbol += 1
            continue
        if symbol not in ranges:
            missing_symbol += 1
            continue
        start, end = ranges[symbol]
        if pd.Timestamp(date).normalize() < start or pd.Timestamp(date).normalize() > end:
            outside_symbol += 1
    if outside_global:
        warnings.append(f"labels outside global daily date range: {outside_global}")
    if missing_symbol:
        warnings.append(f"labels with no matching daily parquet symbol: {missing_symbol}")
    if outside_symbol:
        warnings.append(f"labels outside symbol daily date range: {outside_symbol}")
    return {
        "daily_min_date": daily_min,
        "daily_max_date": daily_max,
        "labels_min_date": labels_min,
        "labels_max_date": labels_max,
        "outside_global_daily_range": outside_global,
        "missing_daily_symbol": missing_symbol,
        "outside_symbol_daily_range": outside_symbol,
        "warnings": warnings,
    }


def _downtrend_candidate_pool(
    daily_by_symbol: dict[str, pd.DataFrame],
    rng: np.random.Generator,
    per_symbol_limit: int,
) -> list[tuple[str, pd.Timestamp]]:
    pool: list[tuple[str, pd.Timestamp]] = []
    for symbol, df in daily_by_symbol.items():
        if len(df) < 253:
            continue
        close = pd.to_numeric(df["close"], errors="coerce")
        ma60 = close.rolling(60).mean()
        ma120 = close.rolling(120).mean()
        ma60_slope = ma60 - ma60.shift(20)
        ret120 = close / close.shift(120) - 1.0
        prior_60_high = close.rolling(60).max().shift(1)
        mask = (
            (close.index >= 252)
            & (close < ma60)
            & ((ma60 < ma120) | (ma60_slope < 0))
            & (ret120 < -0.15)
            & (close < prior_60_high)
        )
        pool.extend(_sample_symbol_dates(symbol, df, mask, rng, per_symbol_limit))
    return pool


def _weak_base_candidate_pool(
    daily_by_symbol: dict[str, pd.DataFrame],
    rng: np.random.Generator,
    per_symbol_limit: int,
) -> list[tuple[str, pd.Timestamp]]:
    pool: list[tuple[str, pd.Timestamp]] = []
    for symbol, df in daily_by_symbol.items():
        if len(df) < 505:
            continue
        close = pd.to_numeric(df["close"], errors="coerce")
        prior_high = close.rolling(252).max().shift(1)
        prior_low = close.rolling(252).min().shift(1)
        prior_drawdown = (prior_high - prior_low) / prior_high
        base_std = close.rolling(120).std() / close.rolling(120).mean()
        base_range = (close.rolling(120).max() - close.rolling(120).min()) / close.rolling(120).mean()
        resistance = close.rolling(120).max().shift(1)
        mask = (
            (close.index >= 504)
            & (prior_drawdown >= 0.15)
            & ((base_std <= 0.12) | (base_range <= 0.35))
            & (close <= resistance * 0.97)
            & (close >= prior_low * 1.05)
        )
        pool.extend(_sample_symbol_dates(symbol, df, mask, rng, per_symbol_limit))
    return pool


def _sample_symbol_dates(
    symbol: str,
    df: pd.DataFrame,
    mask: pd.Series | np.ndarray,
    rng: np.random.Generator,
    per_symbol_limit: int,
) -> list[tuple[str, pd.Timestamp]]:
    mask_series = pd.Series(mask, index=df.index).fillna(False)
    indices = mask_series.index[mask_series.astype(bool)].to_numpy()
    if len(indices) == 0:
        return []
    take = min(len(indices), max(1, int(per_symbol_limit)))
    selected = rng.choice(indices, size=take, replace=False)
    return [(symbol, pd.Timestamp(df.loc[int(idx), "trade_date"])) for idx in selected]


def _sample_negative_pool(
    *,
    pool: list[tuple[str, pd.Timestamp]],
    target_count: int,
    acceptance: NegativeAcceptance,
    rng: np.random.Generator,
    label_source: str,
    confidence: float,
) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    if target_count <= 0:
        return _negative_frame(rows), warnings
    if not pool:
        warnings.append(f"{label_source} shortfall: requested={target_count}, generated=0")
        return _negative_frame(rows), warnings

    order = rng.permutation(len(pool))
    for pos in order:
        symbol, date = pool[int(pos)]
        if not acceptance.accept(symbol, date):
            continue
        rows.append(_negative_row(symbol, date, label_source, confidence))
        if len(rows) >= target_count:
            break
    if len(rows) < target_count:
        warnings.append(f"{label_source} shortfall: requested={target_count}, generated={len(rows)}")
    return _negative_frame(rows), warnings


def _negative_row(ts_code: str, asof_date: pd.Timestamp, label_source: str, confidence: float) -> dict[str, Any]:
    date_text = pd.Timestamp(asof_date).strftime("%Y-%m-%d")
    return {
        "sample_id": f"{str(ts_code).upper()}_{date_text}_{label_source}_neg",
        "ts_code": str(ts_code).upper(),
        "asof_date": date_text,
        "label": 0,
        "label_source": label_source,
        "confidence": confidence,
        "pattern_type": "negative",
        "source_miner": "negative_sampler",
        "candidate_score": 0.0,
    }


def _negative_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for col in BASE_LABEL_COLUMNS + PASSTHROUGH_COLUMNS:
        if col not in frame.columns:
            frame[col] = pd.NA
    return frame[BASE_LABEL_COLUMNS + PASSTHROUGH_COLUMNS]


def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    valid = [frame for frame in frames if frame is not None and not frame.empty]
    if not valid:
        return pd.DataFrame(columns=BASE_LABEL_COLUMNS + PASSTHROUGH_COLUMNS)
    return pd.concat(valid, ignore_index=True)


def _finalize_columns(labels: pd.DataFrame) -> pd.DataFrame:
    out = labels.copy()
    for col in BASE_LABEL_COLUMNS + PASSTHROUGH_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    out["asof_date"] = pd.to_datetime(out["asof_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["label"] = pd.to_numeric(out["label"], errors="coerce").fillna(0).astype(int)
    out["confidence"] = pd.to_numeric(out["confidence"], errors="coerce")
    out["candidate_score"] = pd.to_numeric(out["candidate_score"], errors="coerce")
    return out[BASE_LABEL_COLUMNS + PASSTHROUGH_COLUMNS].sort_values(
        ["asof_date", "label", "ts_code", "label_source"],
        ascending=[True, False, True, True],
    ).reset_index(drop=True)


def _build_report(
    *,
    labels: pd.DataFrame,
    positive_candidates: Path,
    data_dir: Path,
    output: Path,
    requested_negative_count: int,
    negative_ratio: float,
    min_asof_date: str | None,
    daily_range: tuple[str | None, str | None],
    validation: dict[str, Any],
    warnings: list[str],
) -> str:
    positive_count = int((labels["label"] == 1).sum())
    negative_count = int((labels["label"] == 0).sum())
    lines = [
        "# ML Labels Report",
        "",
        "## Inputs",
        f"- positive_candidates: `{positive_candidates}`",
        f"- data_dir: `{data_dir}`",
        f"- output: `{output}`",
        "",
        "## Summary",
        f"- positive samples: {positive_count}",
        f"- negative samples: {negative_count}",
        f"- total samples: {len(labels)}",
        f"- requested negative samples: {requested_negative_count}",
        f"- negative_ratio: {negative_ratio:g}",
        f"- min_asof_date: {min_asof_date or 'none'}",
        "",
        "## Data Availability Validation",
        f"- daily parquet date range: {daily_range[0] or 'N/A'} to {daily_range[1] or 'N/A'}",
        f"- labels date range: {validation['labels_min_date'] or 'N/A'} to {validation['labels_max_date'] or 'N/A'}",
        f"- labels outside global daily date range: {validation['outside_global_daily_range']}",
        f"- labels missing daily parquet symbol: {validation['missing_daily_symbol']}",
        f"- labels outside symbol daily date range: {validation['outside_symbol_daily_range']}",
        f"- availability_status: {'ok' if validation['outside_symbol_daily_range'] == 0 and validation['missing_daily_symbol'] == 0 and validation['outside_global_daily_range'] == 0 else 'warning'}",
        "",
        "## Label Distribution",
        _series_to_markdown(labels["label"].value_counts().sort_index()),
        "",
        "## Label Source Distribution",
        _series_to_markdown(labels["label_source"].value_counts()),
        "",
        "## Split Distribution",
        _series_to_markdown(labels["split"].value_counts()),
        "",
        "## Label x Split",
        _frame_to_markdown(pd.crosstab(labels["label"], labels["split"])),
        "",
        "## Label Source x Split",
        _frame_to_markdown(pd.crosstab(labels["label_source"], labels["split"])),
        "",
        "## Year Distribution",
        _series_to_markdown(pd.to_datetime(labels["asof_date"], errors="coerce").dt.year.value_counts().sort_index()),
        "",
        "## Top Symbols By Sample Count",
        _series_to_markdown(labels["ts_code"].value_counts().head(20)),
        "",
        "## Warnings",
    ]
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _series_to_markdown(series: pd.Series) -> str:
    if series.empty:
        return "_none_"
    frame = series.rename("count").reset_index()
    frame.columns = ["value", "count"]
    return _frame_to_markdown(frame)


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_none_"
    out = frame.copy()
    if not isinstance(out.index, pd.RangeIndex):
        out = out.reset_index()
    columns = [str(col) for col in out.columns]
    rows = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in out.iterrows():
        rows.append("| " + " | ".join(_markdown_cell(row[col]) for col in out.columns) + " |")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _value_counts(frame: pd.DataFrame, column: str) -> dict[Any, int]:
    if column not in frame.columns or frame.empty:
        return {}
    return frame[column].value_counts().to_dict()


__all__ = [
    "BuildMLLabelsSummary",
    "assign_time_split",
    "build_ml_labels",
    "build_positive_labels",
    "load_daily_index",
    "load_positive_candidates",
    "sample_downtrend_continuation",
    "sample_random_non_events",
    "sample_weak_base_non_breakout",
]
