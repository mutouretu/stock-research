# research-data-core

`research-data-core` is the configuration-driven research data interface layer for the unified
`stock-research` workspace. Its layout follows stock-pattern-search: configurations, runnable
inspection scripts, source packages, tests, and explicit data contracts live together while the
package remains independently installable.

## Responsibilities

- Resolve the workspace root and `storage/shared_data` without local absolute paths.
- Describe datasets through YAML and discover them through a catalog.
- Read CSV, parquet files, and parquet-by-entity directories.
- Map source fields to canonical dataset fields and optionally normalize entity/time names.
- Validate columns and key uniqueness.
- Perform generic entity-aware as-of alignment.
- Inspect and validate bounded samples without writing outputs.

This package does not download data, implement market or strategy logic, calculate business
signals, train models, backtest, or generate reports. It is not connected to an existing business
project in this phase.

## Install and test

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

## Dataset contract

A dataset YAML specifies its identifier, storage layout, repository-relative path, abstract entity
and time fields, optional availability time, source-field mapping, and required source columns.
Python reads these values from `DatasetConfig`; it does not assume market-specific field names.

`columns` maps canonical names to source names. For example, `volume: source_volume` makes the
loader rename `source_volume` to `volume`. When requested, configured entity and time columns are
additionally normalized to `entity_id` and `time`.

See [`configs/datasets/examples/`](configs/datasets/examples/) and use:

```bash
.venv/bin/python scripts/check_shared_data.py
.venv/bin/python scripts/inspect_dataset.py --config path/to/dataset.yaml --max-files 5
.venv/bin/python scripts/validate_dataset.py --config path/to/dataset.yaml --max-files 5
```
