from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.loader import DailyDataLoader
from src.data.schema import build_sample_id
from src.features.feature_builder_tabular import build_tabular_features
from src.features.indicators import add_basic_indicators
from src.features.window_builder import build_window_by_asof_date
from src.inference.predictor import TabularPredictor


@dataclass
class Predictors:
    phase1_lgbm: TabularPredictor
    phase1_xgb: TabularPredictor
    phase2_lgbm: TabularPredictor
    phase2_xgb: TabularPredictor


def _load_yaml(path: str | Path) -> Dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"config not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _load_predictors(config: Dict[str, Any]) -> Predictors:
    phase1 = config.get("phase1", {}) or {}
    phase2 = config.get("phase2", {}) or {}
    return Predictors(
        phase1_lgbm=TabularPredictor.from_dir(Path(phase1["lgbm_model_dir"])),
        phase1_xgb=TabularPredictor.from_dir(Path(phase1["xgb_model_dir"])),
        phase2_lgbm=TabularPredictor.from_dir(Path(phase2["lgbm_model_dir"])),
        phase2_xgb=TabularPredictor.from_dir(Path(phase2["xgb_model_dir"])),
    )


def _to_date_strings(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d")


def _load_prepared_daily(raw_daily_dir: Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    loader = DailyDataLoader(raw_daily_dir)
    prepared: dict[str, pd.DataFrame] = {}
    all_dates: set[str] = set()

    for i, path in enumerate(sorted(raw_daily_dir.glob("*.parquet")), start=1):
        ts_code = path.stem
        try:
            daily_df = add_basic_indicators(loader.load_one(ts_code))
            prepared[ts_code] = daily_df
            all_dates.update(_to_date_strings(daily_df["trade_date"]).dropna().tolist())
        except Exception as exc:  # noqa: BLE001
            print(f"[skip] {ts_code}: {exc}")
        if i % 500 == 0:
            print(f"loaded_symbols={i}")

    return prepared, sorted(all_dates)


def _build_features_for_date(
    prepared: dict[str, pd.DataFrame],
    asof_date: str,
    window_size: int,
    min_history: int,
    ts_codes: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    meta_rows: list[dict[str, str]] = []
    feat_rows: list[dict[str, float]] = []

    iterable = prepared.items()
    if ts_codes is not None:
        iterable = ((ts, prepared[ts]) for ts in sorted(ts_codes) if ts in prepared)

    for ts_code, daily_df in iterable:
        window_df = build_window_by_asof_date(
            daily_df,
            asof_date=asof_date,
            window_size=window_size,
            min_history=min_history,
        )
        if window_df is None:
            continue
        meta_rows.append(
            {
                "sample_id": build_sample_id(ts_code, asof_date),
                "ts_code": ts_code,
                "asof_date": asof_date,
            }
        )
        feat_rows.append(build_tabular_features(window_df))

    return pd.DataFrame(meta_rows), pd.DataFrame(feat_rows)


def _score_with_pair(
    meta_df: pd.DataFrame,
    feat_df: pd.DataFrame,
    lgbm: TabularPredictor,
    xgb: TabularPredictor,
    prefix: str,
) -> pd.DataFrame:
    if meta_df.empty:
        return meta_df.copy()
    out = meta_df.copy()
    out[f"{prefix}_score_lgbm"] = lgbm.predict_proba(feat_df)
    out[f"{prefix}_score_xgb"] = xgb.predict_proba(feat_df)
    out[f"{prefix}_score_mean"] = (out[f"{prefix}_score_lgbm"] + out[f"{prefix}_score_xgb"]) / 2.0
    out[f"{prefix}_score_min"] = out[[f"{prefix}_score_lgbm", f"{prefix}_score_xgb"]].min(axis=1)
    return out


def _select_phase1_anchor_top(
    prepared: dict[str, pd.DataFrame],
    predictors: Predictors,
    anchor_date: str,
    phase1_top_n: int,
    window_size: int,
    min_history: int,
) -> pd.DataFrame:
    meta_df, feat_df = _build_features_for_date(prepared, anchor_date, window_size, min_history)
    if meta_df.empty:
        raise RuntimeError(f"No Phase1 predictable samples for anchor_date={anchor_date}")

    scored = _score_with_pair(meta_df, feat_df, predictors.phase1_lgbm, predictors.phase1_xgb, "phase1")
    scored = scored.sort_values(["phase1_score_mean", "phase1_score_min"], ascending=[False, False]).reset_index(drop=True)
    top = scored.head(phase1_top_n).copy()
    top["phase1_rank"] = range(1, len(top) + 1)
    return top


def _build_stock_resource_pool(daily_anchor_top: pd.DataFrame) -> pd.DataFrame:
    """Collapse repeated daily Phase1 hits into one stock-level pool row."""
    if daily_anchor_top.empty:
        return daily_anchor_top.copy()

    pool_rows: list[dict[str, Any]] = []
    for ts_code, group in daily_anchor_top.sort_values(["asof_date", "phase1_rank"]).groupby("ts_code", sort=False):
        first = group.iloc[0].to_dict()
        last = group.iloc[-1]
        best = group.sort_values(["phase1_score_mean", "phase1_score_min"], ascending=[False, False]).iloc[0]
        seen_dates = group["asof_date"].astype(str).tolist()

        first["pool_entry_date"] = str(first["asof_date"])
        first["phase1_seen_count"] = int(len(group))
        first["phase1_seen_dates"] = ";".join(seen_dates)
        first["last_seen_phase1_date"] = str(last["asof_date"])
        first["latest_phase1_rank"] = int(last["phase1_rank"])
        first["latest_phase1_score_lgbm"] = float(last["phase1_score_lgbm"])
        first["latest_phase1_score_xgb"] = float(last["phase1_score_xgb"])
        first["latest_phase1_score_mean"] = float(last["phase1_score_mean"])
        first["latest_phase1_score_min"] = float(last["phase1_score_min"])
        first["best_phase1_date"] = str(best["asof_date"])
        first["best_phase1_rank"] = int(best["phase1_rank"])
        first["best_phase1_score_mean"] = float(best["phase1_score_mean"])
        first["pool_policy"] = "first_entry_per_stock"
        pool_rows.append(first)

    pool = pd.DataFrame(pool_rows)
    return pool.sort_values(["asof_date", "phase1_rank"]).reset_index(drop=True)


def _anchor_dates_from_config(config: Dict[str, Any], all_dates: list[str]) -> list[str]:
    if "target_date" not in config:
        anchor_date = str(config["anchor_date"])
        if anchor_date not in all_dates:
            raise RuntimeError(f"anchor_date not found in raw data: {anchor_date}")
        return [anchor_date]

    target_date = str(config["target_date"])
    if target_date not in all_dates:
        raise RuntimeError(f"target_date not found in raw data: {target_date}")

    target_pos = all_dates.index(target_date)
    anchor_start_date = config.get("anchor_start_date")
    if anchor_start_date is not None:
        anchor_start = str(anchor_start_date)
        if anchor_start not in all_dates:
            raise RuntimeError(f"anchor_start_date not found in raw data: {anchor_start}")
        start_pos = all_dates.index(anchor_start)
    else:
        lookback_days = int(config.get("anchor_lookback_days", config.get("max_forward_days", 10)))
        start_pos = max(0, target_pos - lookback_days)
    anchor_dates = all_dates[start_pos:target_pos]
    if not anchor_dates:
        raise RuntimeError(f"No anchor dates available before target_date={target_date}")
    return anchor_dates


def _track_dates(all_dates: list[str], anchor_date: str, max_forward_days: int) -> list[str]:
    if anchor_date not in all_dates:
        raise RuntimeError(f"anchor_date not found in raw data: {anchor_date}")
    anchor_pos = all_dates.index(anchor_date)
    return all_dates[anchor_pos + 1 : anchor_pos + 1 + max_forward_days]


def _track_dates_for_anchor(
    all_dates: list[str],
    anchor_date: str,
    max_forward_days: int,
    target_date: str | None = None,
) -> list[str]:
    if target_date is None:
        return _track_dates(all_dates, anchor_date, max_forward_days)

    if anchor_date not in all_dates:
        raise RuntimeError(f"anchor_date not found in raw data: {anchor_date}")
    if target_date not in all_dates:
        raise RuntimeError(f"target_date not found in raw data: {target_date}")

    anchor_pos = all_dates.index(anchor_date)
    target_pos = all_dates.index(target_date)
    if target_pos <= anchor_pos:
        return []

    end_pos = min(target_pos, anchor_pos + max_forward_days)
    return all_dates[anchor_pos + 1 : end_pos + 1]


def _daily_row(daily_df: pd.DataFrame, asof_date: str) -> pd.Series | None:
    dates = _to_date_strings(daily_df["trade_date"])
    rows = daily_df.loc[dates == asof_date]
    if rows.empty:
        return None
    return rows.iloc[-1]


def _price_metrics(
    daily_df: pd.DataFrame,
    anchor_date: str,
    asof_date: str,
    anchor_close: float,
) -> dict[str, float]:
    dates = _to_date_strings(daily_df["trade_date"])
    path = daily_df.loc[(dates >= anchor_date) & (dates <= asof_date)].copy()
    current = _daily_row(daily_df, asof_date)
    if path.empty or current is None or anchor_close <= 0:
        return {
            "current_close": float("nan"),
            "current_return_from_anchor": float("nan"),
            "max_runup_since_anchor": float("nan"),
            "drawdown_from_post_anchor_high": float("nan"),
            "min_low_return_from_anchor": float("nan"),
        }

    current_close = float(current["close"])
    high = pd.to_numeric(path["high"] if "high" in path.columns else path["close"], errors="coerce")
    low = pd.to_numeric(path["low"] if "low" in path.columns else path["close"], errors="coerce")
    max_high = float(high.max())
    min_low = float(low.min())
    return {
        "current_close": current_close,
        "current_return_from_anchor": current_close / anchor_close - 1.0,
        "max_runup_since_anchor": max_high / anchor_close - 1.0,
        "drawdown_from_post_anchor_high": current_close / max_high - 1.0 if max_high > 0 else float("nan"),
        "min_low_return_from_anchor": min_low / anchor_close - 1.0,
    }


def _build_pool_score_rows(
    item: pd.Series,
    daily_df: pd.DataFrame | None,
    phase2_scores: dict[tuple[str, str], dict[str, float]],
    score_dates: list[str],
) -> list[dict[str, Any]]:
    ts_code = str(item["ts_code"])
    anchor_date = str(item["asof_date"])
    event_id = f"{ts_code}_{anchor_date}"

    if daily_df is None:
        return []

    anchor = _daily_row(daily_df, anchor_date)
    if anchor is None:
        return []

    anchor_close = float(anchor["close"])
    rows: list[dict[str, Any]] = []
    date_list = _to_date_strings(daily_df["trade_date"]).tolist()
    anchor_pos = date_list.index(anchor_date)

    for asof_date in score_dates:
        current = _daily_row(daily_df, asof_date)
        if current is None:
            continue

        metrics = _price_metrics(daily_df, anchor_date, asof_date, anchor_close)
        score = phase2_scores.get((ts_code, asof_date), {})
        phase2_score_lgbm = score.get("phase2_score_lgbm", float("nan"))
        phase2_score_xgb = score.get("phase2_score_xgb", float("nan"))
        phase2_score_mean = score.get("phase2_score_mean", float("nan"))
        phase2_score_min = score.get("phase2_score_min", float("nan"))
        asof_pos = date_list.index(asof_date)

        rows.append(
            {
                "event_id": event_id,
                "sample_id": build_sample_id(ts_code, asof_date),
                "ts_code": ts_code,
                "anchor_date": anchor_date,
                "pool_entry_date": item.get("pool_entry_date", anchor_date),
                "asof_date": asof_date,
                "days_since_anchor": asof_pos - anchor_pos,
                "phase1_rank": int(item["phase1_rank"]),
                "phase1_seen_count": int(item.get("phase1_seen_count", 1)),
                "phase1_seen_dates": item.get("phase1_seen_dates", anchor_date),
                "last_seen_phase1_date": item.get("last_seen_phase1_date", anchor_date),
                "latest_phase1_rank": item.get("latest_phase1_rank", item["phase1_rank"]),
                "latest_phase1_score_mean": item.get("latest_phase1_score_mean", item["phase1_score_mean"]),
                "best_phase1_date": item.get("best_phase1_date", anchor_date),
                "best_phase1_score_mean": item.get("best_phase1_score_mean", item["phase1_score_mean"]),
                "phase1_score_lgbm": float(item["phase1_score_lgbm"]),
                "phase1_score_xgb": float(item["phase1_score_xgb"]),
                "phase1_score_mean": float(item["phase1_score_mean"]),
                "phase1_score_min": float(item["phase1_score_min"]),
                "anchor_close": anchor_close,
                **metrics,
                "phase2_score_lgbm": phase2_score_lgbm,
                "phase2_score_xgb": phase2_score_xgb,
                "phase2_score_mean": phase2_score_mean,
                "phase2_score_min": phase2_score_min,
            }
        )

    return rows


def _build_phase2_scores(
    prepared: dict[str, pd.DataFrame],
    predictors: Predictors,
    track_dates: list[str],
    ts_codes: set[str],
    window_size: int,
    min_history: int,
) -> dict[tuple[str, str], dict[str, float]]:
    scores: dict[tuple[str, str], dict[str, float]] = {}
    for asof_date in track_dates:
        meta_df, feat_df = _build_features_for_date(
            prepared,
            asof_date,
            window_size,
            min_history,
            ts_codes=ts_codes,
        )
        if meta_df.empty:
            continue
        scored = _score_with_pair(meta_df, feat_df, predictors.phase2_lgbm, predictors.phase2_xgb, "phase2")
        for row in scored.itertuples(index=False):
            scores[(str(row.ts_code), str(row.asof_date))] = {
                "phase2_score_lgbm": float(row.phase2_score_lgbm),
                "phase2_score_xgb": float(row.phase2_score_xgb),
                "phase2_score_mean": float(row.phase2_score_mean),
                "phase2_score_min": float(row.phase2_score_min),
            }
    return scores


def run_phase_tracking(config_path: str | Path) -> Dict[str, pd.DataFrame]:
    config = _load_yaml(config_path)
    raw_daily_dir = Path(config.get("raw_daily_dir", "data/raw/daily"))
    if not raw_daily_dir.exists():
        raise FileNotFoundError(f"raw_daily_dir not found: {raw_daily_dir}")

    phase1_top_n = int(config.get("phase1_top_n", 20))
    window_size = int(config.get("window_size", 150))
    min_history = int(config.get("min_history", 1))
    output_dir = Path(config.get("output_dir", "outputs/predictions/type_n/phase_tracking"))
    predictors = _load_predictors(config)

    prepared, all_dates = _load_prepared_daily(raw_daily_dir)
    anchor_dates = _anchor_dates_from_config(config, all_dates)
    target_date = str(config["target_date"]) if "target_date" in config else None

    anchor_frames: list[pd.DataFrame] = []
    for anchor_date in anchor_dates:
        top = _select_phase1_anchor_top(
            prepared,
            predictors,
            anchor_date,
            phase1_top_n,
            window_size,
            min_history,
        )
        anchor_frames.append(top)
    daily_anchor_top = pd.concat(anchor_frames, ignore_index=True) if anchor_frames else pd.DataFrame()
    anchor_top = _build_stock_resource_pool(daily_anchor_top) if target_date else daily_anchor_top

    max_forward_days = int(config.get("max_forward_days", 10))
    score_dates_by_anchor = {
        anchor_date: [target_date]
        if target_date
        else _track_dates_for_anchor(all_dates, anchor_date, max_forward_days, None)
        for anchor_date in anchor_dates
    }
    all_score_dates = sorted({day for dates in score_dates_by_anchor.values() for day in dates if day})
    phase2_scores = _build_phase2_scores(
        prepared,
        predictors,
        all_score_dates,
        set(anchor_top["ts_code"].astype(str)) if "ts_code" in anchor_top.columns else set(),
        window_size,
        min_history,
    )

    score_rows: list[dict[str, Any]] = []
    for _, item in anchor_top.iterrows():
        rows = _build_pool_score_rows(
            item,
            prepared.get(str(item["ts_code"])),
            phase2_scores,
            score_dates_by_anchor.get(str(item["asof_date"]), []),
        )
        score_rows.extend(rows)

    pool_scores = pd.DataFrame(score_rows)
    if not pool_scores.empty:
        pool_scores = pool_scores.sort_values(
            ["asof_date", "phase2_score_mean", "phase2_score_min", "phase1_score_mean"],
            ascending=[True, False, False, False],
        ).reset_index(drop=True)

    output_dir.mkdir(parents=True, exist_ok=True)
    daily_anchor_top.to_csv(output_dir / "phase1_daily_top_anchor.csv", index=False)
    anchor_top.to_csv(output_dir / "phase1_pool_anchor.csv", index=False)
    anchor_top.to_csv(output_dir / "phase1_top_anchor.csv", index=False)
    pool_scores.to_csv(output_dir / "phase2_pool_scores.csv", index=False)

    snapshot_date = target_date or (all_score_dates[-1] if all_score_dates else None)
    target_snapshot = pd.DataFrame()
    if snapshot_date and not pool_scores.empty:
        target_snapshot = pool_scores.loc[pool_scores["asof_date"].astype(str) == snapshot_date].copy()
        target_snapshot = target_snapshot.sort_values(
            ["phase2_score_mean", "phase2_score_min", "phase1_score_mean"],
            ascending=[False, False, False],
        ).reset_index(drop=True)
        target_snapshot.to_csv(output_dir / "tracking_target_snapshot.csv", index=False)

    print(f"anchor_dates={anchor_dates}")
    print(f"daily_anchor_top={len(daily_anchor_top)}")
    print(f"pool_anchor={len(anchor_top)}")
    print(f"score_dates={all_score_dates}")
    print(f"pool_scores={len(pool_scores)}")
    if not target_snapshot.empty:
        print(f"target_snapshot_date={snapshot_date}")
        print(f"target_snapshot={len(target_snapshot)}")
    print(f"output_dir={output_dir}")

    return {
        "phase1_top_anchor": anchor_top,
        "phase2_pool_scores": pool_scores,
        "tracking_target_snapshot": target_snapshot,
    }


def main(config_path: str = "configs/phase_tracking.yaml") -> Dict[str, pd.DataFrame]:
    return run_phase_tracking(config_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a deduplicated Phase1 pool and score it with Phase2 models.")
    parser.add_argument("--config", default="configs/phase_tracking.yaml", help="Path to phase tracking config yaml")
    args = parser.parse_args()
    main(config_path=args.config)
