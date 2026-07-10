from __future__ import annotations

import pandas as pd

from market_pattern_labeler.miners.type_n.phase2_pullback.positive import PullbackPatternConfig, PullbackPatternMiner


class PullbackNegativeMiner(PullbackPatternMiner):
    name = "pullback_negative"

    def __init__(self, config: PullbackPatternConfig):
        super().__init__(config)

    def generate_samples(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        out = super().generate_samples(ts_code, df)
        if out.empty:
            return out
        return out[out["label"] == 0].reset_index(drop=True)


__all__ = ["PullbackNegativeMiner"]
