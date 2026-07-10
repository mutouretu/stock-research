"""Export CN flat daily parquet into one parquet file per A-share symbol."""

from __future__ import annotations

from pathlib import Path

from market_data_hub.markets.cn.pipelines.merge_daily_increment import (
    CN_DAILY_COLUMNS,
    MergeSummary,
    export_cn_daily_by_symbol,
)

DEFAULT_INPUT_PATH = Path("data/processed/cn/increments/daily_increment.parquet")
DEFAULT_OUTPUT_DIR = Path("../shared_data/raw/daily/parquet_daily_cache_cn")


def run(
    input_path: str | Path = DEFAULT_INPUT_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    overwrite: bool = False,
) -> MergeSummary:
    return export_cn_daily_by_symbol(
        input_path=input_path,
        output_dir=output_dir,
        overwrite=overwrite,
        columns=CN_DAILY_COLUMNS,
    )
