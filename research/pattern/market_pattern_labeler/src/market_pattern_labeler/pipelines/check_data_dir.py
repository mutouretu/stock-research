from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from market_pattern_labeler.data.daily_loader import REQUIRED_PRICE_COLS


@dataclass
class FileCheck:
    file: str
    ok: bool
    rows: int = 0
    ts_code: str | None = None
    date_min: str | None = None
    date_max: str | None = None
    missing_columns: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class DataDirCheckSummary:
    data_dir: Path
    total_files: int
    checked_files: int
    ok_files: int
    failed_files: int
    total_rows_checked: int
    min_rows_per_file: int | None
    max_rows_per_file: int | None
    symbols_checked: int
    date_min: str | None
    date_max: str | None
    missing_column_warnings: int
    examples: list[FileCheck]

    def summary_text(self) -> str:
        required_columns_status = "ok" if self.missing_column_warnings == 0 else "failed"
        lines = [
            "data_dir_check_summary",
            f"data_dir={self.data_dir}",
            f"total_parquet_files={self.total_files}",
            f"checked_files={self.checked_files}",
            f"ok_files={self.ok_files}",
            f"failed_files={self.failed_files}",
            f"required_columns_status={required_columns_status}",
            f"missing_column_warnings={self.missing_column_warnings}",
            f"symbols_checked={self.symbols_checked}",
            f"rows_checked={self.total_rows_checked}",
            f"min_rows_per_file={self.min_rows_per_file if self.min_rows_per_file is not None else 'N/A'}",
            f"max_rows_per_file={self.max_rows_per_file if self.max_rows_per_file is not None else 'N/A'}",
            f"date_range={self.date_min or 'N/A'} to {self.date_max or 'N/A'}",
            "examples:",
        ]
        for item in self.examples:
            status = "ok" if item.ok else "failed"
            detail = (
                f"  - {item.file}: {status}, rows={item.rows}, ts_code={item.ts_code or 'N/A'}, "
                f"date_range={item.date_min or 'N/A'} to {item.date_max or 'N/A'}"
            )
            if item.missing_columns:
                detail += f", missing_columns={item.missing_columns}"
            if item.error:
                detail += f", error={item.error}"
            lines.append(detail)
        return "\n".join(lines)


def check_data_dir(data_dir: str | Path, max_files: int = 20) -> DataDirCheckSummary:
    base = Path(data_dir)
    if not base.exists():
        raise FileNotFoundError(f"daily data directory not found: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"daily data path is not a directory: {base}")

    files = sorted(base.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no parquet files found in {base}")
    limit = max(0, int(max_files))
    files_to_check = files[:limit] if limit else files

    checks = [_check_one_file(path) for path in files_to_check]
    ok_checks = [item for item in checks if item.ok]
    all_dates = [
        pd.Timestamp(value)
        for item in ok_checks
        for value in [item.date_min, item.date_max]
        if value
    ]

    return DataDirCheckSummary(
        data_dir=base,
        total_files=len(files),
        checked_files=len(checks),
        ok_files=len(ok_checks),
        failed_files=len(checks) - len(ok_checks),
        total_rows_checked=sum(item.rows for item in ok_checks),
        min_rows_per_file=min([item.rows for item in ok_checks], default=None),
        max_rows_per_file=max([item.rows for item in ok_checks], default=None),
        symbols_checked=len({item.ts_code for item in ok_checks if item.ts_code}),
        date_min=_format_date(min(all_dates)) if all_dates else None,
        date_max=_format_date(max(all_dates)) if all_dates else None,
        missing_column_warnings=sum(1 for item in checks if item.missing_columns),
        examples=checks[: min(len(checks), 20)],
    )


def _check_one_file(path: Path) -> FileCheck:
    try:
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        return FileCheck(file=path.name, ok=False, error=f"read parquet failed: {exc}")

    missing = [column for column in REQUIRED_PRICE_COLS if column not in df.columns]
    if missing:
        return FileCheck(
            file=path.name,
            ok=False,
            rows=len(df),
            missing_columns=missing,
        )

    if df.empty:
        return FileCheck(file=path.name, ok=False, rows=0, error="empty parquet")

    trade_date = pd.to_datetime(df["trade_date"], errors="coerce").dropna()
    ts_code = _infer_ts_code(df, path)

    return FileCheck(
        file=path.name,
        ok=not trade_date.empty,
        rows=len(df),
        ts_code=ts_code,
        date_min=_format_date(trade_date.min()) if not trade_date.empty else None,
        date_max=_format_date(trade_date.max()) if not trade_date.empty else None,
        error=None if not trade_date.empty else "no valid trade_date values",
    )


def _infer_ts_code(df: pd.DataFrame, path: Path) -> str:
    if "ts_code" in df.columns:
        values = df["ts_code"].dropna()
        if not values.empty:
            return str(values.iloc[0])
    if "symbol" in df.columns:
        values = df["symbol"].dropna()
        if not values.empty:
            return str(values.iloc[0])
    return path.stem


def _format_date(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")
