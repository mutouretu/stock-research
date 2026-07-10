# research-ml-core

Minimal reusable machine-learning primitives for the unified `stock-research` workspace.

The initial extraction is deliberately small and strategy-neutral. It contains:

- rolling, lag, return, z-score, winsorization, normalization, and volatility features;
- forward-return classification/regression labels;
- walk-forward, rolling-window, and expanding-window time splits;
- sklearn, LightGBM, and XGBoost model adapters;
- a minimal trainer and classification/regression/IC metrics;
- sample metadata and feature-column selection helpers;
- basic return-series performance metrics.

It does **not** contain Type-N, breakout/pullback, reviewer, watchlist, scanning, or other strategy
logic. It never imports `stock-pattern-search`.

During this first extraction, `stock-pattern-search` keeps its original generic modules and imports
unchanged. This avoids changing existing model or strategy behavior; consumers can adopt
`research_ml_core` incrementally in later tasks.

## Install and test

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```
