"""Validate normalized US daily prices."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_INPUT_PATH = Path("data/processed/us/prices_daily/prices.parquet")
DEFAULT_REPORT_PATH = Path("reports/us_prices_validation_report.md")
DEFAULT_EXPECTED_START_DATE = "2015-01-01"
DEFAULT_EXPECTED_START_TOLERANCE_DAYS = 7
MISSING_WARNING_THRESHOLD = 0.05

REQUIRED_COLUMNS = [
    "symbol",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adj_close",
]
OPTIONAL_COLUMNS = ["market", "dividends", "stock_splits", "source", "created_at"]
QUALITY_COLUMNS = ["open", "high", "low", "close", "volume", "adj_close"]


@dataclass(frozen=True)
class ValidationReport:
    input_path: Path
    rows: int
    symbol_count: int
    date_min: str | None
    date_max: str | None
    present_columns: list[str]
    missing_required_columns: list[str]
    optional_columns_present: list[str]
    missing_rates: dict[str, float]
    symbol_history: pd.DataFrame
    shortest_history: pd.DataFrame
    longest_history: pd.DataFrame
    symbols_starting_after_expected: pd.DataFrame
    anomaly_counts: dict[str, int]
    anomaly_examples: dict[str, pd.DataFrame]
    duplicate_count: int
    duplicate_examples: pd.DataFrame
    unsorted_symbols: list[str]
    warnings: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# US Prices Validation Report",
            "",
            "## Basic Info",
            f"- Input file: `{self.input_path}`",
            f"- Rows: {self.rows}",
            f"- Symbols: {self.symbol_count}",
            f"- Date range: {self.date_min or 'N/A'} to {self.date_max or 'N/A'}",
            "",
            "## Required Columns",
            _format_key_values(
                {
                    "present": ", ".join(self.present_columns),
                    "missing_required": ", ".join(self.missing_required_columns) or "none",
                    "optional_present": ", ".join(self.optional_columns_present) or "none",
                }
            ),
            "",
            "## Missing Values",
            _format_key_values(
                {column: f"{rate:.2%}" for column, rate in self.missing_rates.items()}
            ),
            "",
            "## Per-symbol History Length",
            "### Shortest 20",
            _dataframe_to_markdown(self.shortest_history),
            "",
            "### Longest 20",
            _dataframe_to_markdown(self.longest_history),
            "",
            "### Symbols Starting After Expected Start",
            _dataframe_to_markdown(self.symbols_starting_after_expected.head(20)),
            "",
            "## Anomalies",
            _format_key_values(self.anomaly_counts),
            "",
            "### Anomaly Examples",
        ]
        for name, examples in self.anomaly_examples.items():
            lines.extend([f"#### {name}", _dataframe_to_markdown(examples), ""])
        lines.extend(
            [
                "## Duplicate Rows",
                f"- Duplicate symbol/trade_date rows: {self.duplicate_count}",
                _dataframe_to_markdown(self.duplicate_examples),
                "",
                "## Sorting",
                f"- Symbols not sorted by trade_date: {len(self.unsorted_symbols)}",
                f"- Examples: {', '.join(self.unsorted_symbols[:20]) or 'none'}",
                "",
                "## Warnings",
            ]
        )
        if self.warnings:
            lines.extend(f"- {warning}" for warning in self.warnings)
        else:
            lines.append("- none")
        lines.append("")
        return "\n".join(lines)

    def summary_text(self) -> str:
        warning_count = len(self.warnings)
        return "\n".join(
            [
                "US prices validation summary",
                f"input: {self.input_path}",
                f"rows: {self.rows}",
                f"symbols: {self.symbol_count}",
                f"date_range: {self.date_min or 'N/A'} to {self.date_max or 'N/A'}",
                f"missing_required_columns: {self.missing_required_columns or 'none'}",
                f"duplicate_rows: {self.duplicate_count}",
                f"unsorted_symbols: {len(self.unsorted_symbols)}",
                f"warnings: {warning_count}",
            ]
        )


def validate_us_prices(
    input_path: str | Path = DEFAULT_INPUT_PATH,
    report_path: str | Path | None = DEFAULT_REPORT_PATH,
    expected_start_date: str = DEFAULT_EXPECTED_START_DATE,
    expected_start_tolerance_days: int = DEFAULT_EXPECTED_START_TOLERANCE_DAYS,
) -> ValidationReport:
    """Validate a normalized US daily prices parquet file."""

    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"US prices parquet not found: {path}")

    try:
        prices = pd.read_parquet(path)
    except Exception as exc:
        raise ValueError(f"Failed to read US prices parquet: {path}") from exc

    missing_required = [column for column in REQUIRED_COLUMNS if column not in prices.columns]
    if missing_required:
        raise ValueError(
            "US prices parquet is missing required columns: "
            + ", ".join(missing_required)
        )

    prepared = prices.copy()
    prepared["symbol"] = prepared["symbol"].astype(str).str.upper()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"], errors="coerce")

    report = _build_validation_report(
        prepared,
        path,
        missing_required,
        expected_start_date,
        expected_start_tolerance_days,
    )
    if report_path is not None:
        output_path = Path(report_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report.to_markdown(), encoding="utf-8")
    return report


def _build_validation_report(
    prices: pd.DataFrame,
    input_path: Path,
    missing_required: list[str],
    expected_start_date: str,
    expected_start_tolerance_days: int,
) -> ValidationReport:
    warnings: list[str] = []
    if prices.empty:
        warnings.append("input parquet is empty")
    if prices["trade_date"].isna().any():
        warnings.append("trade_date contains unparsable values")

    valid_dates = prices["trade_date"].dropna()
    date_min = _format_date(valid_dates.min()) if not valid_dates.empty else None
    date_max = _format_date(valid_dates.max()) if not valid_dates.empty else None

    symbol_history = _build_symbol_history(prices)
    expected_start = pd.Timestamp(expected_start_date)
    minimum_acceptable_start = expected_start + pd.Timedelta(days=expected_start_tolerance_days)
    symbols_starting_after_expected = symbol_history[
        symbol_history["first_trade_date"] > minimum_acceptable_start
    ].copy()
    if not symbols_starting_after_expected.empty:
        warnings.append(
            f"{len(symbols_starting_after_expected)} symbols start more than "
            f"{expected_start_tolerance_days} days after {expected_start_date}"
        )

    missing_rates = {
        column: 0.0 if prices.empty else float(prices[column].isna().mean())
        for column in QUALITY_COLUMNS
        if column in prices.columns
    }
    high_missing = [
        f"{column} missing rate {rate:.2%}"
        for column, rate in missing_rates.items()
        if rate > MISSING_WARNING_THRESHOLD
    ]
    warnings.extend(high_missing)

    anomaly_counts, anomaly_examples = _collect_anomalies(prices)
    for name, count in anomaly_counts.items():
        if count:
            warnings.append(f"{name} anomalies: {count}")

    duplicate_mask = prices.duplicated(["symbol", "trade_date"], keep=False)
    duplicate_examples = _example_rows(prices.loc[duplicate_mask])
    duplicate_count = int(duplicate_mask.sum())
    if duplicate_count:
        warnings.append(f"duplicate symbol/trade_date rows: {duplicate_count}")

    unsorted_symbols = _find_unsorted_symbols(prices)
    if unsorted_symbols:
        warnings.append(f"{len(unsorted_symbols)} symbols are not sorted by trade_date")

    return ValidationReport(
        input_path=input_path,
        rows=len(prices),
        symbol_count=int(prices["symbol"].nunique()),
        date_min=date_min,
        date_max=date_max,
        present_columns=list(prices.columns),
        missing_required_columns=missing_required,
        optional_columns_present=[column for column in OPTIONAL_COLUMNS if column in prices.columns],
        missing_rates=missing_rates,
        symbol_history=_format_history_dates(symbol_history),
        shortest_history=_format_history_dates(symbol_history.nsmallest(20, "rows")),
        longest_history=_format_history_dates(symbol_history.nlargest(20, "rows")),
        symbols_starting_after_expected=_format_history_dates(symbols_starting_after_expected),
        anomaly_counts=anomaly_counts,
        anomaly_examples=anomaly_examples,
        duplicate_count=duplicate_count,
        duplicate_examples=duplicate_examples,
        unsorted_symbols=unsorted_symbols,
        warnings=warnings,
    )


def _build_symbol_history(prices: pd.DataFrame) -> pd.DataFrame:
    history = (
        prices.groupby("symbol", dropna=False)
        .agg(
            rows=("trade_date", "size"),
            first_trade_date=("trade_date", "min"),
            last_trade_date=("trade_date", "max"),
        )
        .reset_index()
        .sort_values(["rows", "symbol"], ascending=[True, True])
        .reset_index(drop=True)
    )
    return history


def _collect_anomalies(prices: pd.DataFrame) -> tuple[dict[str, int], dict[str, pd.DataFrame]]:
    masks = {
        "high_less_than_low": prices["high"] < prices["low"],
        "close_non_positive": prices["close"] <= 0,
        "adj_close_non_positive": prices["adj_close"] <= 0,
        "volume_negative": prices["volume"] < 0,
        "ohlc_non_positive": (prices[["open", "high", "low", "close"]] <= 0).any(axis=1),
    }
    counts = {name: int(mask.sum()) for name, mask in masks.items()}
    examples = {name: _example_rows(prices.loc[mask]) for name, mask in masks.items() if mask.any()}
    return counts, examples


def _find_unsorted_symbols(prices: pd.DataFrame) -> list[str]:
    unsorted: list[str] = []
    for symbol, group in prices.groupby("symbol", sort=False):
        if not group["trade_date"].is_monotonic_increasing:
            unsorted.append(str(symbol))
    return unsorted


def _example_rows(rows: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    columns = [column for column in REQUIRED_COLUMNS if column in rows.columns]
    return _format_history_dates(rows.loc[:, columns].head(limit).copy())


def _format_history_dates(frame: pd.DataFrame) -> pd.DataFrame:
    formatted = frame.copy()
    for column in ("trade_date", "first_trade_date", "last_trade_date"):
        if column in formatted.columns:
            formatted[column] = pd.to_datetime(formatted[column], errors="coerce").dt.strftime(
                "%Y-%m-%d"
            )
    return formatted


def _format_date(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _format_key_values(values: dict[str, object]) -> str:
    if not values:
        return "- none"
    return "\n".join(f"- {key}: {value}" for key, value in values.items())


def _dataframe_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_none_"
    display = frame.head(20).copy()
    headers = [str(column) for column in display.columns]
    rows = [
        [
            str(value).replace("|", "\\|") if pd.notna(value) else ""
            for value in record
        ]
        for record in display.to_numpy()
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)
