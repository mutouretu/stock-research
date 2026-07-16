# CF cycle-analysis publication

This directory contains presentation-layer assets for the Chinese CF cycle-analysis manuscript.
Research calculations remain under `src/`, configured experiments remain under `configs/`, and
machine-readable evidence remains under `reports/`.

```text
cf_cycle_analysis.tex                  manuscript source
figures/                               generated, versioned TeX figure fragments
scripts/generate_lead_lag_figure.py    JSON report to PGFPlots figure
scripts/generate_stability_figure.py   M4.2 rolling-range figure
scripts/build_publication.py           regenerate figures and compile twice with XeLaTeX
build/                                 ignored compiler output
```

From this directory, build the manuscript with:

```bash
python3 scripts/build_publication.py
```

The coefficient figure reads `reports/cycle_analysis/cf_lead_lag_v1.json`; values are not copied
manually into the plotting script. The plotted intervals are Newey--West HAC 95% intervals for the
selected lag and are not adjusted for best-lag selection. Evidence colors come from the report's
stability and multiple-testing labels.
