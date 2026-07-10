from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Tuple

import pandas as pd

from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS


class BaseMiner(ABC):
    """Lightweight miner interface for candidate generation."""

    name: str = "base"

    @abstractmethod
    def scan_one(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        """Scan one symbol and return candidate rows."""

    def scan_many(self, iterable: Iterable[Tuple[str, pd.DataFrame]]) -> pd.DataFrame:
        rows: list[pd.DataFrame] = []
        for ts_code, df in iterable:
            out = self.scan_one(ts_code, df)
            if not out.empty:
                rows.append(out)

        if not rows:
            return pd.DataFrame(columns=CANDIDATE_COLUMNS)

        combined = pd.concat(rows, ignore_index=True)
        for col in CANDIDATE_COLUMNS:
            if col not in combined.columns:
                combined[col] = pd.NA

        combined = combined[CANDIDATE_COLUMNS]
        combined = combined.sort_values(
            ["candidate_score", "asof_date"],
            ascending=[False, False],
            na_position="last",
        ).reset_index(drop=True)
        return combined
