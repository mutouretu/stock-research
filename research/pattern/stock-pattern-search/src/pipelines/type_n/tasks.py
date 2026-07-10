from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import yaml

from src.inference.predictor import TabularPredictor
from src.pipelines.type_n.phase_tracking import (
    _anchor_dates_from_config,
    _build_features_for_date,
    _build_stock_resource_pool,
    _load_prepared_daily,
    _score_with_pair,
    _select_phase1_anchor_top,
)
from src.reviewers.type_n.phase1_breakout.penalties import apply_post_penalties


PHASE1_HIT_COLUMNS = [
    "target_date",
    "anchor_date",
    "ts_code",
    "sample_id",
    "phase1_rank",
    "phase1_score_lgbm",
    "phase1_score_xgb",
    "phase1_score_mean",
    "phase1_score_min",
]

PHASE1_POOL_COLUMNS = [
    "target_date",
    "ts_code",
    "first_phase1_date",
    "last_phase1_date",
    "phase1_hit_count",
    "phase1_seen_dates",
    "best_phase1_date",
    "best_phase1_score_mean",
    "latest_phase1_score_mean",
    "latest_phase1_rank",
    "pool_status",
]

PHASE2_SCORE_COLUMNS = [
    "target_date",
    "ts_code",
    "sample_id",
    "phase2_score_lgbm",
    "phase2_score_xgb",
    "phase2_score_mean",
    "phase2_score_min",
    "reviewer_config",
    "adjusted_phase2_score",
]

FINAL_CANDIDATE_COLUMNS = [
    "target_date",
    "ts_code",
    "first_phase1_date",
    "last_phase1_date",
    "phase1_hit_count",
    "best_phase1_score_mean",
    "latest_phase1_score_mean",
    "phase2_score_mean",
    "phase2_score_min",
    "final_score",
    "final_rank",
    "decision",
    "reason",
]


def run_phase1_scan_task(
    *,
    target_date: str,
    anchor_lookback_days: int,
    phase1_top_n: int,
    raw_daily_dir: str | Path,
    lgbm_model_dir: str | Path,
    xgb_model_dir: str | Path,
    output_path: str | Path,
    status_path: str | Path,
    phase1_reviewer_config: str | None = None,
    window_size: int = 150,
    min_history: int = 1,
    anchor_start_date: str | None = None,
) -> dict[str, Any]:
    raw_daily_dir = Path(raw_daily_dir)
    output_path = Path(output_path)
    status_path = Path(status_path)

    prepared, all_dates = _load_prepared_daily(raw_daily_dir)
    config: dict[str, Any] = {
        "target_date": target_date,
        "anchor_lookback_days": anchor_lookback_days,
    }
    if anchor_start_date:
        config["anchor_start_date"] = anchor_start_date
    anchor_dates = _anchor_dates_from_config(config, all_dates)

    predictors = SimpleNamespace(
        phase1_lgbm=TabularPredictor.from_dir(Path(lgbm_model_dir)),
        phase1_xgb=TabularPredictor.from_dir(Path(xgb_model_dir)),
    )

    frames: list[pd.DataFrame] = []
    warnings: list[str] = []
    for anchor_date in anchor_dates:
        try:
            top = _select_phase1_anchor_top_reviewed(
                prepared,
                predictors,
                anchor_date,
                phase1_top_n,
                window_size,
                min_history,
                raw_daily_dir=raw_daily_dir,
                phase1_reviewer_config=phase1_reviewer_config,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"phase1 scan skipped {anchor_date}: {exc}")
            continue
        top = top.copy()
        top["target_date"] = target_date
        top["anchor_date"] = top["asof_date"].astype(str)
        frames.append(top)

    hits = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=PHASE1_HIT_COLUMNS)
    if not hits.empty:
        hits = hits.sort_values(["anchor_date", "phase1_rank"]).reset_index(drop=True)
        ordered = [col for col in PHASE1_HIT_COLUMNS if col in hits.columns]
        ordered.extend(col for col in hits.columns if col not in ordered and col != "asof_date")
        hits = hits[ordered]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    hits.to_csv(output_path, index=False)

    status = {
        "ok": True,
        "status": "success" if not hits.empty else "empty",
        "target_date": target_date,
        "anchor_lookback_days": anchor_lookback_days,
        "anchor_start_date": anchor_start_date,
        "anchor_dates": anchor_dates,
        "phase1_top_n": phase1_top_n,
        "phase1_reviewer_config": phase1_reviewer_config,
        "phase1_hits_count": int(len(hits)),
        "output_path": str(output_path.resolve()),
        "warnings": warnings,
        "errors": [],
    }
    _write_json(status_path, status)
    return status


def run_phase1_cache_task(
    *,
    start_date: str,
    end_date: str,
    phase1_top_n: int,
    raw_daily_dir: str | Path,
    lgbm_model_dir: str | Path,
    xgb_model_dir: str | Path,
    output_path: str | Path,
    status_path: str | Path,
    phase1_reviewer_config: str | None = None,
    window_size: int = 150,
    min_history: int = 1,
) -> dict[str, Any]:
    raw_daily_dir = Path(raw_daily_dir)
    output_path = Path(output_path)
    status_path = Path(status_path)

    prepared, all_dates = _load_prepared_daily(raw_daily_dir)
    anchor_dates = [date for date in all_dates if start_date <= date <= end_date]
    if not anchor_dates:
        raise RuntimeError(f"No anchor dates available in range {start_date}..{end_date}")

    predictors = SimpleNamespace(
        phase1_lgbm=TabularPredictor.from_dir(Path(lgbm_model_dir)),
        phase1_xgb=TabularPredictor.from_dir(Path(xgb_model_dir)),
    )

    frames: list[pd.DataFrame] = []
    warnings: list[str] = []
    for anchor_date in anchor_dates:
        try:
            top = _select_phase1_anchor_top_reviewed(
                prepared,
                predictors,
                anchor_date,
                phase1_top_n,
                window_size,
                min_history,
                raw_daily_dir=raw_daily_dir,
                phase1_reviewer_config=phase1_reviewer_config,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"phase1 cache skipped {anchor_date}: {exc}")
            continue
        top = top.copy()
        top["anchor_date"] = top["asof_date"].astype(str)
        frames.append(top)

    cache = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=PHASE1_HIT_COLUMNS)
    if not cache.empty:
        cache = cache.sort_values(["anchor_date", "phase1_rank"]).reset_index(drop=True)
        ordered = [col for col in PHASE1_HIT_COLUMNS if col in cache.columns and col != "target_date"]
        ordered.extend(col for col in cache.columns if col not in ordered and col not in {"target_date", "asof_date"})
        cache = cache[ordered]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cache.to_csv(output_path, index=False)

    status = {
        "ok": True,
        "status": "success" if not cache.empty else "empty",
        "start_date": start_date,
        "end_date": end_date,
        "anchor_dates": anchor_dates,
        "phase1_top_n": phase1_top_n,
        "phase1_reviewer_config": phase1_reviewer_config,
        "phase1_cache_count": int(len(cache)),
        "output_path": str(output_path.resolve()),
        "warnings": warnings,
        "errors": [],
    }
    _write_json(status_path, status)
    return status


def _select_phase1_anchor_top_reviewed(
    prepared: dict[str, pd.DataFrame],
    predictors: Any,
    anchor_date: str,
    phase1_top_n: int,
    window_size: int,
    min_history: int,
    *,
    raw_daily_dir: Path,
    phase1_reviewer_config: str | None,
) -> pd.DataFrame:
    meta_df, feat_df = _build_features_for_date(prepared, anchor_date, window_size, min_history)
    if meta_df.empty:
        raise RuntimeError(f"No Phase1 predictable samples for anchor_date={anchor_date}")

    scored = _score_with_pair(meta_df, feat_df, predictors.phase1_lgbm, predictors.phase1_xgb, "phase1")
    reviewer_name = phase1_reviewer_config or ""
    sort_fields = ["phase1_score_mean", "phase1_score_min"]
    if reviewer_name:
        post_penalties = _load_reviewer_post_penalties(reviewer_name, raw_daily_dir)
        scored = apply_post_penalties(scored, post_penalties, Path.cwd())
        if "adjusted_phase1_score" in scored.columns:
            sort_fields = ["adjusted_phase1_score", "phase1_score_mean", "phase1_score_min"]

    scored = scored.sort_values(sort_fields, ascending=[False] * len(sort_fields)).reset_index(drop=True)
    top = scored.head(phase1_top_n).copy()
    top["phase1_rank"] = range(1, len(top) + 1)
    return top


def build_phase1_pool_task(
    *,
    phase1_hits_path: str | Path,
    output_path: str | Path,
    status_path: str | Path,
    target_date: str | None = None,
) -> dict[str, Any]:
    phase1_hits_path = Path(phase1_hits_path)
    output_path = Path(output_path)
    status_path = Path(status_path)
    hits = pd.read_csv(phase1_hits_path)

    if hits.empty:
        pool = pd.DataFrame(columns=PHASE1_POOL_COLUMNS)
    else:
        if "anchor_date" not in hits.columns:
            raise ValueError("phase1_hits.csv must contain anchor_date")
        if "asof_date" not in hits.columns:
            hits = hits.assign(asof_date=hits["anchor_date"].astype(str))
        if target_date is None and "target_date" in hits.columns:
            target_date = str(hits["target_date"].dropna().astype(str).iloc[0])
        pool = _build_stock_resource_pool(hits)
        pool = _normalize_phase1_pool(pool, target_date=target_date)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pool.to_csv(output_path, index=False)

    status = {
        "ok": True,
        "status": "success" if not pool.empty else "empty",
        "input_path": str(phase1_hits_path.resolve()),
        "output_path": str(output_path.resolve()),
        "phase1_hits_count": int(len(hits)),
        "phase1_pool_count": int(len(pool)),
        "warnings": [],
        "errors": [],
    }
    _write_json(status_path, status)
    return status


def build_phase1_pool_from_cache_task(
    *,
    phase1_cache_path: str | Path,
    target_date: str,
    anchor_lookback_days: int,
    raw_daily_dir: str | Path,
    hits_output_path: str | Path,
    pool_output_path: str | Path,
    status_path: str | Path,
    anchor_start_date: str | None = None,
    all_dates: list[str] | None = None,
) -> dict[str, Any]:
    phase1_cache_path = Path(phase1_cache_path)
    raw_daily_dir = Path(raw_daily_dir)
    hits_output_path = Path(hits_output_path)
    pool_output_path = Path(pool_output_path)
    status_path = Path(status_path)

    cache = pd.read_csv(phase1_cache_path)
    if all_dates is None:
        _, all_dates = _load_prepared_daily(raw_daily_dir)
    config: dict[str, Any] = {
        "target_date": target_date,
        "anchor_lookback_days": anchor_lookback_days,
    }
    if anchor_start_date:
        config["anchor_start_date"] = anchor_start_date
    anchor_dates = _anchor_dates_from_config(config, all_dates)

    if cache.empty:
        hits = pd.DataFrame(columns=PHASE1_HIT_COLUMNS)
    else:
        if "anchor_date" not in cache.columns:
            raise ValueError("phase1 cache must contain anchor_date")
        hits = cache[cache["anchor_date"].astype(str).isin(anchor_dates)].copy()
        if not hits.empty:
            hits["target_date"] = target_date
            if "asof_date" not in hits.columns:
                hits["asof_date"] = hits["anchor_date"].astype(str)
            hits = hits.sort_values(["anchor_date", "phase1_rank"]).reset_index(drop=True)
            ordered = [col for col in PHASE1_HIT_COLUMNS if col in hits.columns]
            ordered.extend(col for col in hits.columns if col not in ordered and col != "asof_date")
            hits = hits[ordered]

    if hits.empty:
        pool = pd.DataFrame(columns=PHASE1_POOL_COLUMNS)
    else:
        pool_hits = hits if "asof_date" in hits.columns else hits.assign(asof_date=hits["anchor_date"].astype(str))
        pool = _normalize_phase1_pool(_build_stock_resource_pool(pool_hits), target_date=target_date)

    hits_output_path.parent.mkdir(parents=True, exist_ok=True)
    pool_output_path.parent.mkdir(parents=True, exist_ok=True)
    hits.to_csv(hits_output_path, index=False)
    pool.to_csv(pool_output_path, index=False)

    missing_anchor_dates = sorted(set(anchor_dates) - set(cache.get("anchor_date", pd.Series(dtype=str)).astype(str)))
    warnings = [f"missing cached anchor_dates: {', '.join(missing_anchor_dates)}"] if missing_anchor_dates else []
    status = {
        "ok": True,
        "status": "success" if not pool.empty else "empty",
        "target_date": target_date,
        "anchor_lookback_days": anchor_lookback_days,
        "anchor_start_date": anchor_start_date,
        "anchor_dates": anchor_dates,
        "phase1_cache_path": str(phase1_cache_path.resolve()),
        "hits_output_path": str(hits_output_path.resolve()),
        "pool_output_path": str(pool_output_path.resolve()),
        "phase1_cache_count": int(len(cache)),
        "phase1_hits_count": int(len(hits)),
        "phase1_pool_count": int(len(pool)),
        "warnings": warnings,
        "errors": [],
    }
    _write_json(status_path, status)
    return status


def run_phase2_filter_task(
    *,
    target_date: str,
    phase1_pool_path: str | Path,
    raw_daily_dir: str | Path,
    lgbm_model_dir: str | Path,
    xgb_model_dir: str | Path,
    output_path: str | Path,
    status_path: str | Path,
    reviewer_config: str | None = None,
    window_size: int = 150,
    min_history: int = 1,
) -> dict[str, Any]:
    phase1_pool_path = Path(phase1_pool_path)
    raw_daily_dir = Path(raw_daily_dir)
    output_path = Path(output_path)
    status_path = Path(status_path)
    pool = pd.read_csv(phase1_pool_path)
    reviewer_name = reviewer_config or ""

    if pool.empty:
        scores = pd.DataFrame(columns=PHASE2_SCORE_COLUMNS)
    else:
        prepared, _ = _load_prepared_daily(raw_daily_dir)
        ts_codes = set(pool["ts_code"].astype(str))
        meta_df, feat_df = _build_features_for_date(
            prepared,
            target_date,
            window_size,
            min_history,
            ts_codes=ts_codes,
        )
        if meta_df.empty:
            scores = pd.DataFrame(columns=PHASE2_SCORE_COLUMNS)
        else:
            lgbm = TabularPredictor.from_dir(Path(lgbm_model_dir))
            xgb = TabularPredictor.from_dir(Path(xgb_model_dir))
            scores = _score_with_pair(meta_df, feat_df, lgbm, xgb, "phase2")
            scores["target_date"] = scores["asof_date"].astype(str)
            scores["reviewer_config"] = reviewer_name
            if reviewer_name:
                pool_context_cols = [
                    col
                    for col in [
                        "ts_code",
                        "first_phase1_date",
                        "last_phase1_date",
                        "best_phase1_date",
                        "phase1_hit_count",
                        "best_phase1_score_mean",
                    ]
                    if col in pool.columns
                ]
                if len(pool_context_cols) > 1:
                    scores = scores.merge(pool[pool_context_cols], on="ts_code", how="left")
                scores = _apply_reviewer_config(scores, reviewer_name, raw_daily_dir)
            if "adjusted_phase2_score" not in scores.columns:
                scores["adjusted_phase2_score"] = pd.NA

    if not scores.empty:
        primary = "adjusted_phase2_score" if scores["adjusted_phase2_score"].notna().any() else "phase2_score_mean"
        scores = scores.sort_values([primary, "phase2_score_mean", "phase2_score_min"], ascending=[False, False, False])
        scores = scores.reset_index(drop=True)
        ordered = [col for col in PHASE2_SCORE_COLUMNS if col in scores.columns]
        ordered.extend(col for col in scores.columns if col not in ordered and col != "asof_date")
        scores = scores[ordered]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(output_path, index=False)

    status = {
        "ok": True,
        "status": "success" if not scores.empty else "empty",
        "target_date": target_date,
        "phase1_pool_path": str(phase1_pool_path.resolve()),
        "output_path": str(output_path.resolve()),
        "phase1_pool_count": int(len(pool)),
        "phase2_scores_count": int(len(scores)),
        "reviewer_config": reviewer_name or None,
        "warnings": [],
        "errors": [],
    }
    _write_json(status_path, status)
    return status


def run_phase2_filter_prepared_task(
    *,
    prepared: dict[str, pd.DataFrame],
    target_date: str,
    phase1_pool_path: str | Path,
    raw_daily_dir: str | Path,
    lgbm_model_dir: str | Path,
    xgb_model_dir: str | Path,
    output_path: str | Path,
    status_path: str | Path,
    reviewer_config: str | None = None,
    window_size: int = 150,
    min_history: int = 1,
) -> dict[str, Any]:
    phase1_pool_path = Path(phase1_pool_path)
    raw_daily_dir = Path(raw_daily_dir)
    output_path = Path(output_path)
    status_path = Path(status_path)
    pool = pd.read_csv(phase1_pool_path)
    reviewer_name = reviewer_config or ""

    if pool.empty:
        scores = pd.DataFrame(columns=PHASE2_SCORE_COLUMNS)
    else:
        ts_codes = set(pool["ts_code"].astype(str))
        meta_df, feat_df = _build_features_for_date(
            prepared,
            target_date,
            window_size,
            min_history,
            ts_codes=ts_codes,
        )
        if meta_df.empty:
            scores = pd.DataFrame(columns=PHASE2_SCORE_COLUMNS)
        else:
            lgbm = TabularPredictor.from_dir(Path(lgbm_model_dir))
            xgb = TabularPredictor.from_dir(Path(xgb_model_dir))
            scores = _score_with_pair(meta_df, feat_df, lgbm, xgb, "phase2")
            scores["target_date"] = scores["asof_date"].astype(str)
            scores["reviewer_config"] = reviewer_name
            if reviewer_name:
                pool_context_cols = [
                    col
                    for col in [
                        "ts_code",
                        "first_phase1_date",
                        "last_phase1_date",
                        "best_phase1_date",
                        "phase1_hit_count",
                        "best_phase1_score_mean",
                    ]
                    if col in pool.columns
                ]
                if len(pool_context_cols) > 1:
                    scores = scores.merge(pool[pool_context_cols], on="ts_code", how="left")
                scores = _apply_reviewer_config(scores, reviewer_name, raw_daily_dir)
            if "adjusted_phase2_score" not in scores.columns:
                scores["adjusted_phase2_score"] = pd.NA

    if not scores.empty:
        primary = "adjusted_phase2_score" if scores["adjusted_phase2_score"].notna().any() else "phase2_score_mean"
        scores = scores.sort_values([primary, "phase2_score_mean", "phase2_score_min"], ascending=[False, False, False])
        scores = scores.reset_index(drop=True)
        ordered = [col for col in PHASE2_SCORE_COLUMNS if col in scores.columns]
        ordered.extend(col for col in scores.columns if col not in ordered and col != "asof_date")
        scores = scores[ordered]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(output_path, index=False)

    status = {
        "ok": True,
        "status": "success" if not scores.empty else "empty",
        "target_date": target_date,
        "phase1_pool_path": str(phase1_pool_path.resolve()),
        "output_path": str(output_path.resolve()),
        "phase1_pool_count": int(len(pool)),
        "phase2_scores_count": int(len(scores)),
        "reviewer_config": reviewer_name or None,
        "warnings": [],
        "errors": [],
    }
    _write_json(status_path, status)
    return status


def merge_final_candidates_task(
    *,
    phase1_pool_path: str | Path,
    phase2_scores_path: str | Path,
    output_path: str | Path,
    status_path: str | Path,
    final_merge_config: str | None = None,
    sort_fields: str | list[str] | None = None,
) -> dict[str, Any]:
    phase1_pool_path = Path(phase1_pool_path)
    phase2_scores_path = Path(phase2_scores_path)
    output_path = Path(output_path)
    status_path = Path(status_path)
    pool = pd.read_csv(phase1_pool_path)
    scores = pd.read_csv(phase2_scores_path)
    merge_name = final_merge_config or "default"
    requested_sort_fields = _parse_sort_fields(sort_fields)

    if pool.empty or scores.empty:
        final = pd.DataFrame(columns=FINAL_CANDIDATE_COLUMNS)
        applied_sort_fields: list[str] = []
    else:
        merged = pool.merge(scores, on="ts_code", how="inner", suffixes=("", "_phase2"))
        score_col = "adjusted_phase2_score"
        if score_col not in merged.columns or merged[score_col].isna().all():
            score_col = "phase2_score_mean"
        merged["final_score"] = pd.to_numeric(merged[score_col], errors="coerce")
        sort_columns = requested_sort_fields or _default_final_sort_fields(merge_name)
        applied_sort_fields = [field for field in sort_columns if field in merged.columns]
        if not applied_sort_fields:
            applied_sort_fields = ["final_score"]
        merged = merged.sort_values(applied_sort_fields, ascending=[False] * len(applied_sort_fields)).reset_index(drop=True)
        merged["final_rank"] = range(1, len(merged) + 1)
        merged["decision"] = "candidate"
        merged["reason"] = f"score_col={score_col}; ranked_by={','.join(applied_sort_fields)}; final_merge_config={merge_name}"
        if "target_date" not in merged.columns and "target_date_phase2" in merged.columns:
            merged["target_date"] = merged["target_date_phase2"]
        ordered = [col for col in FINAL_CANDIDATE_COLUMNS if col in merged.columns]
        ordered.extend(col for col in merged.columns if col not in ordered)
        final = merged[ordered]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.to_csv(output_path, index=False)

    status = {
        "ok": True,
        "status": "success" if not final.empty else "empty",
        "phase1_pool_path": str(phase1_pool_path.resolve()),
        "phase2_scores_path": str(phase2_scores_path.resolve()),
        "output_path": str(output_path.resolve()),
        "phase1_pool_count": int(len(pool)),
        "phase2_scores_count": int(len(scores)),
        "final_candidates_count": int(len(final)),
        "final_merge_config": merge_name,
        "sort_fields": applied_sort_fields,
        "warnings": [],
        "errors": [],
    }
    _write_json(status_path, status)
    return status


def _parse_sort_fields(sort_fields: str | list[str] | None) -> list[str]:
    if sort_fields is None:
        return []
    if isinstance(sort_fields, str):
        return [field.strip() for field in sort_fields.split(",") if field.strip()]
    return [str(field).strip() for field in sort_fields if str(field).strip()]


def _default_final_sort_fields(final_merge_config: str) -> list[str]:
    if final_merge_config == "fast_compatible":
        return ["phase2_score_mean", "phase2_score_min"]
    return ["final_score", "phase2_score_mean", "best_phase1_score_mean"]


def generate_two_phase_report_task(
    *,
    phase1_hits_path: str | Path,
    phase1_pool_path: str | Path,
    phase2_scores_path: str | Path,
    final_candidates_path: str | Path,
    status_paths: list[str | Path],
    output_path: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_path)
    statuses = [_read_json(Path(path)) for path in status_paths]
    hits = _read_csv_or_empty(phase1_hits_path)
    pool = _read_csv_or_empty(phase1_pool_path)
    scores = _read_csv_or_empty(phase2_scores_path)
    final = _read_csv_or_empty(final_candidates_path)

    phase1_status = statuses[0] if statuses else {}
    target_date = phase1_status.get("target_date") or _first_value(final, "target_date") or _first_value(scores, "target_date")
    warnings = _collect_status_values(statuses, "warnings")
    errors = _collect_status_values(statuses, "errors")

    lines = [
        "# Type-N Two Phase Report",
        "",
        f"- target_date: {target_date or ''}",
        f"- anchor_lookback_days: {phase1_status.get('anchor_lookback_days', '')}",
        f"- anchor_dates: {', '.join(map(str, phase1_status.get('anchor_dates', [])))}",
        f"- phase1_hits_count: {len(hits)}",
        f"- phase1_pool_count: {len(pool)}",
        f"- phase2_scores_count: {len(scores)}",
        f"- final_candidates_count: {len(final)}",
        "",
        "## Top 30 Final Candidates",
        "",
    ]
    if final.empty:
        lines.append("_No final candidates._")
    else:
        top_cols = [
            col
            for col in ["final_rank", "ts_code", "final_score", "phase2_score_mean", "best_phase1_score_mean", "decision"]
            if col in final.columns
        ]
        lines.append(_to_markdown_table(final.head(30)[top_cols]))

    lines.extend(["", "## Stage Outputs", ""])
    for path in [phase1_hits_path, phase1_pool_path, phase2_scores_path, final_candidates_path, *status_paths]:
        lines.append(f"- `{Path(path).resolve()}`")

    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {warning}" for warning in warnings] or ["- None"])
    lines.extend(["", "## Errors", ""])
    lines.extend([f"- {error}" for error in errors] or ["- None"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "ok": not errors,
        "status": "success" if not errors else "completed_with_errors",
        "output_path": str(output_path.resolve()),
        "warnings": warnings,
        "errors": errors,
    }


def _normalize_phase1_pool(pool: pd.DataFrame, *, target_date: str | None) -> pd.DataFrame:
    if pool.empty:
        return pd.DataFrame(columns=PHASE1_POOL_COLUMNS)
    out = pool.copy()
    out["target_date"] = target_date or out.get("target_date", "")
    out["first_phase1_date"] = out["pool_entry_date"].astype(str)
    out["last_phase1_date"] = out["last_seen_phase1_date"].astype(str)
    out["phase1_hit_count"] = out["phase1_seen_count"].astype(int)
    out["pool_status"] = "in_pool"
    if "name" not in out.columns:
        out["name"] = ""
    ordered = [
        "target_date",
        "ts_code",
        "name",
        "first_phase1_date",
        "last_phase1_date",
        "phase1_hit_count",
        "phase1_seen_dates",
        "best_phase1_date",
        "best_phase1_score_mean",
        "latest_phase1_score_mean",
        "latest_phase1_rank",
        "pool_status",
    ]
    ordered = [col for col in ordered if col in out.columns]
    ordered.extend(col for col in out.columns if col not in ordered)
    return out[ordered].reset_index(drop=True)


def _apply_reviewer_config(scores: pd.DataFrame, reviewer_config: str, raw_daily_dir: Path) -> pd.DataFrame:
    post_penalties = _load_reviewer_post_penalties(reviewer_config, raw_daily_dir)
    if not post_penalties:
        return scores
    return apply_post_penalties(scores, post_penalties, Path.cwd())


def _load_reviewer_post_penalties(reviewer_config: str, raw_daily_dir: Path) -> dict[str, Any]:
    if reviewer_config in {"", "none", "default"}:
        return {}
    path = Path(reviewer_config)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        if not isinstance(cfg, dict):
            return {}
        post_penalties = cfg.get("post_penalties", cfg)
        return post_penalties if isinstance(post_penalties, dict) else {}
    if reviewer_config == "ma120_trend_soft":
        return {
            "midlong_trend": {
                "enabled": True,
                "raw_data_dir": str(raw_daily_dir.resolve()),
                "short_window": 20,
                "mid_window": 120,
                "long_window": 250,
                "slope_lag": 60,
                "return_window": 120,
                "position_window": 120,
                "min_return": 0.0,
                "min_mid_ma_slope": 0.0,
                "min_position": 0.45,
                "require_above_mid_ma": True,
                "threshold": 0.0,
                "sharpness": 80,
                "min_factor": 0.25,
                "max_factor": 1.75,
                "score_col": "phase2_score_mean",
                "output_score_col": "adjusted_phase2_score",
            }
        }
    raise ValueError(f"unknown reviewer_config: {reviewer_config}")


def _read_csv_or_empty(path: str | Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "missing", "warnings": [], "errors": [f"failed to read {path}: {exc}"]}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _collect_status_values(statuses: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for status in statuses:
        raw = status.get(key, [])
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item)
        elif raw:
            values.append(str(raw))
    return list(dict.fromkeys(values))


def _first_value(df: pd.DataFrame, column: str) -> str | None:
    if column not in df.columns or df.empty:
        return None
    values = df[column].dropna().astype(str)
    return None if values.empty else str(values.iloc[0])


def _to_markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    headers = [str(col) for col in df.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for _, row in df.iterrows():
        values = [str(row[col]) for col in df.columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)
