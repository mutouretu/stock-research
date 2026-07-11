from __future__ import annotations

import argparse
import sys
import tempfile
import warnings
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipelines.run_scan import main as run_scan_main
from src.common.paths import get_shared_daily_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Compatibility wrapper for external Type-N agents.")
    parser.add_argument("--date", default=None, help="Trade date, for example 2026-05-12.")
    parser.add_argument("--asof-date", default=None, help="Alias for --date.")
    parser.add_argument("--output", default=None, help="Output candidates CSV path.")
    parser.add_argument("--output-path", default=None, help="Alias for --output.")
    parser.add_argument("--raw-daily-dir", default=None, help="Daily parquet directory.")
    parser.add_argument("--model-dir", default=None, help="Model directory.")
    parser.add_argument("--window-size", type=int, default=120)
    parser.add_argument("--min-history", type=int, default=160)
    args = parser.parse_args()

    trade_date = args.date or args.asof_date
    output_path = args.output or args.output_path
    if not trade_date:
        raise SystemExit("--date or --asof-date is required")
    if not output_path:
        raise SystemExit("--output or --output-path is required")

    config = {
        "raw_daily_dir": str(_resolve_raw_daily_dir(args.raw_daily_dir)),
        "model_dir": str(_resolve_model_dir(args.model_dir)),
        "output_path": str(Path(output_path).resolve()),
        "window_size": args.window_size,
        "min_history": args.min_history,
        "asof_date": trade_date,
    }

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False)
        config_path = f.name

    try:
        run_scan_main(config_path=config_path)
    finally:
        Path(config_path).unlink(missing_ok=True)


def _resolve_raw_daily_dir(raw_daily_dir: str | None) -> Path:
    if raw_daily_dir:
        return Path(raw_daily_dir).expanduser().resolve()

    candidates = [
        get_shared_daily_dir(),
        get_shared_daily_dir("parquet_daily_cache_5-12"),
        PROJECT_ROOT / "data" / "raw" / "daily",
    ]
    for candidate in candidates:
        if candidate.exists():
            if candidate.name == "parquet_daily_cache_5-12":
                warnings.warn(
                    f"Using legacy daily cache directory for compatibility only: {candidate.resolve()}",
                    stacklevel=2,
                )
            return candidate.resolve()
    return candidates[0].resolve()


def _resolve_model_dir(model_dir: str | None) -> Path:
    if model_dir:
        return Path(model_dir).expanduser().resolve()

    candidates = [
        PROJECT_ROOT / "outputs" / "models" / "type_n" / "phase2_pullback" / "lr_fastdrop_15k_w150",
        PROJECT_ROOT / "outputs" / "models" / "type_n" / "phase2_pullback" / "lr_2025q4_balanced_w150",
        PROJECT_ROOT / "outputs" / "models" / "type_n" / "phase2_pullback" / "lr_simple_10k_w150",
        PROJECT_ROOT / "outputs" / "models" / "common" / "baseline_lr_v4",
    ]
    for candidate in candidates:
        if (candidate / "model.pkl").exists():
            return candidate.resolve()
    return candidates[0].resolve()


if __name__ == "__main__":
    main()
