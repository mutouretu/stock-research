from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipelines.w_bottom.train_long_base_breakout_baseline import (  # noqa: E402
    build_daily_features,
    load_daily_for_symbol,
)
from src.common.paths import get_shared_us_daily_dir  # noqa: E402

DEFAULT_US_DAILY_DIR = get_shared_us_daily_dir()


def run_latest_ensemble_scan(
    *,
    daily_dir: str | Path = DEFAULT_US_DAILY_DIR,
    model_root: str | Path = "outputs/models/w_bottom/long_base_breakout_baseline/models",
    output_dir: str | Path = "outputs/predictions/w_bottom/latest_ensemble",
    asof_date: str | None = None,
    min_history: int = 252,
    max_window: int = 504,
    threshold: float = 0.5,
    top_n: int = 100,
) -> dict[str, Any]:
    daily_path = Path(daily_dir)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lgbm_model, xgb_model, feature_columns = load_ensemble_models(model_root)
    feature_rows: list[dict[str, Any]] = []
    skipped = 0
    skip_examples: list[str] = []
    target_date = pd.Timestamp(asof_date) if asof_date else None

    for parquet_path in sorted(daily_path.glob("*.parquet")):
        ts_code = parquet_path.stem.upper()
        try:
            daily = load_daily_for_symbol(daily_path, ts_code)
            asof_idx = _select_asof_idx(daily, target_date)
            if asof_idx is None:
                raise ValueError("no daily bar on or before requested asof_date")
            if asof_idx + 1 < min_history:
                raise ValueError(f"insufficient history: have={asof_idx + 1}, need={min_history}")
            start_idx = max(0, asof_idx - int(max_window) + 1)
            window = daily.iloc[start_idx : asof_idx + 1].copy().reset_index(drop=True)
            features = build_daily_features(window)
            feature_rows.append(
                {
                    "ts_code": ts_code,
                    "asof_date": pd.Timestamp(window["trade_date"].iloc[-1]).strftime("%Y-%m-%d"),
                    **features,
                }
            )
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            if len(skip_examples) < 30:
                skip_examples.append(f"{ts_code}: {exc}")

    if not feature_rows:
        raise RuntimeError(f"No symbols were usable in {daily_path}")

    feature_df = pd.DataFrame(feature_rows)
    for col in feature_columns:
        if col not in feature_df.columns:
            feature_df[col] = np.nan
    X = feature_df[feature_columns].apply(pd.to_numeric, errors="coerce")

    predictions = feature_df[["ts_code", "asof_date"]].copy()
    predictions["lgbm_score"] = lgbm_model.predict_proba(X)[:, 1]
    predictions["xgb_score"] = xgb_model.predict_proba(X)[:, 1]
    predictions["ensemble_score"] = predictions[["lgbm_score", "xgb_score"]].mean(axis=1)
    predictions["score_gap"] = (predictions["lgbm_score"] - predictions["xgb_score"]).abs()
    predictions["lgbm_pred_label"] = (predictions["lgbm_score"] >= threshold).astype(int)
    predictions["xgb_pred_label"] = (predictions["xgb_score"] >= threshold).astype(int)
    predictions["ensemble_pred_label"] = (predictions["ensemble_score"] >= threshold).astype(int)
    predictions["model_agreement"] = (predictions["lgbm_pred_label"] == predictions["xgb_pred_label"]).astype(int)
    predictions = predictions.sort_values(["ensemble_score", "score_gap"], ascending=[False, True]).reset_index(
        drop=True
    )

    predictions_path = out_dir / "latest_universe_predictions.csv"
    predictions.to_csv(predictions_path, index=False)
    all_candidates = predictions[predictions["ensemble_pred_label"] == 1].copy()
    candidates = all_candidates.head(top_n).copy()
    candidates_path = out_dir / "latest_universe_candidates.csv"
    candidates.to_csv(candidates_path, index=False)

    summary = {
        "daily_dir": str(daily_path),
        "model_root": str(model_root),
        "output_dir": str(out_dir),
        "requested_asof_date": asof_date,
        "available_asof_min": str(predictions["asof_date"].min()),
        "available_asof_max": str(predictions["asof_date"].max()),
        "symbols_scanned": int(len(predictions)),
        "total_candidates": int(len(all_candidates)),
        "exported_candidates": int(len(candidates)),
        "threshold": float(threshold),
        "top_n": int(top_n),
        "skipped_symbols": int(skipped),
        "skip_examples": skip_examples,
        "predictions_path": str(predictions_path),
        "candidates_path": str(candidates_path),
    }
    report_path = out_dir / "latest_universe_report.md"
    report_path.write_text(build_latest_scan_report(summary, predictions, candidates), encoding="utf-8")
    summary["report_path"] = str(report_path)
    (out_dir / "latest_universe_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def load_ensemble_models(model_root: str | Path):
    root = Path(model_root)
    lgbm_dir = root / "lightgbm"
    xgb_dir = root / "xgboost"
    lgbm_model = joblib.load(lgbm_dir / "model.joblib")
    xgb_model = joblib.load(xgb_dir / "model.joblib")
    lgbm_features = json.loads((lgbm_dir / "feature_columns.json").read_text(encoding="utf-8"))
    xgb_features = json.loads((xgb_dir / "feature_columns.json").read_text(encoding="utf-8"))
    if lgbm_features != xgb_features:
        raise ValueError("LightGBM and XGBoost feature columns differ")
    return lgbm_model, xgb_model, lgbm_features


def build_latest_scan_report(summary: dict[str, Any], predictions: pd.DataFrame, candidates: pd.DataFrame) -> str:
    lines = [
        "# Latest Universe LGBM XGBoost Ensemble Scan",
        "",
        f"- daily_dir: `{summary['daily_dir']}`",
        f"- model_root: `{summary['model_root']}`",
        f"- requested_asof_date: {summary['requested_asof_date']}",
        f"- available_asof_range: {summary['available_asof_min']} to {summary['available_asof_max']}",
        f"- symbols_scanned: {summary['symbols_scanned']}",
        f"- total_candidates: {summary['total_candidates']}",
        f"- exported_candidates: {summary['exported_candidates']}",
        f"- threshold: {summary['threshold']}",
        f"- skipped_symbols: {summary['skipped_symbols']}",
        f"- predictions_path: `{summary['predictions_path']}`",
        f"- candidates_path: `{summary['candidates_path']}`",
        "",
        "## Top Candidates",
        _frame_to_markdown(candidates.head(50)),
        "",
        "## Top Scores Including Non-Candidates",
        _frame_to_markdown(predictions.head(30)),
        "",
        "## Skip Examples",
    ]
    lines.extend([f"- {item}" for item in summary["skip_examples"]] or ["- none"])
    lines.append("")
    return "\n".join(lines)


def _select_asof_idx(daily: pd.DataFrame, target_date: pd.Timestamp | None) -> int | None:
    if daily.empty:
        return None
    if target_date is None:
        return int(len(daily) - 1)
    dates = pd.to_datetime(daily["trade_date"], errors="coerce")
    eligible = dates[dates <= target_date]
    if eligible.empty:
        return None
    return int(eligible.index[-1])


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_none_"
    display = frame.copy()
    for col in display.columns:
        if pd.api.types.is_float_dtype(display[col]):
            display[col] = display[col].map(lambda value: f"{value:.6f}")
    columns = [str(col) for col in display.columns]
    rows = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in display.iterrows():
        rows.append("| " + " | ".join(str(row[col]).replace("|", "\\|") for col in display.columns) + " |")
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run latest universe LGBM/XGBoost ensemble scan.")
    parser.add_argument("--daily-dir", default=str(DEFAULT_US_DAILY_DIR))
    parser.add_argument("--model-root", default="outputs/models/w_bottom/long_base_breakout_baseline/models")
    parser.add_argument("--output-dir", default="outputs/predictions/w_bottom/latest_ensemble")
    parser.add_argument("--asof-date", default=None)
    parser.add_argument("--min-history", type=int, default=252)
    parser.add_argument("--max-window", type=int, default=504)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--top-n", type=int, default=100)
    args = parser.parse_args()

    summary = run_latest_ensemble_scan(
        daily_dir=args.daily_dir,
        model_root=args.model_root,
        output_dir=args.output_dir,
        asof_date=args.asof_date,
        min_history=args.min_history,
        max_window=args.max_window,
        threshold=args.threshold,
        top_n=args.top_n,
    )
    print("Latest ensemble scan finished:")
    for key, value in summary.items():
        if key != "skip_examples":
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
