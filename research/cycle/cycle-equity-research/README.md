# cycle-equity-research

Research application workspace for cycle-sensitive equities. The first declared subject is CF
Industries (`CF`), but this phase only establishes project structure, data contracts, and runnable
inspection entry points. It does not implement a production model or access physical datasets.

The project follows the stock-pattern-search layout with `configs/`, `scripts/`, `src/`, `tests/`,
README, and an independently installable package.

## Current scope

- Declare the CF research domain, driver groups, feature directions, and target directions.
- Declare price, financial, commodity, and crop dataset contracts.
- Validate and summarize configuration without reading full datasets.
- Reserve feature and dataset-building interfaces for later phases.

It does not download data, calculate complete nitrogen economics, train models, backtest, generate
reports, or connect to an existing business application. Dataset YAML files are interface contracts;
their physical paths may not exist yet.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pip install -e ../../../platform/data/research-data-core
.venv/bin/python -m pytest -q
```

Inspect the contracts:

```bash
.venv/bin/python scripts/check_cf_config.py
.venv/bin/python scripts/inspect_cf_datasets.py
.venv/bin/python scripts/build_cf_dataset.py
.venv/bin/python scripts/run_cf_analysis.py
```
