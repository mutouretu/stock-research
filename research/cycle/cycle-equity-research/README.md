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
- Measure predeclared monthly and quarterly lead/lag relationships with explicit economic-period
  and availability-time clocks.
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

## Quarterly operating-bridge experiment

Run the locked expanding-window baseline with:

```bash
.venv/bin/python scripts/run_cf_operating_bridge_experiment.py
```

The experiment makes each estimate 15 days after quarter end, before CF results are available, and
uses only previously disclosed company quarters for fitting. It evaluates realized prices, realized
gas cost, product margins, product volumes, and total gross profit against a last-disclosed-value
comparator. Predictions use a stable long-form schema so later LR, tree, or time-series methods can
be compared on exactly the same periods and targets without dropping difficult rows.

Outputs are stored below `storage/shared_data/research/cycle/CF/experiments/`; the human and JSON
reports are written to `reports/experiments/`.

## Milestone 4.1 lead/lag analysis

Run the low-degree-of-freedom lead/lag grid with:

```bash
.venv/bin/python scripts/run_cf_lead_lag_analysis.py
```

Positive lag `k` always means that signal `x(t)` is paired with target `y(t+k)`. Economic-period
relationships describe operating transmission but are not called tradable. Availability-time
relationships verify source timestamps before evaluating later CF returns. The analysis uses
Newey--West HAC inference, Benjamini--Hochberg multiple-testing adjustment, and chronological
half-sample stability checks. Complete grid and best-lag datasets are written under
`storage/shared_data/research/cycle/CF/cycle_analysis/`; reports are under
`reports/cycle_analysis/`.

## Milestone 4.2 stability analysis

Run fixed-lag rolling, season, gas-regime, and spread-stress checks with:

```bash
.venv/bin/python scripts/run_cf_lead_lag_stability.py
```

M4.2 reads the locked M4.1 best lags and never reselects a lag inside a window or slice. It emits
rolling correlations, descriptive regime slices, and explicit `ACCEPT_*`, `CONDITIONAL`, `REJECT`,
or `DIAGNOSTIC` decisions under `storage/shared_data/research/cycle/CF/cycle_analysis/`. Complete
Markdown/JSON evidence is written to `reports/cycle_analysis/`.

## Milestone 4.3 operating-cycle states

Build the point-in-time monthly state timeline with:

```bash
.venv/bin/python scripts/run_cf_cycle_state.py
```

The v1 state machine uses one non-duplicated economic signal: the global urea--Henry Hub spread.
Its trailing level and three-month direction determine `RECOVERY`, `EXPANSION`, `PEAK_RISK`,
`CONTRACTION`, `TROUGH`, or `MIXED`. Entry confirmation, minimum duration, and hysteresis are
declared in `configs/experiments/cf_cycle_state_v1.yaml`. Missing core data immediately degrades the
state to `MIXED`; latest disclosed CF margin and six-month stock momentum remain confirmation
overlays and never change the economic state.

The command writes the monthly history, current JSON snapshot, manifest, and complete Markdown/JSON
report under the existing `cycle_analysis` output locations.

## Publication source

The Chinese manuscript, generated figure fragments, and one-command XeLaTeX build live under
`publication/cf_cycle_analysis/`. Research calculations are not duplicated there: the lead/lag
figure is regenerated directly from `reports/cycle_analysis/cf_lead_lag_v1.json`.

```bash
cd publication/cf_cycle_analysis
python3 scripts/build_publication.py
```

Compiler artifacts are isolated in the ignored `build/` directory.
