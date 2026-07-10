"""Small, stable data protocols shared by research projects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class SampleMeta:
    sample_id: str
    ts_code: str
    asof_date: str
    label: float | int
    label_source: str = ""
    confidence: float = 1.0
    split: str | None = None


def build_sample_id(ts_code: str, asof_date: str) -> str:
    return f"{ts_code}_{asof_date}"


def select_feature_columns(
    frame: pd.DataFrame,
    *,
    exclude: Iterable[str] = ("sample_id", "ts_code", "asof_date", "label"),
    numeric_only: bool = True,
) -> list[str]:
    excluded = set(exclude)
    columns = [column for column in frame.columns if column not in excluded]
    if numeric_only:
        columns = [column for column in columns if pd.api.types.is_numeric_dtype(frame[column])]
    return columns
