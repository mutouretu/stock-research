"""Export normalized US daily prices into one parquet file per symbol."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

import pandas as pd

DEFAULT_INPUT_PATH = Path("data/processed/us/prices_daily/prices.parquet")
DEFAULT_OUTPUT_DIR = Path("../shared_data/us/raw/daily/parquet_by_symbol")
DEFAULT_MIN_ROWS = 500

REQUIRED_INPUT_COLUMNS = [
    "symbol",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adj_close",
]
OUTPUT_BASE_COLUMNS = [
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "volume",
    "adj_close",
    "ts_code",
    "symbol",
    "market",
]
OPTIONAL_OUTPUT_COLUMNS = ["dividends", "stock_splits", "source", "created_at"]


@dataclass(frozen=True)
class ExportSummary:
    input_path: Path
    output_dir: Path
    input_rows: int
    input_symbols: int
    exported_symbols: int
    skipped_symbols: list[str] = field(default_factory=list)
    failed_symbols: dict[str, str] = field(default_factory=dict)

    def summary_text(self) -> str:
        return "\n".join(
            [
                "US daily by-symbol export summary",
                f"input: {self.input_path}",
                f"input_rows: {self.input_rows}",
                f"input_symbols: {self.input_symbols}",
                f"exported_symbols: {self.exported_symbols}",
                f"skipped_symbols: {len(self.skipped_symbols)}",
                f"failed_symbols: {len(self.failed_symbols)}",
                f"output_dir: {self.output_dir}",
                f"skipped_examples: {', '.join(self.skipped_symbols[:20]) or 'none'}",
                f"failed_examples: {', '.join(list(self.failed_symbols)[:20]) or 'none'}",
            ]
        )


def export_us_daily_by_symbol(
    input_path: str | Path = DEFAULT_INPUT_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    min_rows: int = DEFAULT_MIN_ROWS,
) -> ExportSummary:
    """Export a normalized US daily prices parquet into per-symbol parquet files."""

    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"US prices parquet not found: {path}")

    prices = pd.read_parquet(path)
    if prices.empty:
        raise ValueError(f"US prices parquet is empty: {path}")

    missing = [column for column in REQUIRED_INPUT_COLUMNS if column not in prices.columns]
    if missing:
        raise ValueError(
            "US prices parquet is missing required columns: " + ", ".join(missing)
        )

    prepared = prices.copy()
    prepared["symbol"] = prepared["symbol"].astype(str).str.upper()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"], errors="coerce")

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    skipped: list[str] = []
    failed: dict[str, str] = {}
    exported = 0

    for symbol, group in prepared.groupby("symbol", sort=True):
        symbol_text = str(symbol)
        if min_rows > 0 and len(group) < min_rows:
            skipped.append(symbol_text)
            continue

        try:
            output = _build_symbol_output(group, symbol_text)
            output_path = destination / f"{_safe_symbol_filename(symbol_text)}.parquet"
            output.to_parquet(output_path, index=False)
            exported += 1
        except Exception as exc:
            failed[symbol_text] = str(exc)

    return ExportSummary(
        input_path=path,
        output_dir=destination,
        input_rows=len(prepared),
        input_symbols=int(prepared["symbol"].nunique()),
        exported_symbols=exported,
        skipped_symbols=skipped,
        failed_symbols=failed,
    )


def _build_symbol_output(group: pd.DataFrame, symbol: str) -> pd.DataFrame:
    output = group.copy()
    output["trade_date"] = pd.to_datetime(output["trade_date"], errors="coerce")
    output = output.sort_values("trade_date").reset_index(drop=True)
    output["symbol"] = symbol
    output["ts_code"] = symbol
    output["volume"] = output["volume"]
    output["vol"] = output["volume"]
    if "market" not in output.columns:
        output["market"] = "US"
    output["market"] = output["market"].fillna("US").replace("", "US")

    columns = OUTPUT_BASE_COLUMNS + [
        column for column in OPTIONAL_OUTPUT_COLUMNS if column in output.columns
    ]
    return output.reindex(columns=columns)


def _safe_symbol_filename(symbol: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", symbol).strip("._")
    return safe or "UNKNOWN"
