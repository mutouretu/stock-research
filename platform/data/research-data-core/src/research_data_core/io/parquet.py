"""Bounded parquet readers."""

from pathlib import Path
from typing import Iterable

import pandas as pd


def read_parquet(path: str | Path, columns: Iterable[str] | None = None) -> pd.DataFrame:
    return pd.read_parquet(Path(path), columns=list(columns) if columns is not None else None)


def read_parquet_by_entity_dir(
    path: str | Path,
    max_files: int | None = None,
    columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    directory = Path(path)
    if not directory.is_dir():
        raise FileNotFoundError(f"Parquet-by-entity directory does not exist: {directory}")
    files = sorted(directory.glob("*.parquet"))
    if max_files is not None:
        if max_files < 0:
            raise ValueError("max_files must be non-negative or None")
        files = files[:max_files]
    if not files:
        return pd.DataFrame(columns=list(columns) if columns is not None else None)
    return pd.concat((read_parquet(file, columns=columns) for file in files), ignore_index=True)
