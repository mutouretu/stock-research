from __future__ import annotations

import pandas as pd
from research_ml_core.features import add_return_features, add_rolling_features


def add_basic_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add lightweight indicators used by both dataset build and scan inference."""
    if "trade_date" not in df.columns:
        raise KeyError("Missing required column: trade_date")

    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce")
    out = out.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)

    if "close" in out.columns:
        featured = add_return_features(
            out,
            column="close",
            periods=(1,),
            fill_method="pad",
        )
        featured = add_rolling_features(
            featured,
            column="close",
            windows=(5, 20),
            min_periods=1,
        )
        out["ret_1d"] = featured["close_return_1"]
        out["ma_5"] = featured["close_rolling_mean_5"]
        out["ma_20"] = featured["close_rolling_mean_20"]

    return out
