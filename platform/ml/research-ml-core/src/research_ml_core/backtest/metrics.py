"""Small performance summary without strategy assumptions."""

from __future__ import annotations

import numpy as np
import pandas as pd


def performance_metrics(returns: object, *, periods_per_year: int = 252) -> dict[str, float]:
    values = pd.Series(returns, dtype=float).dropna()
    if values.empty:
        return {"total_return": 0.0, "annualized_return": 0.0, "annualized_volatility": 0.0, "sharpe": float("nan"), "max_drawdown": 0.0}
    equity = (1.0 + values).cumprod()
    total = float(equity.iloc[-1] - 1.0)
    annualized = float(equity.iloc[-1] ** (periods_per_year / len(values)) - 1.0)
    volatility = float(values.std(ddof=0) * np.sqrt(periods_per_year))
    sharpe = float(values.mean() / values.std(ddof=0) * np.sqrt(periods_per_year)) if values.std(ddof=0) else float("nan")
    drawdown = equity / equity.cummax() - 1.0
    return {"total_return": total, "annualized_return": annualized, "annualized_volatility": volatility, "sharpe": sharpe, "max_drawdown": float(drawdown.min())}
