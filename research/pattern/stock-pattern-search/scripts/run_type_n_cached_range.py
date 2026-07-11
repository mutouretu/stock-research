from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipelines.type_n.phase_tracking import _load_prepared_daily  # noqa: E402
from src.common.paths import get_shared_daily_dir  # noqa: E402
from src.pipelines.type_n.tasks import (  # noqa: E402
    build_phase1_pool_from_cache_task,
    generate_two_phase_report_task,
    merge_final_candidates_task,
    run_phase2_filter_prepared_task,
)


DEFAULT_RAW_DAILY_DIR = get_shared_daily_dir()
DEFAULT_PHASE2_LGBM = PROJECT_ROOT / "outputs" / "models" / "type_n" / "phase2_pullback" / "lgbm_fastdrop_15k_w150"
DEFAULT_PHASE2_XGB = PROJECT_ROOT / "outputs" / "models" / "type_n" / "phase2_pullback" / "xgb_fastdrop_15k_w150"


def _dated_csv_name(target_date: str, stem: str) -> str:
    return f"{target_date}_{stem}.csv"


def _summary_csv_name(start_date: str, end_date: str) -> str:
    if start_date == end_date:
        return _dated_csv_name(start_date, "range_summary")
    return f"{start_date}_{end_date}_range_summary.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Type-N Phase2 range jobs from a cached Phase1 anchor file.")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--phase1-cache-path", required=True)
    parser.add_argument("--raw-daily-dir", default=str(DEFAULT_RAW_DAILY_DIR))
    parser.add_argument("--phase2-lgbm-model-dir", default=str(DEFAULT_PHASE2_LGBM))
    parser.add_argument("--phase2-xgb-model-dir", default=str(DEFAULT_PHASE2_XGB))
    parser.add_argument("--phase2-reviewer-config", default=None)
    parser.add_argument("--anchor-lookback-days", type=int, default=5)
    parser.add_argument("--window-size", type=int, default=150)
    parser.add_argument("--min-history", type=int, default=1)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    raw_daily_dir = Path(args.raw_daily_dir)
    prepared, all_dates = _load_prepared_daily(raw_daily_dir)
    target_dates = [date for date in all_dates if args.start_date <= date <= args.end_date]
    if not target_dates:
        raise RuntimeError(f"No target dates available in range {args.start_date}..{args.end_date}")

    output_dir = Path(args.output_dir)
    results: list[dict[str, Any]] = []
    for target_date in target_dates:
        day_dir = output_dir / target_date
        status_dir = day_dir / "status"
        final_path = day_dir / _dated_csv_name(target_date, "final_candidates")
        if args.skip_existing and final_path.exists():
            results.append({"target_date": target_date, "status": "skipped_existing", "final_candidates_path": str(final_path)})
            continue

        hits_path = day_dir / _dated_csv_name(target_date, "phase1_hits")
        pool_path = day_dir / _dated_csv_name(target_date, "phase1_pool")
        phase2_path = day_dir / _dated_csv_name(target_date, "phase2_scores")
        report_path = day_dir / "report.md"

        pool_status = build_phase1_pool_from_cache_task(
            phase1_cache_path=args.phase1_cache_path,
            target_date=target_date,
            anchor_lookback_days=args.anchor_lookback_days,
            raw_daily_dir=raw_daily_dir,
            hits_output_path=hits_path,
            pool_output_path=pool_path,
            status_path=status_dir / "pool_status.json",
            all_dates=all_dates,
        )
        phase2_status = run_phase2_filter_prepared_task(
            prepared=prepared,
            target_date=target_date,
            phase1_pool_path=pool_path,
            raw_daily_dir=raw_daily_dir,
            lgbm_model_dir=args.phase2_lgbm_model_dir,
            xgb_model_dir=args.phase2_xgb_model_dir,
            output_path=phase2_path,
            status_path=status_dir / "phase2_status.json",
            reviewer_config=args.phase2_reviewer_config,
            window_size=args.window_size,
            min_history=args.min_history,
        )
        final_status = merge_final_candidates_task(
            phase1_pool_path=pool_path,
            phase2_scores_path=phase2_path,
            output_path=final_path,
            status_path=status_dir / "final_status.json",
        )
        report_status = generate_two_phase_report_task(
            phase1_hits_path=hits_path,
            phase1_pool_path=pool_path,
            phase2_scores_path=phase2_path,
            final_candidates_path=final_path,
            status_paths=[status_dir / "pool_status.json", status_dir / "phase2_status.json", status_dir / "final_status.json"],
            output_path=report_path,
        )
        results.append(
            {
                "target_date": target_date,
                "phase1_hits_count": pool_status.get("phase1_hits_count", 0),
                "phase1_pool_count": pool_status.get("phase1_pool_count", 0),
                "phase2_scores_count": phase2_status.get("phase2_scores_count", 0),
                "final_candidates_count": final_status.get("final_candidates_count", 0),
                "report_ok": report_status.get("ok", False),
                "final_candidates_path": str(final_path),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(results)
    summary_path = output_dir / _summary_csv_name(args.start_date, args.end_date)
    summary.to_csv(summary_path, index=False)
    print(json.dumps({"ok": True, "target_dates_count": len(target_dates), "summary_path": str(summary_path.resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
