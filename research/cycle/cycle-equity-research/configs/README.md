# Configuration

- `instruments/` declares research subjects and their required driver/feature/target directions.
- `datasets/` contains research-data-core compatible dataset contracts.
- `panels/` declares broad and curated research-panel inputs, outputs, and freshness rules.
- `features/` contains versioned economic assumptions and the core/context feature registry.
- `quality/` defines source roles and milestone quality thresholds.
- `experiments/` locks prediction timing, expanding-window rules, baseline formulas, outputs, and
  comparison metrics so later methods use the same evaluation sample.
- `local_runs/` is reserved for local run configuration; credentials and outputs must not be stored
  here.
