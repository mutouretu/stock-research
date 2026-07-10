from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.inference.postprocess import resolve_dated_output_path
from src.pipelines.run_scan import main as run_single_scan


def _load_yaml(path: str) -> Dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _prepare_ranked(
    df: pd.DataFrame,
    score_col: str,
    rank_col: str,
    model_score_col: str | None = None,
) -> pd.DataFrame:
    out = df.copy().reset_index(drop=True)
    out[rank_col] = out.index + 1
    rename_map = {"score": score_col}
    if model_score_col is not None and "model_score" in out.columns:
        rename_map["model_score"] = model_score_col
    return out.rename(columns=rename_map)


def merge_ranked_predictions(lgbm_df: pd.DataFrame, xgb_df: pd.DataFrame) -> pd.DataFrame:
    """Merge LGBM and XGB scan outputs while keeping shared metadata once."""
    lgbm_ranked = _prepare_ranked(lgbm_df, "score_lgbm", "rank_lgbm", "model_score_lgbm")
    xgb_ranked = _prepare_ranked(xgb_df, "score_xgb", "rank_xgb", "model_score_xgb")

    join_cols = ["sample_id", "ts_code", "asof_date"]
    missing = [col for col in join_cols if col not in lgbm_ranked.columns or col not in xgb_ranked.columns]
    if missing:
        raise ValueError(f"missing merge key columns: {missing}")

    xgb_score_cols = join_cols + ["score_xgb", "rank_xgb"]
    if "model_score_xgb" in xgb_ranked.columns:
        xgb_score_cols.append("model_score_xgb")
    merged = lgbm_ranked.merge(
        xgb_ranked[xgb_score_cols],
        on=join_cols,
        how="inner",
    )
    if merged.empty:
        raise ValueError("No intersection candidates found between LGBM and XGB scans")

    merged["score_mean"] = (merged["score_lgbm"] + merged["score_xgb"]) / 2.0
    merged["score_min"] = merged[["score_lgbm", "score_xgb"]].min(axis=1)
    merged["rank_sum"] = merged["rank_lgbm"] + merged["rank_xgb"]

    return merged.sort_values(
        ["score_mean", "score_min", "rank_sum"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def main(config_path: str = "configs/common/infer_intersection.yaml") -> pd.DataFrame:
    config = _load_yaml(config_path)
    lgbm_config = str(config.get("lgbm_config", "configs/common/infer_lgbm.yaml"))
    xgb_config = str(config.get("xgb_config", "configs/common/infer_xgb.yaml"))
    output_path = Path(config.get("output_path", "outputs/predictions/common/scan_predictions_intersection.csv"))
    top_n = int(config.get("top_n", 200))

    merged = merge_ranked_predictions(
        run_single_scan(lgbm_config),
        run_single_scan(xgb_config),
    )

    if top_n > 0:
        merged = merged.head(top_n).copy()

    latest_asof_date = str(merged["asof_date"].max()) if not merged.empty else None
    output_path = resolve_dated_output_path(output_path, latest_asof_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)
    print(f"intersection scan finished: {len(merged)} samples -> {output_path}")
    return merged


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run LGBM+XGB intersection scan and export top candidates.")
    parser.add_argument("--config", default="configs/common/infer_intersection.yaml", help="Path to intersection infer config yaml")
    args = parser.parse_args()
    main(config_path=args.config)
