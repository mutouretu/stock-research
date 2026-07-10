from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

KEY_COLUMNS = ["sample_id", "ts_code", "asof_date"]
CHIP_COLUMNS = [
    "cost_5pct",
    "cost_15pct",
    "cost_50pct",
    "cost_85pct",
    "cost_95pct",
    "weight_avg",
    "winner_rate",
]


def _safe_ratio(numerator: float | int | None, denominator: float | int | None) -> float:
    if pd.isna(numerator) or pd.isna(denominator):
        return float("nan")
    denominator = float(denominator)
    if denominator == 0:
        return float("nan")
    return float(numerator) / denominator - 1.0


def _normalize_daily_dates(daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out = out.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    return out


def _read_chip_daily(path: Path) -> pd.DataFrame:
    columns = ["trade_date", "close", *CHIP_COLUMNS]
    try:
        daily = pd.read_parquet(path, columns=columns).copy()
    except Exception:
        return pd.DataFrame(columns=columns)
    daily = _normalize_daily_dates(daily)
    for col in ["close", *CHIP_COLUMNS]:
        if col in daily.columns:
            daily[col] = pd.to_numeric(daily[col], errors="coerce")
    return daily


def _row_metrics(daily: pd.DataFrame, *, anchor_date: str | None, asof_date: str, pre_window: int, near_pct: float) -> Dict[str, Any]:
    if daily.empty or "trade_date" not in daily.columns:
        return _empty_metrics(anchor_date=anchor_date)

    history = daily[daily["trade_date"] <= asof_date].copy()
    if history.empty:
        return _empty_metrics(anchor_date=anchor_date)

    current_price_row = history.iloc[-1]
    current_close = current_price_row.get("close", pd.NA)
    chip_history = history.dropna(subset=["weight_avg", "cost_50pct", "winner_rate"], how="all")
    current = chip_history.iloc[-1] if not chip_history.empty else current_price_row
    anchor = str(anchor_date) if anchor_date else None
    if anchor:
        pre = daily[daily["trade_date"] < anchor].tail(pre_window)
        post = daily[(daily["trade_date"] >= anchor) & (daily["trade_date"] <= asof_date)]
    else:
        pre = pd.DataFrame()
        post = history.tail(pre_window)

    pre_center = pd.to_numeric(pre.get("weight_avg"), errors="coerce").mean() if not pre.empty else float("nan")
    post_center = pd.to_numeric(post.get("weight_avg"), errors="coerce").mean() if not post.empty else float("nan")
    pre_winner = pd.to_numeric(pre.get("winner_rate"), errors="coerce").mean() if not pre.empty else float("nan")
    post_winner = pd.to_numeric(post.get("winner_rate"), errors="coerce").mean() if not post.empty else float("nan")

    cost_15 = current.get("cost_15pct", pd.NA)
    cost_50 = current.get("cost_50pct", pd.NA)
    cost_85 = current.get("cost_85pct", pd.NA)
    cost_95 = current.get("cost_95pct", pd.NA)
    weight_avg = current.get("weight_avg", pd.NA)
    winner_rate = current.get("winner_rate", pd.NA)

    near_low = float(current_close) * (1.0 - near_pct) if pd.notna(current_close) else float("nan")
    near_high = float(current_close) * (1.0 + near_pct) if pd.notna(current_close) else float("nan")
    near_price_has_cost_50 = bool(pd.notna(cost_50) and pd.notna(near_low) and near_low <= float(cost_50) <= near_high)
    near_price_has_weight_avg = bool(pd.notna(weight_avg) and pd.notna(near_low) and near_low <= float(weight_avg) <= near_high)

    return {
        "chip_anchor_date": anchor,
        "chip_data_date": current.get("trade_date", pd.NA),
        "chip_current_close": current_close,
        "chip_cost_5pct": current.get("cost_5pct", pd.NA),
        "chip_cost_15pct": cost_15,
        "chip_cost_50pct": cost_50,
        "chip_cost_85pct": cost_85,
        "chip_cost_95pct": cost_95,
        "chip_weight_avg": weight_avg,
        "chip_winner_rate": winner_rate,
        "chip_price_vs_cost_50": _safe_ratio(current_close, cost_50),
        "chip_price_vs_cost_85": _safe_ratio(current_close, cost_85),
        "chip_price_vs_cost_95": _safe_ratio(current_close, cost_95),
        "chip_price_vs_weight_avg": _safe_ratio(current_close, weight_avg),
        "chip_cost_band_width_15_85": _safe_ratio(cost_85, cost_15),
        "chip_cost_band_width_5_95": _safe_ratio(cost_95, current.get("cost_5pct", pd.NA)),
        "chip_pre_weight_avg_mean": pre_center,
        "chip_post_weight_avg_mean": post_center,
        "chip_center_shift": _safe_ratio(post_center, pre_center),
        "chip_pre_winner_rate_mean": pre_winner,
        "chip_post_winner_rate_mean": post_winner,
        "chip_winner_rate_change": float(post_winner) - float(pre_winner) if pd.notna(pre_winner) and pd.notna(post_winner) else float("nan"),
        "chip_near_price_has_cost_50": near_price_has_cost_50,
        "chip_near_price_has_weight_avg": near_price_has_weight_avg,
    }


def _empty_metrics(*, anchor_date: str | None) -> Dict[str, Any]:
    return {
        "chip_anchor_date": str(anchor_date) if anchor_date else None,
        "chip_data_date": pd.NA,
        "chip_current_close": pd.NA,
        "chip_cost_5pct": pd.NA,
        "chip_cost_15pct": pd.NA,
        "chip_cost_50pct": pd.NA,
        "chip_cost_85pct": pd.NA,
        "chip_cost_95pct": pd.NA,
        "chip_weight_avg": pd.NA,
        "chip_winner_rate": pd.NA,
        "chip_price_vs_cost_50": pd.NA,
        "chip_price_vs_cost_85": pd.NA,
        "chip_price_vs_cost_95": pd.NA,
        "chip_price_vs_weight_avg": pd.NA,
        "chip_cost_band_width_15_85": pd.NA,
        "chip_cost_band_width_5_95": pd.NA,
        "chip_pre_weight_avg_mean": pd.NA,
        "chip_post_weight_avg_mean": pd.NA,
        "chip_center_shift": pd.NA,
        "chip_pre_winner_rate_mean": pd.NA,
        "chip_post_winner_rate_mean": pd.NA,
        "chip_winner_rate_change": pd.NA,
        "chip_near_price_has_cost_50": False,
        "chip_near_price_has_weight_avg": False,
    }


def load_chip_structure_values(
    rows: pd.DataFrame,
    *,
    raw_data_dir: Path,
    pre_window: int = 60,
    near_pct: float = 0.03,
    anchor_date_col: str = "anchor_date",
) -> pd.DataFrame:
    """Load interpretable chip-structure fields for review; it does not change scores."""
    review_rows = rows.copy()
    required = [col for col in KEY_COLUMNS if col not in review_rows.columns]
    if required:
        raise ValueError(f"chip structure reviewer missing required columns: {required}")

    output_rows: List[Dict[str, Any]] = []
    base_cols = KEY_COLUMNS + ([anchor_date_col] if anchor_date_col in review_rows.columns else [])
    for ts_code, group in review_rows[base_cols].drop_duplicates().groupby("ts_code"):
        path = raw_data_dir / f"{ts_code}.parquet"
        daily = _read_chip_daily(path) if path.exists() else pd.DataFrame()
        for _, row in group.iterrows():
            anchor_date = row.get(anchor_date_col) if anchor_date_col in row.index else None
            metrics = _row_metrics(
                daily,
                anchor_date=str(anchor_date) if pd.notna(anchor_date) else None,
                asof_date=str(row["asof_date"]),
                pre_window=pre_window,
                near_pct=near_pct,
            )
            output_rows.append(
                {
                    "sample_id": row["sample_id"],
                    "ts_code": row["ts_code"],
                    "asof_date": row["asof_date"],
                    **metrics,
                }
            )
    return pd.DataFrame(output_rows)


__all__ = ["CHIP_COLUMNS", "load_chip_structure_values"]
