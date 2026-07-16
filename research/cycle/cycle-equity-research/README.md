# cycle-equity-research

Research application workspace for cycle-sensitive equities. The first implemented subject is CF
Industries (`CF`). It consumes standardized physical datasets and builds broad point-in-time panels,
compact model-ready panels, and versioned nitrogen-economics proxies. Predictive models and trading
rules remain later milestones.

The project follows the stock-pattern-search layout with `configs/`, `scripts/`, `src/`, `tests/`,
README, and an independently installable package.

## Current scope

- Declare the CF research domain, driver groups, feature directions, and target directions.
- Declare price, financial, commodity, and crop dataset contracts.
- Build daily and quarterly research panels using reusable time-alignment primitives.
- Curate six monthly and five quarterly core features while isolating short-history tactical data.
- Build and validate versioned nitrogen-economics proxies.
- Validate source availability, panel uniqueness, coverage, freshness, and lineage.

It does not train predictive models, backtest, or connect to an existing business application.
Source ingestion remains in `market-data-hub`; dataset YAML files are the boundary between
ingestion and research.

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

## Milestone 1 data quality

The active implementation roadmap is in
[`docs/cf_research_roadmap.md`](docs/cf_research_roadmap.md). After the public-source ingestion in
`market-data-hub` has run, generate the CF quality report with:

```bash
.venv/bin/python scripts/validate_cf_data.py
```

The command writes Markdown and JSON reports under `reports/data_quality/`. It returns a non-zero
exit status while any dataset has an `ERROR`; warnings remain visible but do not fail the command.

Milestone 1 is complete for the currently declared P0 public sources. Source limitations remain
visible in the generated report rather than being silently filled.

## Milestone 2 research panels

Build both physical panels, their lineage manifest, and the panel quality report with:

```bash
.venv/bin/python scripts/build_cf_panels.py
.venv/bin/python scripts/audit_cf_panels.py
```

Outputs:

```text
storage/shared_data/research/cycle/CF/
├── daily_panel.parquet
├── quarterly_panel.parquet
└── panel_lineage.json

reports/panel_quality/
├── cf_panel_audit.md
├── cf_panel_audit.json
├── cf_panel_quality.md
└── cf_panel_quality.json
```

Low-frequency values are joined using their `available_time`, not their observation period. The
quarterly panel becomes available at the later of the earnings exhibit and formal periodic filing,
which is conservative for backtests. Current World Bank urea freshness limitations remain visible
as warnings and do not create future-data leakage.

## Milestone 2.1 curated panels

Build the compact model-readiness layer from the existing M2 and M3 artifacts with:

```bash
.venv/bin/python scripts/build_cf_curated_panels.py
```

The command produces `core_monthly_panel.parquet`, `core_quarterly_panel.parquet`,
`tactical_context_panel.parquet`, lineage, and Markdown/JSON reports under
`reports/model_readiness/`. Core features are explicitly whitelisted in
`configs/features/cf_feature_registry.yaml`. AMS prices, planted acres, and product-cost residuals
remain available for scenarios and diagnostics but are prohibited from entering the base feature
matrix.

The current effective sample is suitable for exploratory monthly estimates and descriptive or
low-degree-of-freedom quarterly analysis. It is not evidence that a complex model can be trained.

## Milestone 3 nitrogen economics

Build the versioned daily and quarterly nitrogen-profit proxies with:

```bash
.venv/bin/python scripts/build_cf_nitrogen_proxies.py
```

The model keeps market prices, CF realized prices and accounting gross margin separate. Gas
intensity, nutrient content, unit conversion, fixed basket weights, source links and known failure
scenarios are declared in `configs/features/cf_nitrogen_economics_v1.yaml`.
