from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from research_data_core.paths import get_shared_data_dir

from src.reviewers.common.overhang import (
    build_volume_weighted_price_histogram,
    compute_overhang_factor,
    compute_overhang_ratio,
)
from src.reviewers.common.scoring import sigmoid_boost_factor, sigmoid_decay_factor, sigmoid_rise_factor
from src.reviewers.type_n.phase2_pullback.chip_structure_reviewer import load_chip_structure_values
from src.reviewers.type_n.phase2_pullback.trend_reviewer import load_midlong_trend_values

KEY_COLUMNS = ["sample_id", "ts_code", "asof_date"]


def _resolve_path(project_root: Path, path: str | Path) -> Path:
    p = Path(path).expanduser()
    if p.is_absolute():
        return p

    candidate = project_root / p
    if candidate.exists():
        return candidate

    parts = p.parts
    if "shared_data" in parts:
        shared_data_index = parts.index("shared_data")
        suffix = Path(*parts[shared_data_index + 1 :]) if shared_data_index + 1 < len(parts) else Path()
        return get_shared_data_dir() / suffix

    return candidate


def _apply_factor_weight(factor: pd.Series, weight: float) -> pd.Series:
    """Interpolate a multiplicative factor toward neutral 1.0 by weight."""
    numeric_factor = pd.to_numeric(factor, errors="coerce")
    return 1.0 + float(weight) * (numeric_factor - 1.0)


def _load_runup_values(
    rows: pd.DataFrame,
    *,
    raw_data_dir: Path,
    window: int,
) -> pd.DataFrame:
    runup_rows: List[Dict[str, Any]] = []
    for ts_code, group in rows[KEY_COLUMNS].drop_duplicates().groupby("ts_code"):
        path = raw_data_dir / f"{ts_code}.parquet"
        runup_by_date: Dict[str, float] = {}
        if path.exists():
            daily = pd.read_parquet(path, columns=["trade_date", "close"]).copy()
            daily["trade_date"] = pd.to_datetime(daily["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
            daily = daily.dropna(subset=["trade_date"]).sort_values("trade_date")
            close = pd.to_numeric(daily["close"], errors="coerce")
            rolling_low = close.rolling(window, min_periods=window).min().replace(0, float("nan"))
            daily["runup"] = close / rolling_low - 1.0
            runup_by_date = daily.set_index("trade_date")["runup"].to_dict()
        for _, row in group.iterrows():
            runup_rows.append(
                {
                    "sample_id": row["sample_id"],
                    "ts_code": row["ts_code"],
                    "asof_date": row["asof_date"],
                    "runup_value": runup_by_date.get(str(row["asof_date"]), pd.NA),
                }
            )
    return pd.DataFrame(runup_rows)


def _load_volume_values(
    rows: pd.DataFrame,
    *,
    raw_data_dir: Path,
    ma_window: int,
    short_window: int,
    spike_ratio: float,
) -> pd.DataFrame:
    volume_rows: List[Dict[str, Any]] = []
    for ts_code, group in rows[KEY_COLUMNS].drop_duplicates().groupby("ts_code"):
        path = raw_data_dir / f"{ts_code}.parquet"
        values_by_date: Dict[str, Dict[str, float]] = {}
        if path.exists():
            daily = pd.read_parquet(path, columns=["trade_date", "vol"]).copy()
            daily["trade_date"] = pd.to_datetime(daily["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
            daily = daily.dropna(subset=["trade_date"]).sort_values("trade_date")
            vol = pd.to_numeric(daily["vol"], errors="coerce")
            vol_base = vol.rolling(ma_window, min_periods=ma_window).mean().shift(1).replace(0, float("nan"))
            ratio_1d = vol / vol_base
            ratio_short = vol.rolling(short_window, min_periods=short_window).mean() / vol_base
            spike = ratio_1d >= spike_ratio
            streak = spike.groupby((spike != spike.shift()).cumsum()).cumcount() + 1
            streak = streak.where(spike, 0)
            daily["volume_ratio"] = ratio_short
            daily["volume_spike_streak"] = streak
            values_by_date = daily.set_index("trade_date")[["volume_ratio", "volume_spike_streak"]].to_dict("index")
        for _, row in group.iterrows():
            values = values_by_date.get(str(row["asof_date"]), {})
            volume_rows.append(
                {
                    "sample_id": row["sample_id"],
                    "ts_code": row["ts_code"],
                    "asof_date": row["asof_date"],
                    "volume_ratio": values.get("volume_ratio", pd.NA),
                    "volume_spike_streak": values.get("volume_spike_streak", pd.NA),
                }
            )
    return pd.DataFrame(volume_rows)


def _load_burst_strength_values(
    rows: pd.DataFrame,
    *,
    raw_data_dir: Path,
    volume_window: int,
    recent_high_window: int,
) -> pd.DataFrame:
    burst_rows: List[Dict[str, Any]] = []
    for ts_code, group in rows[KEY_COLUMNS].drop_duplicates().groupby("ts_code"):
        path = raw_data_dir / f"{ts_code}.parquet"
        values_by_date: Dict[str, Dict[str, float]] = {}
        if path.exists():
            daily = pd.read_parquet(path, columns=["trade_date", "high", "low", "close", "vol", "amount"]).copy()
            daily["trade_date"] = pd.to_datetime(daily["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
            daily = daily.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
            high = pd.to_numeric(daily["high"], errors="coerce")
            low = pd.to_numeric(daily["low"], errors="coerce")
            close = pd.to_numeric(daily["close"], errors="coerce")
            vol = pd.to_numeric(daily["vol"], errors="coerce")
            amount = pd.to_numeric(daily["amount"], errors="coerce")
            vol_base = vol.rolling(volume_window, min_periods=volume_window).mean().shift(1).replace(0, float("nan"))
            amount_base = amount.rolling(volume_window, min_periods=volume_window).mean().shift(1).replace(0, float("nan"))
            recent_high = high.shift(1).rolling(recent_high_window, min_periods=1).max().replace(0, float("nan"))
            daily["burst_ret_1d"] = close / close.shift(1).replace(0, float("nan")) - 1.0
            daily["burst_ret_2d"] = close / close.shift(2).replace(0, float("nan")) - 1.0
            daily["burst_volume_ratio_1d"] = vol / vol_base
            daily["burst_volume_ratio_2d"] = vol.rolling(2, min_periods=2).mean() / vol_base
            daily["burst_amount_ratio_1d"] = amount / amount_base
            daily["burst_amount_ratio_2d"] = amount.rolling(2, min_periods=2).mean() / amount_base
            daily["burst_recent_high"] = recent_high
            daily["burst_breakout_pct"] = close / recent_high - 1.0
            daily["burst_close_position"] = (close - low) / (high - low).replace(0, float("nan"))
            values_by_date = daily.set_index("trade_date")[
                [
                    "burst_ret_1d",
                    "burst_ret_2d",
                    "burst_volume_ratio_1d",
                    "burst_volume_ratio_2d",
                    "burst_amount_ratio_1d",
                    "burst_amount_ratio_2d",
                    "burst_recent_high",
                    "burst_breakout_pct",
                    "burst_close_position",
                ]
            ].to_dict("index")
        for _, row in group.iterrows():
            values = values_by_date.get(str(row["asof_date"]), {})
            burst_rows.append(
                {
                    "sample_id": row["sample_id"],
                    "ts_code": row["ts_code"],
                    "asof_date": row["asof_date"],
                    **{key: values.get(key, pd.NA) for key in [
                        "burst_ret_1d",
                        "burst_ret_2d",
                        "burst_volume_ratio_1d",
                        "burst_volume_ratio_2d",
                        "burst_amount_ratio_1d",
                        "burst_amount_ratio_2d",
                        "burst_recent_high",
                        "burst_breakout_pct",
                        "burst_close_position",
                    ]},
                }
            )
    return pd.DataFrame(burst_rows)


def _load_base_stability_values(
    rows: pd.DataFrame,
    *,
    raw_data_dir: Path,
    window: int,
    fast_ma_col: str,
    slow_ma_col: str,
    trend_ma_col: str,
    prior_lag: int,
    recent_weight: float,
    prior_weight: float,
) -> pd.DataFrame:
    stability_rows: List[Dict[str, Any]] = []
    parquet_columns = list(dict.fromkeys(["trade_date", fast_ma_col, slow_ma_col, trend_ma_col]))
    for ts_code, group in rows[KEY_COLUMNS].drop_duplicates().groupby("ts_code"):
        path = raw_data_dir / f"{ts_code}.parquet"
        values_by_date: Dict[str, Dict[str, float]] = {}
        if path.exists():
            daily = pd.read_parquet(path, columns=parquet_columns).copy()
            daily["trade_date"] = pd.to_datetime(daily["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
            daily = daily.dropna(subset=["trade_date"]).sort_values("trade_date")
            fast_ma = pd.to_numeric(daily[fast_ma_col], errors="coerce")
            slow_ma = pd.to_numeric(daily[slow_ma_col], errors="coerce").replace(0, float("nan"))
            trend_ma = pd.to_numeric(daily[trend_ma_col], errors="coerce").replace(0, float("nan"))

            # Shift by one day so the base score describes the pre-breakout box, not the trigger day.
            ma_gap = ((fast_ma - slow_ma) / slow_ma).shift(1)
            daily["base_ma_gap_l2"] = (ma_gap.pow(2).rolling(window, min_periods=window).mean()).pow(0.5)
            daily["base_ma60_recent_slope_pct"] = trend_ma.shift(1) / trend_ma.shift(window + 1) - 1.0
            daily["base_ma60_prior_slope_pct"] = trend_ma.shift(window + 1) / trend_ma.shift(prior_lag + 1) - 1.0
            daily["base_ma60_trend_abs"] = (
                recent_weight * daily["base_ma60_recent_slope_pct"].abs()
                + prior_weight * daily["base_ma60_prior_slope_pct"].abs()
            )
            values_by_date = daily.set_index("trade_date")[
                [
                    "base_ma_gap_l2",
                    "base_ma60_recent_slope_pct",
                    "base_ma60_prior_slope_pct",
                    "base_ma60_trend_abs",
                ]
            ].to_dict("index")
        for _, row in group.iterrows():
            values = values_by_date.get(str(row["asof_date"]), {})
            stability_rows.append(
                {
                    "sample_id": row["sample_id"],
                    "ts_code": row["ts_code"],
                    "asof_date": row["asof_date"],
                    "base_ma_gap_l2": values.get("base_ma_gap_l2", pd.NA),
                    "base_ma60_recent_slope_pct": values.get("base_ma60_recent_slope_pct", pd.NA),
                    "base_ma60_prior_slope_pct": values.get("base_ma60_prior_slope_pct", pd.NA),
                    "base_ma60_trend_abs": values.get("base_ma60_trend_abs", pd.NA),
                }
            )
    return pd.DataFrame(stability_rows)


def _load_box_breakout_values(
    rows: pd.DataFrame,
    *,
    raw_data_dir: Path,
    window: int,
    high_col: str,
    close_col: str,
) -> pd.DataFrame:
    breakout_rows: List[Dict[str, Any]] = []
    for ts_code, group in rows[KEY_COLUMNS].drop_duplicates().groupby("ts_code"):
        path = raw_data_dir / f"{ts_code}.parquet"
        values_by_date: Dict[str, Dict[str, float]] = {}
        if path.exists():
            daily = pd.read_parquet(path, columns=["trade_date", high_col, close_col]).copy()
            daily["trade_date"] = pd.to_datetime(daily["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
            daily = daily.dropna(subset=["trade_date"]).sort_values("trade_date")
            high = pd.to_numeric(daily[high_col], errors="coerce")
            close = pd.to_numeric(daily[close_col], errors="coerce")
            box_high = high.shift(1).rolling(window, min_periods=window).max().replace(0, float("nan"))
            daily["box_high"] = box_high
            daily["box_breakout_pct"] = close / box_high - 1.0
            values_by_date = daily.set_index("trade_date")[["box_high", "box_breakout_pct"]].to_dict("index")
        for _, row in group.iterrows():
            values = values_by_date.get(str(row["asof_date"]), {})
            breakout_rows.append(
                {
                    "sample_id": row["sample_id"],
                    "ts_code": row["ts_code"],
                    "asof_date": row["asof_date"],
                    "box_high": values.get("box_high", pd.NA),
                    "box_breakout_pct": values.get("box_breakout_pct", pd.NA),
                }
            )
    return pd.DataFrame(breakout_rows)


def _load_overhang_values(
    rows: pd.DataFrame,
    *,
    raw_data_dir: Path,
    lookback: int,
    n_bins: int,
) -> pd.DataFrame:
    overhang_rows: List[Dict[str, Any]] = []
    for ts_code, group in rows[KEY_COLUMNS].drop_duplicates().groupby("ts_code"):
        path = raw_data_dir / f"{ts_code}.parquet"
        values_by_date: Dict[str, float] = {}
        if path.exists():
            daily = pd.read_parquet(path, columns=["trade_date", "close", "vol"]).copy()
            daily["trade_date"] = pd.to_datetime(daily["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
            daily = daily.dropna(subset=["trade_date"]).sort_values("trade_date")
            for asof_date in group["asof_date"].astype(str).unique():
                history = daily[daily["trade_date"] <= asof_date].tail(lookback)
                if history.empty:
                    values_by_date[asof_date] = 0.0
                    continue
                hist, bin_edges = build_volume_weighted_price_histogram(
                    history,
                    lookback=lookback,
                    n_bins=n_bins,
                )
                current_price = pd.to_numeric(history["close"], errors="coerce").iloc[-1]
                values_by_date[asof_date] = compute_overhang_ratio(hist, bin_edges, current_price)
        for _, row in group.iterrows():
            overhang_rows.append(
                {
                    "sample_id": row["sample_id"],
                    "ts_code": row["ts_code"],
                    "asof_date": row["asof_date"],
                    "overhang_ratio": values_by_date.get(str(row["asof_date"]), pd.NA),
                }
            )
    return pd.DataFrame(overhang_rows)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return float("nan")
    return float(numerator) / float(denominator)


def _phase2_empty_metrics(row: pd.Series) -> Dict[str, Any]:
    return {
        "sample_id": row["sample_id"],
        "ts_code": row["ts_code"],
        "asof_date": row["asof_date"],
        "phase2_anchor_date": pd.NA,
        "phase2_days_since_anchor": pd.NA,
        "phase2_pre_avg_volume": pd.NA,
        "phase2_burst_avg_volume": pd.NA,
        "phase2_pullback_avg_volume": pd.NA,
        "phase2_recent_avg_volume": pd.NA,
        "phase2_pullback_volume_vs_pre": pd.NA,
        "phase2_recent_volume_vs_pre": pd.NA,
        "phase2_pullback_volume_vs_burst": pd.NA,
        "phase2_down_volume_pressure": pd.NA,
        "phase2_anchor_high": pd.NA,
        "phase2_anchor_low": pd.NA,
        "phase2_anchor_close": pd.NA,
        "phase2_post_anchor_high": pd.NA,
        "phase2_pullback_low": pd.NA,
        "phase2_current_close": pd.NA,
        "phase2_pullback_depth_pct": pd.NA,
        "phase2_close_to_anchor_close_pct": pd.NA,
        "phase2_low_to_anchor_low_pct": pd.NA,
        "phase2_chase_extension_pct": pd.NA,
        "phase2_anchor_range_pct": pd.NA,
        "phase2_pullback_avg_range_pct": pd.NA,
        "phase2_range_contraction_ratio": pd.NA,
        "phase2_recent_range_pct": pd.NA,
    }


def _calc_phase2_metrics_for_row(
    row: pd.Series,
    daily: pd.DataFrame,
    *,
    anchor_date_col: str,
    pre_window: int,
    burst_window: int,
    pullback_window: int,
    recent_window: int,
) -> Dict[str, Any]:
    if daily.empty:
        return _phase2_empty_metrics(row)

    anchor_date = row.get(anchor_date_col, pd.NA)
    if pd.isna(anchor_date):
        for fallback_col in ["best_phase1_date", "last_phase1_date", "first_phase1_date", "anchor_date"]:
            anchor_date = row.get(fallback_col, pd.NA)
            if pd.notna(anchor_date):
                break
    if pd.isna(anchor_date):
        return _phase2_empty_metrics(row)

    asof_date = str(row["asof_date"])
    anchor_date = str(anchor_date)
    history = daily[daily["trade_date"] <= asof_date].copy()
    if history.empty:
        return _phase2_empty_metrics(row)

    anchor_positions = history.index[history["trade_date"] == anchor_date].tolist()
    if not anchor_positions:
        eligible_anchor = history[history["trade_date"] <= anchor_date]
        if eligible_anchor.empty:
            return _phase2_empty_metrics(row)
        anchor_idx = int(eligible_anchor.index[-1])
    else:
        anchor_idx = int(anchor_positions[-1])
    asof_idx = int(history.index[-1])
    if anchor_idx >= asof_idx:
        return _phase2_empty_metrics(row)

    pos_by_index = {idx: pos for pos, idx in enumerate(history.index)}
    anchor_pos = pos_by_index[anchor_idx]
    asof_pos = pos_by_index[asof_idx]

    vol = pd.to_numeric(history["vol"], errors="coerce")
    high = pd.to_numeric(history["high"], errors="coerce")
    low = pd.to_numeric(history["low"], errors="coerce")
    close = pd.to_numeric(history["close"], errors="coerce")
    prev_close = close.shift(1)
    range_pct = (high - low) / close.replace(0, float("nan"))

    pre = history.iloc[max(0, anchor_pos - pre_window) : anchor_pos]
    burst = history.iloc[anchor_pos : min(asof_pos + 1, anchor_pos + burst_window)]
    pullback = history.iloc[anchor_pos + 1 : asof_pos + 1]
    pullback_tail = pullback.tail(pullback_window)
    recent = history.iloc[max(anchor_pos + 1, asof_pos - recent_window + 1) : asof_pos + 1]

    pre_avg_volume = float(pd.to_numeric(pre["vol"], errors="coerce").mean()) if not pre.empty else float("nan")
    burst_avg_volume = float(pd.to_numeric(burst["vol"], errors="coerce").mean()) if not burst.empty else float("nan")
    pullback_avg_volume = float(pd.to_numeric(pullback_tail["vol"], errors="coerce").mean()) if not pullback_tail.empty else float("nan")
    recent_avg_volume = float(pd.to_numeric(recent["vol"], errors="coerce").mean()) if not recent.empty else float("nan")

    pullback_positions = list(pullback_tail.index)
    down_mask = close.loc[pullback_positions] < prev_close.loc[pullback_positions]
    up_mask = close.loc[pullback_positions] >= prev_close.loc[pullback_positions]
    down_avg_volume = float(vol.loc[pullback_positions][down_mask].mean()) if down_mask.any() else float("nan")
    up_avg_volume = float(vol.loc[pullback_positions][up_mask].mean()) if up_mask.any() else float("nan")

    anchor_high = float(high.loc[anchor_idx])
    anchor_low = float(low.loc[anchor_idx])
    anchor_close = float(close.loc[anchor_idx])
    current_close = float(close.loc[asof_idx])
    post_anchor = history.iloc[anchor_pos : asof_pos + 1]
    post_anchor_high = float(pd.to_numeric(post_anchor["high"], errors="coerce").max())
    pullback_low = float(pd.to_numeric(pullback["low"], errors="coerce").min()) if not pullback.empty else float("nan")
    anchor_range_pct = _safe_ratio(anchor_high - anchor_low, anchor_close)
    pullback_avg_range_pct = float(range_pct.loc[pullback_tail.index].mean()) if not pullback_tail.empty else float("nan")
    recent_high = float(pd.to_numeric(recent["high"], errors="coerce").max()) if not recent.empty else float("nan")
    recent_low = float(pd.to_numeric(recent["low"], errors="coerce").min()) if not recent.empty else float("nan")

    return {
        "sample_id": row["sample_id"],
        "ts_code": row["ts_code"],
        "asof_date": row["asof_date"],
        "phase2_anchor_date": anchor_date,
        "phase2_days_since_anchor": asof_pos - anchor_pos,
        "phase2_pre_avg_volume": pre_avg_volume,
        "phase2_burst_avg_volume": burst_avg_volume,
        "phase2_pullback_avg_volume": pullback_avg_volume,
        "phase2_recent_avg_volume": recent_avg_volume,
        "phase2_pullback_volume_vs_pre": _safe_ratio(pullback_avg_volume, pre_avg_volume),
        "phase2_recent_volume_vs_pre": _safe_ratio(recent_avg_volume, pre_avg_volume),
        "phase2_pullback_volume_vs_burst": _safe_ratio(pullback_avg_volume, burst_avg_volume),
        "phase2_down_volume_pressure": _safe_ratio(down_avg_volume, up_avg_volume),
        "phase2_anchor_high": anchor_high,
        "phase2_anchor_low": anchor_low,
        "phase2_anchor_close": anchor_close,
        "phase2_post_anchor_high": post_anchor_high,
        "phase2_pullback_low": pullback_low,
        "phase2_current_close": current_close,
        "phase2_pullback_depth_pct": 1.0 - _safe_ratio(current_close, post_anchor_high),
        "phase2_close_to_anchor_close_pct": _safe_ratio(current_close, anchor_close) - 1.0,
        "phase2_low_to_anchor_low_pct": _safe_ratio(pullback_low, anchor_low) - 1.0,
        "phase2_chase_extension_pct": _safe_ratio(current_close, anchor_high) - 1.0,
        "phase2_anchor_range_pct": anchor_range_pct,
        "phase2_pullback_avg_range_pct": pullback_avg_range_pct,
        "phase2_range_contraction_ratio": _safe_ratio(pullback_avg_range_pct, anchor_range_pct),
        "phase2_recent_range_pct": _safe_ratio(recent_high - recent_low, current_close),
    }


def _load_phase2_pullback_metrics(
    rows: pd.DataFrame,
    *,
    raw_data_dir: Path,
    anchor_date_col: str,
    pre_window: int,
    burst_window: int,
    pullback_window: int,
    recent_window: int,
) -> pd.DataFrame:
    metric_rows: List[Dict[str, Any]] = []
    for ts_code, group in rows[KEY_COLUMNS + [col for col in rows.columns if col not in KEY_COLUMNS]].drop_duplicates().groupby("ts_code"):
        path = raw_data_dir / f"{ts_code}.parquet"
        if path.exists():
            daily = pd.read_parquet(path, columns=["trade_date", "open", "high", "low", "close", "vol"]).copy()
            daily["trade_date"] = pd.to_datetime(daily["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
            daily = daily.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
        else:
            daily = pd.DataFrame()
        for _, row in group.iterrows():
            metric_rows.append(
                _calc_phase2_metrics_for_row(
                    row,
                    daily,
                    anchor_date_col=anchor_date_col,
                    pre_window=pre_window,
                    burst_window=burst_window,
                    pullback_window=pullback_window,
                    recent_window=recent_window,
                )
            )
    return pd.DataFrame(metric_rows)


def _apply_runup_post_penalty(result: pd.DataFrame, config: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    if not bool(config.get("enabled", False)):
        return result

    raw_data_dir = _resolve_path(project_root, config["raw_data_dir"])
    window = int(config.get("window", 150))
    threshold = float(config.get("threshold", 0.35))
    sharpness = float(config.get("sharpness", 20.0))
    score_col = str(config.get("score_col", "baseline_score"))
    output_score_col = str(config.get("output_score_col", "adjusted_score"))
    runup_col = str(config.get("runup_col", f"runup_{window}"))
    weight = float(config.get("weight", 1.0))

    if score_col not in result.columns:
        raise ValueError(f"Runup post penalty score_col not found: {score_col}")

    runup = _load_runup_values(result, raw_data_dir=raw_data_dir, window=window)
    out = result.merge(runup, on=KEY_COLUMNS, how="left")
    out = out.rename(columns={"runup_value": runup_col})
    out["runup_penalty_threshold"] = threshold
    out["runup_penalty_sharpness"] = sharpness
    raw_factor = sigmoid_decay_factor(out[runup_col], threshold=threshold, sharpness=sharpness)
    out["runup_penalty_factor"] = _apply_factor_weight(raw_factor, weight)
    out["runup_penalty_raw_factor"] = raw_factor
    out["runup_penalty_weight"] = weight
    out[output_score_col] = pd.to_numeric(out[score_col], errors="coerce") * out["runup_penalty_factor"]
    return out


def _apply_volume_post_penalty(result: pd.DataFrame, config: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    if not bool(config.get("enabled", False)):
        return result

    raw_data_dir = _resolve_path(project_root, config["raw_data_dir"])
    ma_window = int(config.get("ma_window", 20))
    short_window = int(config.get("short_window", 3))
    score_col = str(config.get("score_col", "adjusted_score"))
    output_score_col = str(config.get("output_score_col", score_col))

    strength_cfg = config.get("strength", {})
    if not isinstance(strength_cfg, dict):
        strength_cfg = {}
    strength_threshold = float(strength_cfg.get("threshold", 1.8))
    strength_sharpness = float(strength_cfg.get("sharpness", 3.0))
    max_boost = float(strength_cfg.get("max_boost", 0.15))

    streak_cfg = config.get("streak", {})
    if not isinstance(streak_cfg, dict):
        streak_cfg = {}
    spike_ratio = float(streak_cfg.get("spike_ratio", strength_threshold))
    streak_threshold = float(streak_cfg.get("threshold", 3.0))
    streak_sharpness = float(streak_cfg.get("sharpness", 1.5))

    ratio_col = str(config.get("ratio_col", f"volume_ratio_{short_window}d_{ma_window}"))
    streak_col = str(config.get("streak_col", "volume_spike_streak"))
    factor_col = str(config.get("factor_col", "volume_penalty_factor"))
    keep_component_factors = bool(config.get("keep_component_factors", False))
    weight = float(config.get("weight", 1.0))

    if score_col not in result.columns:
        raise ValueError(f"Volume post penalty score_col not found: {score_col}")

    volume = _load_volume_values(
        result,
        raw_data_dir=raw_data_dir,
        ma_window=ma_window,
        short_window=short_window,
        spike_ratio=spike_ratio,
    )
    out = result.merge(volume, on=KEY_COLUMNS, how="left")
    out = out.rename(columns={"volume_ratio": ratio_col, "volume_spike_streak": streak_col})

    strength_factor = sigmoid_boost_factor(
        out[ratio_col],
        threshold=strength_threshold,
        sharpness=strength_sharpness,
        max_boost=max_boost,
    )
    streak_factor = sigmoid_decay_factor(
        out[streak_col],
        threshold=streak_threshold,
        sharpness=streak_sharpness,
    )
    raw_factor = strength_factor * streak_factor
    out[factor_col] = _apply_factor_weight(raw_factor, weight)
    out["volume_penalty_weight"] = weight
    if keep_component_factors:
        out["volume_strength_boost_factor"] = strength_factor
        out["volume_streak_decay_factor"] = streak_factor
        out["volume_raw_factor"] = raw_factor
    out["volume_strength_threshold"] = strength_threshold
    out["volume_streak_threshold"] = streak_threshold
    out[output_score_col] = pd.to_numeric(out[score_col], errors="coerce") * out[factor_col]
    return out


def _apply_burst_strength_post_boost(result: pd.DataFrame, config: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    if not bool(config.get("enabled", False)):
        return result

    raw_data_dir = _resolve_path(project_root, config["raw_data_dir"])
    score_col = str(config.get("score_col", "adjusted_score"))
    output_score_col = str(config.get("output_score_col", score_col))
    factor_col = str(config.get("factor_col", "burst_strength_factor"))
    if score_col not in result.columns:
        raise ValueError(f"Burst strength post boost score_col not found: {score_col}")

    burst = _load_burst_strength_values(
        result,
        raw_data_dir=raw_data_dir,
        volume_window=int(config.get("volume_window", 20)),
        recent_high_window=int(config.get("recent_high_window", 30)),
    )
    out = result.merge(burst, on=KEY_COLUMNS, how="left")
    min_factor = float(config.get("min_factor", 1.0))
    max_factor = float(config.get("max_factor", 1.45))

    ret_1d = sigmoid_rise_factor(
        out["burst_ret_1d"],
        threshold=float(config.get("min_ret_1d", 0.12)),
        sharpness=float(config.get("ret_sharpness", 25.0)),
        missing_value=0.0,
    )
    ret_2d = sigmoid_rise_factor(
        out["burst_ret_2d"],
        threshold=float(config.get("min_ret_2d", 0.16)),
        sharpness=float(config.get("ret_sharpness", 25.0)),
        missing_value=0.0,
    )
    volume_1d = sigmoid_rise_factor(
        out["burst_volume_ratio_1d"],
        threshold=float(config.get("min_volume_ratio_1d", 4.0)),
        sharpness=float(config.get("volume_sharpness", 1.4)),
        missing_value=0.0,
    )
    volume_2d = sigmoid_rise_factor(
        out["burst_volume_ratio_2d"],
        threshold=float(config.get("min_volume_ratio_2d", 3.0)),
        sharpness=float(config.get("volume_sharpness", 1.4)),
        missing_value=0.0,
    )
    amount_1d = sigmoid_rise_factor(
        out["burst_amount_ratio_1d"],
        threshold=float(config.get("min_amount_ratio_1d", 3.5)),
        sharpness=float(config.get("amount_sharpness", 1.3)),
        missing_value=0.0,
    )
    breakout = sigmoid_rise_factor(
        out["burst_breakout_pct"],
        threshold=float(config.get("min_breakout_pct", -0.01)),
        sharpness=float(config.get("breakout_sharpness", 80.0)),
        missing_value=0.0,
    )
    close_position = sigmoid_rise_factor(
        out["burst_close_position"],
        threshold=float(config.get("min_close_position", 0.75)),
        sharpness=float(config.get("close_position_sharpness", 8.0)),
        missing_value=0.0,
    )

    out["burst_strength_price_score"] = pd.concat([ret_1d, ret_2d], axis=1).max(axis=1)
    out["burst_strength_volume_score"] = pd.concat([volume_1d, volume_2d], axis=1).max(axis=1)
    out["burst_strength_score"] = (
        0.30 * out["burst_strength_price_score"]
        + 0.30 * out["burst_strength_volume_score"]
        + 0.15 * amount_1d
        + 0.15 * breakout
        + 0.10 * close_position
    )
    out[factor_col] = min_factor + (max_factor - min_factor) * out["burst_strength_score"].clip(lower=0.0, upper=1.0)
    out["burst_strength_min_ret_1d"] = float(config.get("min_ret_1d", 0.12))
    out["burst_strength_min_volume_ratio_1d"] = float(config.get("min_volume_ratio_1d", 4.0))
    out["burst_strength_min_amount_ratio_1d"] = float(config.get("min_amount_ratio_1d", 3.5))
    out["burst_strength_min_breakout_pct"] = float(config.get("min_breakout_pct", -0.01))
    out[output_score_col] = pd.to_numeric(out[score_col], errors="coerce") * out[factor_col]
    return out


def _apply_base_stability_post_penalty(result: pd.DataFrame, config: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    if not bool(config.get("enabled", False)):
        return result

    raw_data_dir = _resolve_path(project_root, config["raw_data_dir"])
    window = int(config.get("window", 60))
    fast_ma_col = str(config.get("fast_ma_col", "ma_bfq_20"))
    slow_ma_col = str(config.get("slow_ma_col", "ma_bfq_60"))
    trend_ma_col = str(config.get("trend_ma_col", slow_ma_col))
    score_col = str(config.get("score_col", "adjusted_score"))
    output_score_col = str(config.get("output_score_col", score_col))
    factor_col = str(config.get("factor_col", "base_stability_factor"))
    keep_component_factors = bool(config.get("keep_component_factors", False))

    ma_gap_cfg = config.get("ma_gap", {})
    if not isinstance(ma_gap_cfg, dict):
        ma_gap_cfg = {}
    ma_gap_threshold = float(ma_gap_cfg.get("threshold", 0.04))
    ma_gap_sharpness = float(ma_gap_cfg.get("sharpness", 80.0))

    trend_cfg = config.get("ma_trend", {})
    if not isinstance(trend_cfg, dict):
        trend_cfg = {}
    prior_lag = int(trend_cfg.get("prior_lag", window * 2))
    recent_weight = float(trend_cfg.get("recent_weight", 0.7))
    prior_weight = float(trend_cfg.get("prior_weight", 0.3))
    trend_threshold = float(trend_cfg.get("threshold", 0.08))
    trend_sharpness = float(trend_cfg.get("sharpness", 25.0))

    if score_col not in result.columns:
        raise ValueError(f"Base stability post penalty score_col not found: {score_col}")

    stability = _load_base_stability_values(
        result,
        raw_data_dir=raw_data_dir,
        window=window,
        fast_ma_col=fast_ma_col,
        slow_ma_col=slow_ma_col,
        trend_ma_col=trend_ma_col,
        prior_lag=prior_lag,
        recent_weight=recent_weight,
        prior_weight=prior_weight,
    )
    out = result.merge(stability, on=KEY_COLUMNS, how="left")
    ma_gap_factor = sigmoid_decay_factor(
        out["base_ma_gap_l2"],
        threshold=ma_gap_threshold,
        sharpness=ma_gap_sharpness,
    )
    trend_factor = sigmoid_decay_factor(
        out["base_ma60_trend_abs"],
        threshold=trend_threshold,
        sharpness=trend_sharpness,
    )
    out[factor_col] = ma_gap_factor * trend_factor
    if keep_component_factors:
        out["base_ma_gap_factor"] = ma_gap_factor
        out["base_ma60_trend_factor"] = trend_factor
    out["base_ma_gap_threshold"] = ma_gap_threshold
    out["base_ma60_trend_threshold"] = trend_threshold
    out[output_score_col] = pd.to_numeric(out[score_col], errors="coerce") * out[factor_col]
    return out


def _apply_box_breakout_post_penalty(result: pd.DataFrame, config: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    if not bool(config.get("enabled", False)):
        return result

    raw_data_dir = _resolve_path(project_root, config["raw_data_dir"])
    window = int(config.get("window", 60))
    high_col = str(config.get("high_col", "high"))
    close_col = str(config.get("close_col", "close"))
    score_col = str(config.get("score_col", "adjusted_score"))
    output_score_col = str(config.get("output_score_col", score_col))
    factor_col = str(config.get("factor_col", "box_breakout_factor"))

    strength_cfg = config.get("strength", {})
    if not isinstance(strength_cfg, dict):
        strength_cfg = {}
    strength_threshold = float(strength_cfg.get("threshold", -0.01))
    strength_sharpness = float(strength_cfg.get("sharpness", 80.0))
    min_factor = float(config.get("min_factor", 0.3))
    max_factor = float(config.get("max_factor", 1.2))
    weight = float(config.get("weight", 1.0))

    if score_col not in result.columns:
        raise ValueError(f"Box breakout post penalty score_col not found: {score_col}")

    breakout = _load_box_breakout_values(
        result,
        raw_data_dir=raw_data_dir,
        window=window,
        high_col=high_col,
        close_col=close_col,
    )
    out = result.merge(breakout, on=KEY_COLUMNS, how="left")
    strength = sigmoid_boost_factor(
        out["box_breakout_pct"],
        threshold=strength_threshold,
        sharpness=strength_sharpness,
        max_boost=1.0,
        missing_value=0.0,
    )
    # sigmoid_boost_factor returns [1, 2]; normalize it to [0, 1] before scaling.
    normalized_strength = strength - 1.0
    raw_factor = min_factor + (max_factor - min_factor) * normalized_strength
    out[factor_col] = _apply_factor_weight(raw_factor, weight)
    out["box_breakout_raw_factor"] = raw_factor
    out["box_breakout_weight"] = weight
    out["box_breakout_threshold"] = strength_threshold
    out[output_score_col] = pd.to_numeric(out[score_col], errors="coerce") * out[factor_col]
    return out


def _apply_overhang_post_penalty(result: pd.DataFrame, config: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    if not bool(config.get("enabled", False)):
        return result

    raw_data_dir = _resolve_path(project_root, config["raw_data_dir"])
    lookback = int(config.get("lookback", 150))
    n_bins = int(config.get("n_bins", 50))
    threshold = float(config.get("threshold", 0.35))
    sharpness = float(config.get("sharpness", 12.0))
    min_factor = float(config.get("min_factor", 0.4))
    max_factor = float(config.get("max_factor", 1.0))
    score_col = str(config.get("score_col", "adjusted_score"))
    output_score_col = str(config.get("output_score_col", score_col))
    factor_col = str(config.get("factor_col", "overhang_factor"))

    if score_col not in result.columns:
        raise ValueError(f"Overhang post penalty score_col not found: {score_col}")

    overhang = _load_overhang_values(
        result,
        raw_data_dir=raw_data_dir,
        lookback=lookback,
        n_bins=n_bins,
    )
    out = result.merge(overhang, on=KEY_COLUMNS, how="left")
    out[factor_col] = out["overhang_ratio"].map(
        lambda value: compute_overhang_factor(
            value,
            threshold=threshold,
            sharpness=sharpness,
            min_factor=min_factor,
            max_factor=max_factor,
        )
    )
    out["overhang_threshold"] = threshold
    out["overhang_sharpness"] = sharpness
    out[output_score_col] = pd.to_numeric(out[score_col], errors="coerce") * out[factor_col]
    return out


def _apply_chip_structure_review_fields(result: pd.DataFrame, config: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    if not bool(config.get("enabled", False)):
        return result

    raw_data_dir = _resolve_path(project_root, config["raw_data_dir"])
    pre_window = int(config.get("pre_window", 60))
    near_pct = float(config.get("near_pct", 0.03))
    anchor_date_col = str(config.get("anchor_date_col", "anchor_date"))

    chip_values = load_chip_structure_values(
        result,
        raw_data_dir=raw_data_dir,
        pre_window=pre_window,
        near_pct=near_pct,
        anchor_date_col=anchor_date_col,
    )
    return result.merge(chip_values, on=KEY_COLUMNS, how="left")


def _apply_midlong_trend_review_fields(result: pd.DataFrame, config: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    if not bool(config.get("enabled", False)):
        return result

    raw_data_dir = _resolve_path(project_root, config["raw_data_dir"])
    score_col = str(config.get("score_col", ""))
    output_score_col = str(config.get("output_score_col", score_col or ""))
    factor_col = str(config.get("factor_col", "trend_ma_factor"))
    slope_col = str(config.get("slope_col", "trend_mid_ma_slope"))
    threshold = float(config.get("threshold", config.get("min_mid_ma_slope", 0.0)))
    sharpness = float(config.get("sharpness", 80.0))
    min_factor = float(config.get("min_factor", 0.25))
    max_factor = float(config.get("max_factor", 1.35))

    trend_values = load_midlong_trend_values(
        result,
        raw_data_dir=raw_data_dir,
        short_window=int(config.get("short_window", 20)),
        mid_window=int(config.get("mid_window", 60)),
        long_window=int(config.get("long_window", 120)),
        slope_lag=int(config.get("slope_lag", 20)),
        return_window=int(config.get("return_window", 120)),
        position_window=int(config.get("position_window", 120)),
        min_return=float(config.get("min_return", 0.0)),
        min_mid_ma_slope=float(config.get("min_mid_ma_slope", 0.0)),
        min_position=float(config.get("min_position", 0.45)),
        require_above_mid_ma=bool(config.get("require_above_mid_ma", True)),
    )
    out = result.merge(trend_values, on=KEY_COLUMNS, how="left")

    rise = sigmoid_rise_factor(
        out[slope_col],
        threshold=threshold,
        sharpness=sharpness,
        missing_value=0.0,
    )
    out[factor_col] = min_factor + (max_factor - min_factor) * rise
    out["trend_ma_factor_threshold"] = threshold
    out["trend_ma_factor_sharpness"] = sharpness
    out["trend_ma_factor_min"] = min_factor
    out["trend_ma_factor_max"] = max_factor
    if score_col:
        if score_col not in out.columns:
            raise ValueError(f"Midlong trend score_col not found: {score_col}")
        out[output_score_col] = pd.to_numeric(out[score_col], errors="coerce") * out[factor_col]
    return out


def _ensure_phase2_pullback_metrics(result: pd.DataFrame, config: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    required_col = "phase2_pullback_volume_vs_pre"
    if required_col in result.columns:
        return result

    raw_data_dir = _resolve_path(project_root, config["raw_data_dir"])
    metrics = _load_phase2_pullback_metrics(
        result,
        raw_data_dir=raw_data_dir,
        anchor_date_col=str(config.get("anchor_date_col", "best_phase1_date")),
        pre_window=int(config.get("pre_window", 20)),
        burst_window=int(config.get("burst_window", 2)),
        pullback_window=int(config.get("pullback_window", 5)),
        recent_window=int(config.get("recent_window", 2)),
    )
    return result.merge(metrics, on=KEY_COLUMNS, how="left")


def _scale_factor(raw_score: pd.Series, *, min_factor: float, max_factor: float) -> pd.Series:
    numeric = pd.to_numeric(raw_score, errors="coerce").clip(lower=0.0, upper=1.0)
    return float(min_factor) + (float(max_factor) - float(min_factor)) * numeric


def _apply_phase2_volume_hold_post_penalty(result: pd.DataFrame, config: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    if not bool(config.get("enabled", False)):
        return result

    score_col = str(config.get("score_col", "phase2_score_mean"))
    output_score_col = str(config.get("output_score_col", score_col))
    factor_col = str(config.get("factor_col", "phase2_volume_hold_factor"))
    if score_col not in result.columns:
        raise ValueError(f"Phase2 volume hold score_col not found: {score_col}")

    out = _ensure_phase2_pullback_metrics(result, config, project_root)
    min_vs_pre = float(config.get("min_pullback_vs_pre", 1.6))
    min_recent_vs_pre = float(config.get("min_recent_vs_pre", 1.3))
    max_vs_burst = float(config.get("max_pullback_vs_burst", 1.05))
    max_down_pressure = float(config.get("max_down_volume_pressure", 1.5))
    min_factor = float(config.get("min_factor", 0.35))
    max_factor = float(config.get("max_factor", 1.35))

    hold = sigmoid_rise_factor(
        out["phase2_pullback_volume_vs_pre"],
        threshold=min_vs_pre,
        sharpness=float(config.get("hold_sharpness", 3.0)),
        missing_value=0.0,
    )
    recent = sigmoid_rise_factor(
        out["phase2_recent_volume_vs_pre"],
        threshold=min_recent_vs_pre,
        sharpness=float(config.get("recent_sharpness", 3.0)),
        missing_value=0.0,
    )
    burst_cool = sigmoid_decay_factor(
        out["phase2_pullback_volume_vs_burst"],
        threshold=max_vs_burst,
        sharpness=float(config.get("burst_cool_sharpness", 4.0)),
        missing_value=0.5,
    )
    down_pressure = sigmoid_decay_factor(
        out["phase2_down_volume_pressure"],
        threshold=max_down_pressure,
        sharpness=float(config.get("down_pressure_sharpness", 3.0)),
        missing_value=0.7,
    )

    out["phase2_volume_hold_score"] = 0.55 * hold + 0.25 * recent + 0.10 * burst_cool + 0.10 * down_pressure
    out[factor_col] = _scale_factor(out["phase2_volume_hold_score"], min_factor=min_factor, max_factor=max_factor)
    out["phase2_volume_hold_min_pullback_vs_pre"] = min_vs_pre
    out["phase2_volume_hold_min_recent_vs_pre"] = min_recent_vs_pre
    out["phase2_volume_hold_max_pullback_vs_burst"] = max_vs_burst
    out["phase2_volume_hold_max_down_pressure"] = max_down_pressure
    out[output_score_col] = pd.to_numeric(out[score_col], errors="coerce") * out[factor_col]
    return out


def _apply_phase2_pullback_compact_post_penalty(result: pd.DataFrame, config: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    if not bool(config.get("enabled", False)):
        return result

    score_col = str(config.get("score_col", "phase2_score_mean"))
    output_score_col = str(config.get("output_score_col", score_col))
    factor_col = str(config.get("factor_col", "phase2_pullback_compact_factor"))
    if score_col not in result.columns:
        raise ValueError(f"Phase2 pullback compact score_col not found: {score_col}")

    out = _ensure_phase2_pullback_metrics(result, config, project_root)
    min_depth = float(config.get("min_depth", 0.0))
    max_depth = float(config.get("max_depth", 0.14))
    max_low_below_anchor_low = float(config.get("max_low_below_anchor_low", 0.06))
    max_range_contraction = float(config.get("max_range_contraction", 0.95))
    max_recent_range_pct = float(config.get("max_recent_range_pct", 0.12))
    max_chase_extension_pct = float(config.get("max_chase_extension_pct", 0.12))
    min_factor = float(config.get("min_factor", 0.45))
    max_factor = float(config.get("max_factor", 1.25))

    depth_not_deep = sigmoid_decay_factor(
        out["phase2_pullback_depth_pct"],
        threshold=max_depth,
        sharpness=float(config.get("depth_sharpness", 40.0)),
        missing_value=0.0,
    )
    depth_enough = sigmoid_rise_factor(
        out["phase2_pullback_depth_pct"],
        threshold=min_depth,
        sharpness=float(config.get("min_depth_sharpness", 60.0)),
        missing_value=0.0,
    )
    not_broken = sigmoid_rise_factor(
        out["phase2_low_to_anchor_low_pct"],
        threshold=-max_low_below_anchor_low,
        sharpness=float(config.get("breakdown_sharpness", 50.0)),
        missing_value=0.0,
    )
    range_ok = sigmoid_decay_factor(
        out["phase2_range_contraction_ratio"],
        threshold=max_range_contraction,
        sharpness=float(config.get("range_sharpness", 8.0)),
        missing_value=0.0,
    )
    recent_range_ok = sigmoid_decay_factor(
        out["phase2_recent_range_pct"],
        threshold=max_recent_range_pct,
        sharpness=float(config.get("recent_range_sharpness", 35.0)),
        missing_value=0.0,
    )
    not_chasing = sigmoid_decay_factor(
        out["phase2_chase_extension_pct"],
        threshold=max_chase_extension_pct,
        sharpness=float(config.get("chase_sharpness", 35.0)),
        missing_value=0.5,
    )

    out["phase2_pullback_compact_score"] = (
        0.25 * depth_not_deep
        + 0.10 * depth_enough
        + 0.25 * not_broken
        + 0.20 * range_ok
        + 0.10 * recent_range_ok
        + 0.10 * not_chasing
    )
    out[factor_col] = _scale_factor(out["phase2_pullback_compact_score"], min_factor=min_factor, max_factor=max_factor)
    out["phase2_pullback_compact_max_depth"] = max_depth
    out["phase2_pullback_compact_max_low_below_anchor_low"] = max_low_below_anchor_low
    out["phase2_pullback_compact_max_range_contraction"] = max_range_contraction
    out["phase2_pullback_compact_max_recent_range_pct"] = max_recent_range_pct
    out["phase2_pullback_compact_max_chase_extension_pct"] = max_chase_extension_pct
    out[output_score_col] = pd.to_numeric(out[score_col], errors="coerce") * out[factor_col]
    return out


def apply_post_penalties(result: pd.DataFrame, config: Dict[str, Any], project_root: Path) -> pd.DataFrame:
    """Apply optional review-stage penalties without touching training/inference pipelines."""
    if not isinstance(config, dict):
        return result

    out = result.copy()
    runup_penalty_cfg = config.get("runup", {})
    if isinstance(runup_penalty_cfg, dict):
        out = _apply_runup_post_penalty(out, runup_penalty_cfg, project_root)
    volume_penalty_cfg = config.get("volume", {})
    if isinstance(volume_penalty_cfg, dict):
        out = _apply_volume_post_penalty(out, volume_penalty_cfg, project_root)
    burst_strength_cfg = config.get("burst_strength", {})
    if isinstance(burst_strength_cfg, dict):
        out = _apply_burst_strength_post_boost(out, burst_strength_cfg, project_root)
    base_stability_penalty_cfg = config.get("base_stability", {})
    if isinstance(base_stability_penalty_cfg, dict):
        out = _apply_base_stability_post_penalty(out, base_stability_penalty_cfg, project_root)
    box_breakout_penalty_cfg = config.get("box_breakout", {})
    if isinstance(box_breakout_penalty_cfg, dict):
        out = _apply_box_breakout_post_penalty(out, box_breakout_penalty_cfg, project_root)
    overhang_penalty_cfg = config.get("overhang", {})
    if isinstance(overhang_penalty_cfg, dict):
        out = _apply_overhang_post_penalty(out, overhang_penalty_cfg, project_root)
    chip_structure_cfg = config.get("chip_structure", {})
    if isinstance(chip_structure_cfg, dict):
        out = _apply_chip_structure_review_fields(out, chip_structure_cfg, project_root)
    midlong_trend_cfg = config.get("midlong_trend", {})
    if isinstance(midlong_trend_cfg, dict):
        out = _apply_midlong_trend_review_fields(out, midlong_trend_cfg, project_root)
    phase2_volume_hold_cfg = config.get("phase2_volume_hold", {})
    if isinstance(phase2_volume_hold_cfg, dict):
        out = _apply_phase2_volume_hold_post_penalty(out, phase2_volume_hold_cfg, project_root)
    phase2_pullback_compact_cfg = config.get("phase2_pullback_compact", {})
    if isinstance(phase2_pullback_compact_cfg, dict):
        out = _apply_phase2_pullback_compact_post_penalty(out, phase2_pullback_compact_cfg, project_root)
    return out


__all__ = ["apply_post_penalties"]
