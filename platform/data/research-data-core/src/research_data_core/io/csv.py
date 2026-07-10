"""CSV reader wrapper."""

from pathlib import Path
from typing import Any

import pandas as pd


def read_csv(path: str | Path, **kwargs: Any) -> pd.DataFrame:
    return pd.read_csv(Path(path), **kwargs)
