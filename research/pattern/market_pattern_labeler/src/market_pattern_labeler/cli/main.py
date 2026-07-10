from __future__ import annotations

import argparse

from market_pattern_labeler.labels.build_ml_labels import build_ml_labels
from market_pattern_labeler.pipelines.check_data_dir import check_data_dir
from market_pattern_labeler.pipelines.run_miner import run_miner
from market_pattern_labeler.review.plot_candidates import plot_candidates_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Market pattern labeler CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run-miner", help="Run candidate miner over daily parquet data")
    run_parser.add_argument("--miner", required=True, help="Miner name, e.g. type_n")
    run_parser.add_argument("--data-dir", required=True, help="Directory with per-symbol parquet files")
    run_parser.add_argument("--config", default=None, help="Optional miner config yaml path")
    run_parser.add_argument("--output", required=True, help="Output CSV path")
    run_parser.add_argument("--symbols", default=None, help="Optional comma-separated symbols to scan")

    check_parser = subparsers.add_parser("check-data-dir", help="Check daily parquet data directory")
    check_parser.add_argument("--data-dir", required=True, help="Directory with per-symbol parquet files")
    check_parser.add_argument("--max-files", type=int, default=20, help="Max files to inspect; 0 means all")

    plot_parser = subparsers.add_parser("plot-candidates", help="Plot candidate charts for manual review")
    plot_parser.add_argument("--candidates", default="outputs/w_bottom/candidates/us_w_bottom_candidates.csv", help="Candidate CSV path")
    plot_parser.add_argument(
        "--data-dir",
        default="../shared_data/us/raw/daily/parquet_by_symbol",
        help="Directory with per-symbol parquet files",
    )
    plot_parser.add_argument("--output-dir", default="outputs/w_bottom/charts/candidate_charts", help="Chart output directory")
    plot_parser.add_argument("--stage", default=None, help="Optional pattern_stage filter")
    plot_parser.add_argument("--top-n", type=int, default=100, help="Number of candidates to plot")
    plot_parser.add_argument(
        "--sample",
        choices=["top", "random", "year_stratified"],
        default="top",
        help="Candidate sampling mode",
    )
    plot_parser.add_argument("--random-seed", type=int, default=42, help="Random seed for random sampling")
    plot_parser.add_argument("--pre-days", type=int, default=1260, help="Trading days before chart anchor to plot")
    plot_parser.add_argument("--post-days", type=int, default=90, help="Trading days after chart anchor to plot")
    plot_parser.add_argument(
        "--anchor",
        choices=["breakout", "asof"],
        default="breakout",
        help="Chart anchor date: first neckline breakout after right bottom, or candidate asof_date",
    )
    plot_parser.add_argument("--score-column", default="candidate_score", help="Score column for top sampling")
    plot_parser.add_argument("--format", default="png", help="Output image format")

    labels_parser = subparsers.add_parser("build-ml-labels", help="Build ML labels from mined candidates")
    labels_parser.add_argument(
        "--positive-candidates",
        default="outputs/w_bottom/candidates/us_long_base_breakout_candidates.csv",
        help="Positive candidates CSV path",
    )
    labels_parser.add_argument(
        "--data-dir",
        default="../shared_data/us/raw/daily/parquet_by_symbol",
        help="Directory with per-symbol parquet files",
    )
    labels_parser.add_argument(
        "--output",
        default="outputs/w_bottom/labels/labels_long_base_breakout.csv",
        help="Output labels CSV path",
    )
    labels_parser.add_argument(
        "--report",
        default=None,
        help="Optional report Markdown path; defaults to <output_stem>_report.md",
    )
    labels_parser.add_argument("--negative-ratio", type=float, default=3.0, help="Negative / positive sample ratio")
    labels_parser.add_argument(
        "--positive-exclusion-days",
        type=int,
        default=60,
        help="Exclude negative samples within +/- this many calendar days of positives",
    )
    labels_parser.add_argument(
        "--max-negative-per-symbol",
        type=int,
        default=50,
        help="Maximum negative samples per symbol",
    )
    labels_parser.add_argument("--train-end", default="2022-12-31", help="Train split end date")
    labels_parser.add_argument("--valid-end", default="2024-12-31", help="Validation split end date")
    labels_parser.add_argument(
        "--min-asof-date",
        default=None,
        help="Optional minimum asof_date for positive and negative labels",
    )
    labels_parser.add_argument("--random-seed", type=int, default=42, help="Random seed for negative sampling")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run-miner":
        run_miner(
            data_dir=args.data_dir,
            output_csv=args.output,
            miner_name=args.miner,
            config_path=args.config,
            symbols=args.symbols,
        )
    elif args.command == "check-data-dir":
        summary = check_data_dir(data_dir=args.data_dir, max_files=args.max_files)
        print(summary.summary_text())
    elif args.command == "plot-candidates":
        summary = plot_candidates_batch(
            candidates_path=args.candidates,
            data_dir=args.data_dir,
            output_dir=args.output_dir,
            stage=args.stage,
            top_n=args.top_n,
            sample=args.sample,
            random_seed=args.random_seed,
            pre_days=args.pre_days,
            post_days=args.post_days,
            score_column=args.score_column,
            image_format=args.format,
            anchor=args.anchor,
        )
        print(summary.summary_text())
    elif args.command == "build-ml-labels":
        summary = build_ml_labels(
            positive_candidates=args.positive_candidates,
            data_dir=args.data_dir,
            output=args.output,
            report=args.report,
            negative_ratio=args.negative_ratio,
            positive_exclusion_days=args.positive_exclusion_days,
            max_negative_per_symbol=args.max_negative_per_symbol,
            train_end=args.train_end,
            valid_end=args.valid_end,
            min_asof_date=args.min_asof_date,
            random_seed=args.random_seed,
        )
        print(summary.summary_text())


if __name__ == "__main__":
    main()
