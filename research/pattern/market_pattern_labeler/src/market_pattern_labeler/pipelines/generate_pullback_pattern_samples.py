from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from market_pattern_labeler.data.daily_loader import iter_daily_frames
from market_pattern_labeler.miners.type_n.phase2_pullback.positive import PullbackPatternConfig, PullbackPatternMiner


def _load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config must be a YAML mapping: {path}")
    return data


def generate_pullback_pattern_samples(
    data_dir: str | Path,
    output_csv: str | Path,
    config_path: str | Path | None = None,
    asof_date: str | None = None,
    latest_only: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    date_stride: int = 1,
) -> pd.DataFrame:
    """Generate independent Phase 2 pullback pattern samples from daily parquet files."""
    config = PullbackPatternConfig.from_dict(_load_yaml(config_path) if config_path else {})
    miner = PullbackPatternMiner(config)

    frames: list[pd.DataFrame] = []
    n_symbols = 0
    for ts_code, df in iter_daily_frames(data_dir):
        n_symbols += 1
        if n_symbols % 500 == 0:
            print(f"processed_symbols_progress={n_symbols}")
        if latest_only or asof_date:
            samples = miner.generate_sample_for_asof(ts_code, df, asof_date=asof_date)
        elif start_date or end_date:
            samples = miner.generate_samples_for_range(
                ts_code,
                df,
                start_date=start_date,
                end_date=end_date,
                date_stride=date_stride,
            )
        else:
            samples = miner.generate_samples(ts_code, df)
        if not samples.empty:
            frames.append(samples)

    if frames:
        out = pd.concat(frames, ignore_index=True)
        out = out.sort_values(["asof_date", "ts_code"], ascending=[False, True]).reset_index(drop=True)
    else:
        out = pd.DataFrame(columns=miner.output_columns)

    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    n_positive = int(out["label"].sum()) if "label" in out.columns and not out.empty else 0
    n_samples = len(out)
    n_negative = n_samples - n_positive
    positive_ratio = n_positive / n_samples if n_samples else 0.0
    print(f"processed_symbols={n_symbols}")
    print(f"samples={n_samples}")
    print(f"positive={n_positive}")
    print(f"negative={n_negative}")
    print(f"positive_ratio={positive_ratio:.4f}")
    print(f"output={output_path}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate independent Phase 2 pullback pattern samples.")
    parser.add_argument("--data-dir", required=True, help="Directory containing one parquet file per symbol.")
    parser.add_argument(
        "--config",
        default=None,
        help="Optional pullback pattern config YAML.",
    )
    parser.add_argument(
        "--output",
        default="outputs/pullback_pattern_samples.csv",
        help="Output samples CSV path.",
    )
    parser.add_argument("--asof-date", default=None, help="Generate one sample per symbol for this YYYY-MM-DD date.")
    parser.add_argument("--start-date", default=None, help="Generate samples from this YYYY-MM-DD date, inclusive.")
    parser.add_argument("--end-date", default=None, help="Generate samples through this YYYY-MM-DD date, inclusive.")
    parser.add_argument(
        "--date-stride",
        type=int,
        default=1,
        help="When generating a date range, keep every Nth eligible asof date per symbol.",
    )
    parser.add_argument(
        "--latest-only",
        action="store_true",
        help="Generate one sample per symbol using each symbol's latest available date.",
    )
    args = parser.parse_args()
    generate_pullback_pattern_samples(
        args.data_dir,
        args.output,
        args.config,
        asof_date=args.asof_date,
        latest_only=args.latest_only,
        start_date=args.start_date,
        end_date=args.end_date,
        date_stride=args.date_stride,
    )


if __name__ == "__main__":
    main()
