#!/usr/bin/env python3
"""Run deterministic fixed-sample and reconciliation audits for CF M1/M2."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from research_data_core.data import DatasetLoader
from research_data_core.paths import find_stock_research_root

from cycle_equity_research.data import load_dataset_catalog
from cycle_equity_research.panels import (
    attach_quarterly_features,
    build_daily_panel,
    build_quarterly_panel,
)
from cycle_equity_research.quality.audit import (
    audit_annual_reconciliation,
    audit_asof_values,
    audit_determinism,
    audit_exact_values,
    audit_period_means,
    write_audit_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workspace = find_stock_research_root(PROJECT_ROOT)
    dataset_dir = PROJECT_ROOT / "configs/datasets"
    daily_config = PROJECT_ROOT / "configs/panels/cf_daily.yaml"
    quarterly_config = PROJECT_ROOT / "configs/panels/cf_quarterly.yaml"
    daily_spec = _yaml(daily_config)
    catalog = load_dataset_catalog(dataset_dir)
    cache: dict[str, pd.DataFrame] = {}

    quarterly_first = build_quarterly_panel(quarterly_config, dataset_dir, root=workspace)
    daily_first = attach_quarterly_features(
        build_daily_panel(daily_config, dataset_dir, root=workspace),
        quarterly_first,
        list(daily_spec.get("quarterly_features") or []),
    )
    quarterly_second = build_quarterly_panel(quarterly_config, dataset_dir, root=workspace)
    daily_second = attach_quarterly_features(
        build_daily_panel(daily_config, dataset_dir, root=workspace),
        quarterly_second,
        list(daily_spec.get("quarterly_features") or []),
    )

    price = _data(catalog, "cycle.cf.price", workspace, cache)
    henry = _data(catalog, "commodity.henry_hub", workspace, cache)
    urea = _data(catalog, "commodity.urea", workspace, cache)
    crops = _data(catalog, "crop.corn", workspace, cache)
    ams = _data(catalog, "commodity.fertilizer_ams_3195", workspace, cache)
    operations = _data(catalog, "cycle.cf.product_operations", workspace, cache)
    facts = _data(catalog, "cycle.cf.financials", workspace, cache)

    results = [
        audit_determinism("daily_panel_determinism", daily_first, daily_second),
        audit_determinism("quarterly_panel_determinism", quarterly_first, quarterly_second),
        audit_exact_values(
            daily_first,
            price[price["symbol"] == "CF"],
            name="daily_cf_price_fixed_samples",
            panel_time_col="trade_date",
            source_time_col="trade_date",
            source_value_col="adj_close",
            panel_value_col="cf_adj_close",
        ),
        audit_asof_values(
            daily_first,
            henry[henry["series_id"] == "DHHNGSP"],
            name="daily_henry_hub_asof_samples",
            panel_time_col="trade_date",
            source_available_col="available_time",
            source_value_col="price",
            panel_value_col="henry_hub_spot",
        ),
        audit_asof_values(
            daily_first,
            urea[urea["series_id"] == "WORLD_BANK_UREA_MONTHLY"],
            name="daily_world_bank_urea_asof_samples",
            panel_time_col="trade_date",
            source_available_col="available_time",
            source_value_col="price",
            panel_value_col="world_bank_urea",
        ),
        audit_asof_values(
            daily_first,
            crops[crops["symbol"] == "ZC=F"],
            name="daily_corn_asof_samples",
            panel_time_col="trade_date",
            source_available_col="trade_date",
            source_value_col="price",
            panel_value_col="corn_futures",
        ),
        audit_asof_values(
            daily_first,
            ams[ams["product"] == "urea_46"],
            name="daily_ams_urea_asof_samples",
            panel_time_col="trade_date",
            source_available_col="available_time",
            source_value_col="price",
            panel_value_col="ams_urea_46",
        ),
        audit_exact_values(
            quarterly_first,
            operations[
                (operations["product"] == "granular_urea")
                & (operations["metric"] == "average_selling_price")
            ],
            name="quarterly_cf_urea_selling_price_samples",
            panel_time_col="period_end",
            source_time_col="period_end",
            source_value_col="value",
            panel_value_col="cf_granular_urea_average_selling_price",
        ),
        audit_period_means(
            quarterly_first,
            henry[henry["series_id"] == "DHHNGSP"],
            name="quarterly_henry_hub_mean_samples",
            period_end_col="period_end",
            panel_available_col="panel_available_time",
            source_time_col="observation_date",
            source_available_col="available_time",
            source_value_col="price",
            panel_value_col="henry_hub_quarter_mean",
        ),
        audit_period_means(
            quarterly_first,
            urea[urea["series_id"] == "WORLD_BANK_UREA_MONTHLY"],
            name="quarterly_world_bank_urea_mean_samples",
            period_end_col="period_end",
            panel_available_col="panel_available_time",
            source_time_col="observation_date",
            source_available_col="available_time",
            source_value_col="price",
            panel_value_col="world_bank_urea_quarter_mean",
        ),
    ]
    financial_metrics = [
        ("annual_revenue", "cf_revenue", ["Revenues", "SalesRevenueNet"]),
        ("annual_gross_profit", "cf_gross_profit", ["GrossProfit"]),
        ("annual_operating_income", "cf_operating_income", ["OperatingIncomeLoss"]),
        (
            "annual_operating_cash_flow",
            "cf_operating_cash_flow",
            ["NetCashProvidedByUsedInOperatingActivities"],
        ),
        ("annual_capex", "cf_capex", ["PaymentsToAcquirePropertyPlantAndEquipment"]),
    ]
    for name, panel_column, concepts in financial_metrics:
        results.append(
            audit_annual_reconciliation(
                quarterly_first,
                _annual_facts(facts, concepts),
                name=name,
                quarterly_value_col=panel_column,
                annual_year_col="year",
                annual_value_col="value",
            )
        )

    report_dir = PROJECT_ROOT / "reports/panel_quality"
    write_audit_report(
        results,
        report_dir / "cf_panel_audit.md",
        report_dir / "cf_panel_audit.json",
    )
    failures = sum(result["status"] == "FAIL" for result in results)
    samples = sum(result["sample_count"] for result in results)
    print(f"checks={len(results)} samples={samples} failures={failures}")
    return 1 if failures else 0


def _annual_facts(facts: pd.DataFrame, concepts: list[str]) -> pd.DataFrame:
    source = facts[
        facts["concept"].isin(concepts)
        & facts["form"].eq("10-K")
        & facts["period_start"].notna()
    ].copy()
    duration = (pd.to_datetime(source["period_end"]) - pd.to_datetime(source["period_start"])).dt.days
    source = source[duration.between(330, 370)]
    source["year"] = pd.to_datetime(source["period_end"]).dt.year
    rows: list[dict] = []
    for year, annual in source.groupby("year"):
        for concept in concepts:
            preferred = annual[annual["concept"] == concept].sort_values("filing_date")
            if not preferred.empty:
                rows.append({"year": int(year), "value": float(preferred.iloc[0]["value"])})
                break
    return pd.DataFrame(rows)


def _data(catalog, dataset_id: str, workspace: Path, cache: dict) -> pd.DataFrame:
    if dataset_id not in cache:
        cache[dataset_id] = DatasetLoader(catalog.get(dataset_id), root=workspace).load(
            allow_full_scan=True
        )
    return cache[dataset_id]


def _yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
