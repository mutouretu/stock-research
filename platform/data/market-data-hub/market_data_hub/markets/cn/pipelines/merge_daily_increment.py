"""Merge CN flat daily increment parquet into per-symbol shared-data snapshots."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd

CN_DAILY_COLUMNS = [
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount",
    "pct_chg",
    "ma_bfq_20",
    "ma_bfq_60",
    "ma_bfq_250",
    "cost_5pct",
    "cost_15pct",
    "cost_50pct",
    "cost_85pct",
    "cost_95pct",
    "weight_avg",
    "winner_rate",
]


@dataclass(frozen=True)
class MergeSummary:
    base_dir: Path
    increment_path: Path
    output_dir: Path
    base_symbols: int
    increment_symbols: int
    output_symbols: int
    output_rows: int
    failed_symbols: dict[str, str] = field(default_factory=dict)

    def summary_text(self) -> str:
        return "\n".join(
            [
                "CN daily increment merge summary",
                f"base_dir: {self.base_dir}",
                f"increment: {self.increment_path}",
                f"base_symbols: {self.base_symbols}",
                f"increment_symbols: {self.increment_symbols}",
                f"output_symbols: {self.output_symbols}",
                f"output_rows: {self.output_rows}",
                f"failed_symbols: {len(self.failed_symbols)}",
                f"output_dir: {self.output_dir}",
                f"failed_examples: {', '.join(list(self.failed_symbols)[:20]) or 'none'}",
            ]
        )


def merge_cn_daily_increment(
    *,
    base_dir: str | Path,
    increment_path: str | Path,
    output_dir: str | Path,
    overwrite: bool = False,
    columns: Iterable[str] = CN_DAILY_COLUMNS,
) -> MergeSummary:
    base = Path(base_dir)
    increment = Path(increment_path)
    destination = Path(output_dir)
    if not base.exists():
        raise FileNotFoundError(f"base_dir not found: {base}")
    if not increment.exists():
        raise FileNotFoundError(f"increment_path not found: {increment}")
    if destination.exists():
        if not overwrite:
            raise FileExistsError(f"output_dir already exists: {destination}")
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    column_list = list(columns)
    increments = split_increment_by_symbol(increment, column_list)
    base_files = {path.stem: path for path in base.glob("*.parquet")}
    all_symbols = sorted(set(base_files) | set(increments))

    rows = 0
    exported = 0
    failed: dict[str, str] = {}
    for ts_code in all_symbols:
        try:
            frames: list[pd.DataFrame] = []
            base_path = base_files.get(ts_code)
            if base_path is not None:
                frames.append(normalize_symbol_daily(pd.read_parquet(base_path)))
            if ts_code in increments:
                frames.append(normalize_symbol_daily(increments[ts_code]))
            if not frames:
                continue

            merged = pd.concat(frames, ignore_index=True)
            merged = merged.drop_duplicates(subset=["trade_date"], keep="last")
            keep = [column for column in column_list if column in merged.columns]
            merged = merged[keep].sort_values("trade_date").reset_index(drop=True)
            merged.to_parquet(destination / f"{ts_code}.parquet", index=False)
            rows += len(merged)
            exported += 1
        except Exception as exc:
            failed[ts_code] = str(exc)

    return MergeSummary(
        base_dir=base,
        increment_path=increment,
        output_dir=destination,
        base_symbols=len(base_files),
        increment_symbols=len(increments),
        output_symbols=exported,
        output_rows=rows,
        failed_symbols=failed,
    )


def export_cn_daily_by_symbol(
    *,
    input_path: str | Path,
    output_dir: str | Path,
    overwrite: bool = False,
    columns: Iterable[str] = CN_DAILY_COLUMNS,
) -> MergeSummary:
    """Export a flat CN parquet directly into one parquet file per symbol."""

    source = Path(input_path)
    destination = Path(output_dir)
    if not source.exists():
        raise FileNotFoundError(f"input_path not found: {source}")
    if destination.exists():
        if not overwrite:
            raise FileExistsError(f"output_dir already exists: {destination}")
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    column_list = list(columns)
    increments = split_increment_by_symbol(source, column_list)
    rows = 0
    failed: dict[str, str] = {}
    exported = 0
    for ts_code, frame in increments.items():
        try:
            output = normalize_symbol_daily(frame)
            keep = [column for column in column_list if column in output.columns]
            output = output[keep].sort_values("trade_date").reset_index(drop=True)
            output.to_parquet(destination / f"{ts_code}.parquet", index=False)
            rows += len(output)
            exported += 1
        except Exception as exc:
            failed[ts_code] = str(exc)

    return MergeSummary(
        base_dir=Path(""),
        increment_path=source,
        output_dir=destination,
        base_symbols=0,
        increment_symbols=len(increments),
        output_symbols=exported,
        output_rows=rows,
        failed_symbols=failed,
    )


def split_increment_by_symbol(
    increment_path: Path,
    columns: list[str],
) -> dict[str, pd.DataFrame]:
    raw = pd.read_parquet(increment_path)
    daily = normalize_cn_daily_flat(raw)
    keep = [column for column in columns if column in daily.columns]
    if "trade_date" not in keep:
        raise ValueError("increment data missing trade_date")

    by_symbol: dict[str, pd.DataFrame] = {}
    for ts_code, group in daily.groupby("ts_code", sort=False):
        output = group.sort_values("trade_date").reset_index(drop=True)
        output = output[keep].copy()
        output["trade_date"] = pd.to_datetime(
            output["trade_date"],
            format="%Y%m%d",
            errors="coerce",
        )
        output = output[output["trade_date"].notna()].copy()
        by_symbol[str(ts_code)] = output.reset_index(drop=True)
    return by_symbol


def normalize_cn_daily_flat(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    required = ["ts_code", "trade_date"]
    missing = [column for column in required if column not in output.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    output["ts_code"] = output["ts_code"].astype(str).str.strip()
    output["trade_date"] = (
        output["trade_date"].astype(str).str.strip().str.replace("-", "", regex=False)
    )
    output["trade_date"] = pd.to_datetime(
        output["trade_date"],
        format="%Y%m%d",
        errors="coerce",
    ).dt.strftime("%Y%m%d")

    non_numeric_cols = {
        "ts_code",
        "trade_date",
        "symbol",
        "name",
        "area",
        "industry",
        "market",
        "list_date",
    }
    for column in output.columns:
        if column not in non_numeric_cols:
            output[column] = pd.to_numeric(output[column], errors="coerce")

    output = output.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    return output.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def normalize_symbol_daily(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    if "trade_date" not in output.columns:
        raise ValueError("daily parquet missing required column: trade_date")
    output["trade_date"] = pd.to_datetime(output["trade_date"], errors="coerce")
    output = output[output["trade_date"].notna()].copy()
    for column in output.columns:
        if column != "trade_date":
            output[column] = pd.to_numeric(output[column], errors="coerce")
    return output.sort_values("trade_date").reset_index(drop=True)
