"""Generic dataframe schema checks."""

from collections.abc import Iterable, Mapping

import pandas as pd


def require_columns(frame: pd.DataFrame, required: Iterable[str]) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}; available={list(frame.columns)}")


def check_no_duplicate_keys(frame: pd.DataFrame, keys: Iterable[str]) -> None:
    key_columns = list(keys)
    if not key_columns:
        raise ValueError("At least one key column is required")
    require_columns(frame, key_columns)
    duplicate_count = int(frame.duplicated(subset=key_columns, keep=False).sum())
    if duplicate_count:
        raise ValueError(f"Found {duplicate_count} rows with duplicate keys for {key_columns}")


def normalize_columns(frame: pd.DataFrame, columns_mapping: Mapping[str, str]) -> pd.DataFrame:
    """Rename columns using a ``source_name -> target_name`` mapping."""
    missing = [column for column in columns_mapping if column not in frame.columns]
    if missing:
        raise ValueError(f"Cannot normalize missing source columns: {missing}")
    return frame.rename(columns=dict(columns_mapping))
