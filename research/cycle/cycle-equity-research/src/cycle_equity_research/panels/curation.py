"""Curate compact model-ready panels from broad CF research panels."""

from __future__ import annotations

import pandas as pd

from research_data_core.alignment import align_latest_available


def build_core_monthly_panel(
    daily_panel: pd.DataFrame,
    daily_nitrogen: pd.DataFrame,
    quarterly_panel: pd.DataFrame,
    quarterly_nitrogen: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """Build a compact monthly panel without carrying stale low-frequency values."""
    daily = daily_panel.merge(
        daily_nitrogen,
        on=["instrument", "trade_date", "panel_available_time"],
        how="left",
        suffixes=("", "_nitrogen"),
    ).sort_values("trade_date")
    date = pd.to_datetime(daily["trade_date"])
    freshness = config["freshness_days"]
    henry_fresh = _fresh(
        date,
        daily["henry_hub_spot__available_time"],
        int(freshness["henry_hub"]),
    )
    urea_fresh = _fresh(
        date,
        daily["world_bank_urea__available_time"],
        int(freshness["world_bank_urea"]),
    )
    corn_fresh = _fresh(
        date,
        daily["corn_futures__available_time"],
        int(freshness["corn_futures"]),
    )
    daily["__global_spread"] = daily["global_urea_theoretical_cash_spread_base"].where(
        henry_fresh & urea_fresh
    )
    daily["__henry"] = daily["henry_hub_spot"].where(henry_fresh)
    daily["__corn"] = daily["corn_futures"].where(corn_fresh)
    daily["__henry_available"] = pd.to_datetime(
        daily["henry_hub_spot__available_time"], errors="coerce"
    ).where(henry_fresh)
    daily["__urea_available"] = pd.to_datetime(
        daily["world_bank_urea__available_time"], errors="coerce"
    ).where(urea_fresh)
    daily["__corn_available"] = pd.to_datetime(
        daily["corn_futures__available_time"], errors="coerce"
    ).where(corn_fresh)
    daily["__month"] = date.dt.to_period("M")

    monthly = (
        daily.groupby("__month", as_index=False)
        .agg(
            month_end=("trade_date", "max"),
            cf_price_month_end=("cf_adj_close", "last"),
            global_urea_gas_spread_month_mean=("__global_spread", "mean"),
            henry_hub_month_mean=("__henry", "mean"),
            corn_month_mean=("__corn", "mean"),
            henry_hub_source_available_time=("__henry_available", "max"),
            world_bank_urea_source_available_time=("__urea_available", "max"),
            corn_source_available_time=("__corn_available", "max"),
            trading_days=("trade_date", "count"),
        )
        .drop(columns="__month")
    )
    monthly.insert(0, "instrument", "CF")
    monthly["month_end"] = pd.to_datetime(monthly["month_end"])
    monthly["panel_available_time"] = monthly["month_end"]
    monthly["cf_return_1m"] = monthly["cf_price_month_end"].pct_change()
    monthly["cf_momentum_6m"] = monthly["cf_price_month_end"].pct_change(6)
    monthly["henry_hub_source_age_days"] = (
        monthly["month_end"] - monthly["henry_hub_source_available_time"]
    ).dt.days
    monthly["world_bank_urea_source_age_days"] = (
        monthly["month_end"] - monthly["world_bank_urea_source_available_time"]
    ).dt.days
    monthly["corn_source_age_days"] = (
        monthly["month_end"] - monthly["corn_source_available_time"]
    ).dt.days
    monthly["global_urea_gas_spread_month_mean"] = monthly[
        "global_urea_gas_spread_month_mean"
    ].where(monthly["world_bank_urea_source_age_days"] <= int(freshness["world_bank_urea"]))
    monthly["henry_hub_month_mean"] = monthly["henry_hub_month_mean"].where(
        monthly["henry_hub_source_age_days"] <= int(freshness["henry_hub"])
    )
    monthly["corn_month_mean"] = monthly["corn_month_mean"].where(
        monthly["corn_source_age_days"] <= int(freshness["corn_futures"])
    )

    quarterly = quarterly_panel.merge(
        quarterly_nitrogen[
            ["period_end", "cf_realized_basket_gas_spread_base"]
        ],
        on="period_end",
        how="left",
    ).sort_values("period_end")
    quarterly["cf_gross_margin_change"] = quarterly["cf_gross_margin"].diff()
    source = quarterly[
        [
            "period_end",
            "panel_available_time",
            "cf_realized_basket_gas_spread_base",
            "cf_gross_margin_change",
        ]
    ].rename(
        columns={
            "period_end": "latest_cf_period_end",
            "panel_available_time": "__quarterly_available_time",
            "cf_realized_basket_gas_spread_base": "latest_cf_realized_basket_gas_spread",
            "cf_gross_margin_change": "latest_cf_gross_margin_change",
        }
    )
    monthly = align_latest_available(
        monthly,
        source,
        calendar_time_col="month_end",
        available_time_col="__quarterly_available_time",
        value_columns=[
            "latest_cf_period_end",
            "latest_cf_realized_basket_gas_spread",
            "latest_cf_gross_margin_change",
        ],
        matched_available_time_col="latest_cf_available_time",
    )
    return _add_missing_indicators(monthly, config["monthly_model_features"])


def build_core_quarterly_panel(
    quarterly_panel: pd.DataFrame,
    quarterly_nitrogen: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """Select a five-feature quarterly core with explicit outcomes kept outside model inputs."""
    combined = quarterly_panel.merge(
        quarterly_nitrogen,
        on=["instrument", "period_end", "panel_available_time"],
        how="left",
        suffixes=("", "_nitrogen"),
    ).sort_values("period_end")
    volume_columns = [
        "cf_ammonia_sales_volume",
        "cf_granular_urea_sales_volume",
        "cf_uan_sales_volume",
        "cf_ammonium_nitrate_sales_volume",
        "cf_other_sales_volume",
    ]
    combined["cf_total_sales_volume"] = combined[volume_columns].sum(axis=1, min_count=4)
    combined["cf_gross_margin_change"] = combined["cf_gross_margin"].diff()
    combined = combined.rename(
        columns={
            "global_urea_theoretical_cash_spread_base_quarter_mean": (
                "global_urea_gas_spread_quarter_mean"
            ),
            "cf_realized_basket_gas_spread_base": "cf_realized_basket_gas_spread",
        }
    )
    columns = [
        "instrument",
        "period_end",
        "panel_available_time",
        *config["quarterly_model_features"],
        "cf_revenue",
        "cf_gross_margin",
        "cf_ebitda_proxy",
    ]
    return _add_missing_indicators(combined[columns].copy(), config["quarterly_model_features"])


def build_tactical_context_panel(
    daily_panel: pd.DataFrame,
    daily_nitrogen: pd.DataFrame,
    quarterly_nitrogen: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """Keep short-history and diagnostic fields outside the core model panels."""
    daily_columns = [
        "instrument",
        "trade_date",
        "panel_available_time",
        "ams_ammonia",
        "ams_ammonia__available_time",
        "ams_urea_46",
        "ams_urea_46__available_time",
        "ams_uan_32",
        "ams_uan_32__available_time",
        "corn_planted_acres",
        "corn_planted_acres__available_time",
        "soybean_planted_acres",
        "soybean_planted_acres__available_time",
        "spring_application_season",
        "fall_application_season",
    ]
    result = daily_panel[daily_columns].merge(
        daily_nitrogen[
            [
                "instrument",
                "trade_date",
                "panel_available_time",
                "ams_urea_theoretical_cash_spread_base",
                "cf_nitrogen_basket",
            ]
        ],
        on=["instrument", "trade_date", "panel_available_time"],
        how="left",
    )
    date = pd.to_datetime(result["trade_date"])
    ams_limit = int(config["freshness_days"]["ams_fertilizer"])
    ams_fresh = pd.Series(True, index=result.index)
    for prefix in ("ams_ammonia", "ams_urea_46", "ams_uan_32"):
        fresh = _fresh(date, result[f"{prefix}__available_time"], ams_limit)
        result[f"{prefix}__stale"] = ~fresh & result[prefix].notna()
        result[prefix] = result[prefix].where(fresh)
        ams_fresh &= fresh
    result["ams_urea_theoretical_cash_spread_base"] = result[
        "ams_urea_theoretical_cash_spread_base"
    ].where(_fresh(date, result["ams_urea_46__available_time"], ams_limit))
    result["cf_nitrogen_basket"] = result["cf_nitrogen_basket"].where(ams_fresh)

    residual_columns = [
        column for column in quarterly_nitrogen if column.endswith("_other_cost_basis_residual")
    ]
    source = quarterly_nitrogen[
        ["period_end", "panel_available_time", *residual_columns]
    ].rename(
        columns={
            "period_end": "latest_residual_period_end",
            "panel_available_time": "__residual_available_time",
        }
    )
    return align_latest_available(
        result,
        source,
        calendar_time_col="trade_date",
        available_time_col="__residual_available_time",
        value_columns=["latest_residual_period_end", *residual_columns],
        matched_available_time_col="latest_residual_available_time",
    )


def _fresh(panel_time: pd.Series, available_time: pd.Series, maximum_days: int) -> pd.Series:
    panel = pd.to_datetime(panel_time, errors="coerce")
    available = pd.to_datetime(available_time, errors="coerce")
    age = (panel - available).dt.days
    return age.between(0, maximum_days)


def _add_missing_indicators(frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    for feature in features:
        frame[f"{feature}__missing"] = frame[feature].isna()
    frame["available_model_feature_count"] = frame[features].notna().sum(axis=1)
    return frame
