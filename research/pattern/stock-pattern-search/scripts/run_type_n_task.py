from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipelines.type_n.tasks import (  # noqa: E402
    build_phase1_pool_from_cache_task,
    build_phase1_pool_task,
    generate_two_phase_report_task,
    merge_final_candidates_task,
    run_phase1_cache_task,
    run_phase1_scan_task,
    run_phase2_filter_task,
)


DEFAULT_RAW_DAILY_DIR = PROJECT_ROOT.parent / "shared_data" / "raw" / "daily" / "parquet_daily_cache"
DEFAULT_PHASE1_LGBM = PROJECT_ROOT / "outputs" / "models" / "type_n" / "phase1_breakout" / "lgbm_v5_no_runupscore7_w150"
DEFAULT_PHASE1_XGB = PROJECT_ROOT / "outputs" / "models" / "type_n" / "phase1_breakout" / "xgb_v5_no_runupscore7_w150"
DEFAULT_PHASE2_LGBM = PROJECT_ROOT / "outputs" / "models" / "type_n" / "phase2_pullback" / "lgbm_fastdrop_15k_w150"
DEFAULT_PHASE2_XGB = PROJECT_ROOT / "outputs" / "models" / "type_n" / "phase2_pullback" / "xgb_fastdrop_15k_w150"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run decomposed Type-N two-phase strategy tasks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    phase1 = subparsers.add_parser("phase1-scan", help="Batch scan anchor dates with Phase1 models.")
    phase1.add_argument("--target-date", required=True)
    phase1.add_argument("--anchor-lookback-days", type=int, default=20)
    phase1.add_argument("--anchor-start-date", default=None)
    phase1.add_argument("--phase1-top-n", type=int, default=20)
    phase1.add_argument("--raw-daily-dir", default=str(DEFAULT_RAW_DAILY_DIR))
    phase1.add_argument("--phase1-lgbm-model-dir", default=str(DEFAULT_PHASE1_LGBM))
    phase1.add_argument("--phase1-xgb-model-dir", default=str(DEFAULT_PHASE1_XGB))
    phase1.add_argument("--window-size", type=int, default=150)
    phase1.add_argument("--min-history", type=int, default=1)
    phase1.add_argument("--output-path", required=True)
    phase1.add_argument("--status-path", required=True)
    phase1.add_argument("--phase1-reviewer-config", default=None)
    phase1.set_defaults(func=_phase1_scan)

    phase1_cache = subparsers.add_parser("phase1-cache", help="Cache Phase1 top hits for each anchor date in a date range.")
    phase1_cache.add_argument("--start-date", required=True)
    phase1_cache.add_argument("--end-date", required=True)
    phase1_cache.add_argument("--phase1-top-n", type=int, default=20)
    phase1_cache.add_argument("--raw-daily-dir", default=str(DEFAULT_RAW_DAILY_DIR))
    phase1_cache.add_argument("--phase1-lgbm-model-dir", default=str(DEFAULT_PHASE1_LGBM))
    phase1_cache.add_argument("--phase1-xgb-model-dir", default=str(DEFAULT_PHASE1_XGB))
    phase1_cache.add_argument("--window-size", type=int, default=150)
    phase1_cache.add_argument("--min-history", type=int, default=1)
    phase1_cache.add_argument("--output-path", required=True)
    phase1_cache.add_argument("--status-path", required=True)
    phase1_cache.add_argument("--phase1-reviewer-config", default=None)
    phase1_cache.set_defaults(func=_phase1_cache)

    pool = subparsers.add_parser("build-pool", help="Aggregate phase1 hits into a stock-level pool.")
    pool.add_argument("--phase1-hits-path", required=True)
    pool.add_argument("--target-date", default=None)
    pool.add_argument("--output-path", required=True)
    pool.add_argument("--status-path", required=True)
    pool.set_defaults(func=_build_pool)

    cached_pool = subparsers.add_parser("build-pool-from-cache", help="Build target-date Phase1 hits and pool from a Phase1 cache.")
    cached_pool.add_argument("--phase1-cache-path", required=True)
    cached_pool.add_argument("--target-date", required=True)
    cached_pool.add_argument("--anchor-lookback-days", type=int, default=5)
    cached_pool.add_argument("--anchor-start-date", default=None)
    cached_pool.add_argument("--raw-daily-dir", default=str(DEFAULT_RAW_DAILY_DIR))
    cached_pool.add_argument("--hits-output-path", required=True)
    cached_pool.add_argument("--pool-output-path", required=True)
    cached_pool.add_argument("--status-path", required=True)
    cached_pool.set_defaults(func=_build_pool_from_cache)

    phase2 = subparsers.add_parser("phase2-filter", help="Score phase1 pool with Phase2 models.")
    phase2.add_argument("--target-date", required=True)
    phase2.add_argument("--phase1-pool-path", required=True)
    phase2.add_argument("--raw-daily-dir", default=str(DEFAULT_RAW_DAILY_DIR))
    phase2.add_argument("--phase2-lgbm-model-dir", default=str(DEFAULT_PHASE2_LGBM))
    phase2.add_argument("--phase2-xgb-model-dir", default=str(DEFAULT_PHASE2_XGB))
    phase2.add_argument("--reviewer-config", default=None)
    phase2.add_argument("--window-size", type=int, default=150)
    phase2.add_argument("--min-history", type=int, default=1)
    phase2.add_argument("--output-path", required=True)
    phase2.add_argument("--status-path", required=True)
    phase2.set_defaults(func=_phase2_filter)

    merge = subparsers.add_parser("merge-final", help="Merge pool and phase2 scores into final candidates.")
    merge.add_argument("--phase1-pool-path", required=True)
    merge.add_argument("--phase2-scores-path", required=True)
    merge.add_argument("--final-merge-config", default="default")
    merge.add_argument("--sort-fields", default=None)
    merge.add_argument("--output-path", required=True)
    merge.add_argument("--status-path", required=True)
    merge.set_defaults(func=_merge_final)

    report = subparsers.add_parser("report", help="Generate a Markdown two-phase report.")
    report.add_argument("--phase1-hits-path", required=True)
    report.add_argument("--phase1-pool-path", required=True)
    report.add_argument("--phase2-scores-path", required=True)
    report.add_argument("--final-candidates-path", required=True)
    report.add_argument("--status-path", action="append", default=[])
    report.add_argument("--output-path", required=True)
    report.set_defaults(func=_report)

    args = parser.parse_args()
    try:
        result = args.func(args)
    except Exception as exc:  # noqa: BLE001
        _write_failure_status(args, exc)
        raise
    print(json.dumps(result, ensure_ascii=False, default=str))


def _phase1_scan(args: argparse.Namespace) -> dict[str, Any]:
    return run_phase1_scan_task(
        target_date=args.target_date,
        anchor_lookback_days=args.anchor_lookback_days,
        anchor_start_date=args.anchor_start_date,
        phase1_top_n=args.phase1_top_n,
        raw_daily_dir=args.raw_daily_dir,
        lgbm_model_dir=args.phase1_lgbm_model_dir,
        xgb_model_dir=args.phase1_xgb_model_dir,
        output_path=args.output_path,
        status_path=args.status_path,
        phase1_reviewer_config=args.phase1_reviewer_config,
        window_size=args.window_size,
        min_history=args.min_history,
    )


def _phase1_cache(args: argparse.Namespace) -> dict[str, Any]:
    return run_phase1_cache_task(
        start_date=args.start_date,
        end_date=args.end_date,
        phase1_top_n=args.phase1_top_n,
        raw_daily_dir=args.raw_daily_dir,
        lgbm_model_dir=args.phase1_lgbm_model_dir,
        xgb_model_dir=args.phase1_xgb_model_dir,
        output_path=args.output_path,
        status_path=args.status_path,
        phase1_reviewer_config=args.phase1_reviewer_config,
        window_size=args.window_size,
        min_history=args.min_history,
    )


def _build_pool(args: argparse.Namespace) -> dict[str, Any]:
    return build_phase1_pool_task(
        phase1_hits_path=args.phase1_hits_path,
        output_path=args.output_path,
        status_path=args.status_path,
        target_date=args.target_date,
    )


def _build_pool_from_cache(args: argparse.Namespace) -> dict[str, Any]:
    return build_phase1_pool_from_cache_task(
        phase1_cache_path=args.phase1_cache_path,
        target_date=args.target_date,
        anchor_lookback_days=args.anchor_lookback_days,
        anchor_start_date=args.anchor_start_date,
        raw_daily_dir=args.raw_daily_dir,
        hits_output_path=args.hits_output_path,
        pool_output_path=args.pool_output_path,
        status_path=args.status_path,
    )


def _phase2_filter(args: argparse.Namespace) -> dict[str, Any]:
    return run_phase2_filter_task(
        target_date=args.target_date,
        phase1_pool_path=args.phase1_pool_path,
        raw_daily_dir=args.raw_daily_dir,
        lgbm_model_dir=args.phase2_lgbm_model_dir,
        xgb_model_dir=args.phase2_xgb_model_dir,
        output_path=args.output_path,
        status_path=args.status_path,
        reviewer_config=args.reviewer_config,
        window_size=args.window_size,
        min_history=args.min_history,
    )


def _merge_final(args: argparse.Namespace) -> dict[str, Any]:
    return merge_final_candidates_task(
        phase1_pool_path=args.phase1_pool_path,
        phase2_scores_path=args.phase2_scores_path,
        output_path=args.output_path,
        status_path=args.status_path,
        final_merge_config=args.final_merge_config,
        sort_fields=args.sort_fields,
    )


def _report(args: argparse.Namespace) -> dict[str, Any]:
    return generate_two_phase_report_task(
        phase1_hits_path=args.phase1_hits_path,
        phase1_pool_path=args.phase1_pool_path,
        phase2_scores_path=args.phase2_scores_path,
        final_candidates_path=args.final_candidates_path,
        status_paths=args.status_path,
        output_path=args.output_path,
    )


def _write_failure_status(args: argparse.Namespace, exc: Exception) -> None:
    status_path = getattr(args, "status_path", None)
    if not status_path or isinstance(status_path, list):
        return
    payload = {
        "ok": False,
        "status": "failed",
        "command": getattr(args, "command", ""),
        "warnings": [],
        "errors": [str(exc)],
    }
    path = Path(status_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
