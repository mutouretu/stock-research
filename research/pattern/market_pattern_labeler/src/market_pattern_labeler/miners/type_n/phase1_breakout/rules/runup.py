from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RunupRuleConfig:
    window: int = 150
    max_runup_pct: float = 0.6
    score_weight: int = 0


@dataclass(frozen=True)
class RunupRuleResult:
    runup_pct: pd.Series
    ok: pd.Series
    score_bonus: pd.Series


class RunupRule:
    name = "runup"
    flag_name = "runup_ok"

    def __init__(self, config: RunupRuleConfig):
        self.config = config

    def evaluate(self, close: pd.Series) -> RunupRuleResult:
        numeric_close = pd.to_numeric(close, errors="coerce")
        rolling_low = numeric_close.rolling(self.config.window).min().replace(0, np.nan)
        runup_pct = numeric_close / rolling_low - 1.0
        ok = runup_pct <= self.config.max_runup_pct
        score_bonus = ok.astype(int) * int(self.config.score_weight)
        return RunupRuleResult(runup_pct=runup_pct, ok=ok, score_bonus=score_bonus)


__all__ = ["RunupRule", "RunupRuleConfig", "RunupRuleResult"]
