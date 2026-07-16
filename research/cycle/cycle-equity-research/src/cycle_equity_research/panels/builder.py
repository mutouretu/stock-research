"""Build daily and quarterly research panels from dataset contracts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from research_data_core.aggregation import aggregate_asof_periods
from research_data_core.alignment import align_latest_available
from research_data_core.data import DatasetLoader
from research_data_core.paths import find_stock_research_root

from cycle_equity_research.data import load_dataset_catalog
from cycle_equity_research.instruments.cf.financials import extract_quarterly_financials


def build_daily_panel(
    panel_config: str | Path,
    dataset_config_dir: str | Path,
    *,
    root: Path | None = None,
) -> pd.DataFrame:
    config = _load_yaml(panel_config)
    workspace = root or find_stock_research_root(Path(panel_config))
    catalog = load_dataset_catalog(dataset_config_dir)
    cache: dict[str, pd.DataFrame] = {}
    base_spec = config["base"]
    base = _dataset(catalog, base_spec["dataset_id"], workspace, cache)
    base = _filter(base, base_spec.get("filters"))
    date_col = str(base_spec["time_col"])
    columns = [date_col, *base_spec["columns"]]
    panel = base[columns].copy().sort_values(date_col).drop_duplicates(date_col)
    panel = panel.rename(columns=base_spec.get("rename") or {})
    date_col = (base_spec.get("rename") or {}).get(date_col, date_col)
    panel[date_col] = pd.to_datetime(panel[date_col])
    panel.insert(0, "instrument", str(config["instrument"]))
    panel["panel_available_time"] = panel[date_col]

    for spec in config.get("inputs", []):
        source = _filter(
            _dataset(catalog, spec["dataset_id"], workspace, cache), spec.get("filters")
        )
        output = str(spec["output_col"])
        time_col = str(spec["time_col"])
        available_col = str(spec.get("available_time_col") or time_col)
        selected = [time_col, spec["value_col"]]
        if available_col != time_col:
            selected.insert(1, available_col)
        source = source[selected].copy()
        source = source.rename(
            columns={time_col: f"{output}__observation_time", spec["value_col"]: output}
        )
        if available_col == time_col:
            source[f"{output}__effective_time"] = source[f"{output}__observation_time"]
        else:
            source = source.rename(columns={available_col: f"{output}__effective_time"})
        panel = align_latest_available(
            panel,
            source,
            calendar_time_col=date_col,
            available_time_col=f"{output}__effective_time",
            value_columns=[output, f"{output}__observation_time"],
            matched_available_time_col=f"{output}__available_time",
        )
    returns = panel["cf_adj_close"].pct_change()
    panel["cf_return_1d"] = returns
    for window in config.get("momentum_windows", [20, 60, 120]):
        panel[f"cf_momentum_{window}d"] = panel["cf_adj_close"].pct_change(int(window))
    for window in config.get("volatility_windows", [20, 60]):
        panel[f"cf_volatility_{window}d"] = returns.rolling(int(window)).std() * (252**0.5)
    panel["calendar_month"] = panel[date_col].dt.month
    panel["spring_application_season"] = panel["calendar_month"].isin([3, 4, 5, 6])
    panel["fall_application_season"] = panel["calendar_month"].isin([9, 10, 11])
    return panel.sort_values(date_col).reset_index(drop=True)


def attach_quarterly_features(
    daily: pd.DataFrame,
    quarterly: pd.DataFrame,
    feature_columns: list[str],
) -> pd.DataFrame:
    """Attach only filed quarterly values to each daily row."""
    available = [column for column in feature_columns if column in quarterly.columns]
    source = quarterly[["period_end", "panel_available_time", *available]].copy()
    source = source.rename(
        columns={
            "period_end": "latest_quarter_period_end",
            "panel_available_time": "quarterly_effective_time",
        }
    )
    return align_latest_available(
        daily,
        source,
        calendar_time_col="trade_date",
        available_time_col="quarterly_effective_time",
        value_columns=["latest_quarter_period_end", *available],
        matched_available_time_col="latest_quarter_available_time",
    )


def build_quarterly_panel(
    panel_config: str | Path,
    dataset_config_dir: str | Path,
    *,
    root: Path | None = None,
) -> pd.DataFrame:
    config = _load_yaml(panel_config)
    workspace = root or find_stock_research_root(Path(panel_config))
    catalog = load_dataset_catalog(dataset_config_dir)
    cache: dict[str, pd.DataFrame] = {}
    base_spec = config["base"]
    operations = _filter(
        _dataset(catalog, base_spec["dataset_id"], workspace, cache), base_spec.get("filters")
    )
    operations = operations.copy()
    operations["feature"] = (
        "cf_" + operations["product"].astype(str) + "_" + operations["metric"].astype(str)
    )
    values = operations.pivot_table(
        index="period_end", columns="feature", values="value", aggfunc="last"
    ).reset_index()
    availability = operations.groupby("period_end", as_index=False)["filing_date"].max()
    panel = values.merge(availability, on="period_end", how="left")
    panel = panel.rename(columns={"filing_date": "panel_available_time"})
    panel.insert(0, "instrument", str(config["instrument"]))
    panel["period_end"] = pd.to_datetime(panel["period_end"])
    panel["panel_available_time"] = pd.to_datetime(panel["panel_available_time"])

    facts = _dataset(catalog, config["financials"]["dataset_id"], workspace, cache)
    first_periodic_filing = (
        facts[facts["form"].isin(["10-Q", "10-K"])]
        .groupby("period_end", as_index=False)["filing_date"]
        .min()
        .rename(columns={"filing_date": "periodic_filing_date"})
    )
    panel = panel.merge(first_periodic_filing, on="period_end", how="left")
    panel["panel_available_time"] = panel[
        ["panel_available_time", "periodic_filing_date"]
    ].max(axis=1)
    financials = extract_quarterly_financials(
        facts, panel[["period_end", "panel_available_time"]], config["financials"]["metrics"]
    )
    panel = panel.merge(financials, on="period_end", how="left")

    for spec in config.get("market_inputs", []):
        source = _filter(
            _dataset(catalog, spec["dataset_id"], workspace, cache), spec.get("filters")
        ).copy()
        time_col = str(spec["time_col"])
        available_col = str(spec.get("available_time_col") or time_col)
        if available_col == time_col:
            source["__effective_available_time"] = source[time_col]
            available_col = "__effective_available_time"
        aggregated = aggregate_asof_periods(
            panel[["period_end", "panel_available_time"]],
            source,
            period_end_col="period_end",
            cutoff_col="panel_available_time",
            observation_time_col=time_col,
            available_time_col=available_col,
            value_col=str(spec["value_col"]),
            output_col=str(spec["output_col"]),
            aggregation=str(spec.get("aggregation", "mean")),
        )
        panel = panel.merge(aggregated, on="period_end", how="left")
    for spec in config.get("asof_inputs", []):
        source = _filter(
            _dataset(catalog, spec["dataset_id"], workspace, cache), spec.get("filters")
        ).copy()
        output = str(spec["output_col"])
        time_col = str(spec["time_col"])
        source = source[[time_col, spec["value_col"]]].rename(
            columns={time_col: "__effective_time", spec["value_col"]: output}
        )
        aligned = align_latest_available(
            panel[["period_end", "panel_available_time"]],
            source,
            calendar_time_col="panel_available_time",
            available_time_col="__effective_time",
            value_columns=[output],
            matched_available_time_col=f"{output}__available_time",
        )
        panel[output] = aligned[output]
        panel[f"{output}__available_time"] = aligned[f"{output}__available_time"]
    if {"cf_gross_profit", "cf_revenue"}.issubset(panel.columns):
        panel["cf_gross_margin"] = panel["cf_gross_profit"] / panel["cf_revenue"]
    if {"cf_operating_income", "cf_depreciation_amortization"}.issubset(panel.columns):
        panel["cf_ebitda_proxy"] = (
            panel["cf_operating_income"] + panel["cf_depreciation_amortization"]
        )
        panel["cf_ebitda_proxy_ttm"] = panel["cf_ebitda_proxy"].rolling(4).sum()
    if {"cf_operating_cash_flow", "cf_capex"}.issubset(panel.columns):
        panel["cf_free_cash_flow"] = panel["cf_operating_cash_flow"] - panel["cf_capex"]
    valuation = {"cf_price_at_available_time", "cf_shares_outstanding", "cf_long_term_debt", "cf_cash"}
    if valuation.issubset(panel.columns):
        panel["cf_market_cap"] = panel["cf_price_at_available_time"] * panel["cf_shares_outstanding"]
        panel["cf_enterprise_value"] = (
            panel["cf_market_cap"] + panel["cf_long_term_debt"] - panel["cf_cash"]
        )
        if "cf_ebitda_proxy_ttm" in panel:
            panel["cf_ev_to_ebitda_proxy"] = panel["cf_enterprise_value"] / panel[
                "cf_ebitda_proxy_ttm"
            ]
    return panel.sort_values("period_end").reset_index(drop=True)


def _dataset(catalog, dataset_id: str, root: Path, cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if dataset_id not in cache:
        cache[dataset_id] = DatasetLoader(catalog.get(dataset_id), root=root).load(
            allow_full_scan=True
        )
    return cache[dataset_id]


def _filter(frame: pd.DataFrame, filters: dict | None) -> pd.DataFrame:
    result = frame
    for column, value in (filters or {}).items():
        values = value if isinstance(value, list) else [value]
        result = result[result[column].isin(values)]
    return result.copy()


def _load_yaml(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"Panel config must contain a YAML mapping: {path}")
    return config
