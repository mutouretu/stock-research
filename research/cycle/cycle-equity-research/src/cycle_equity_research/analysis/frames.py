"""Shared frame assembly for CF lead/lag analyses."""

from __future__ import annotations

import pandas as pd


def prepare_lead_lag_frames(
    inputs: dict[str, pd.DataFrame]
) -> dict[str, pd.DataFrame]:
    """Merge curated and detailed quarterly fields used by M4 analyses."""
    keys = ["instrument", "period_end", "panel_available_time"]
    market_columns = [
        *keys,
        "world_bank_urea_quarter_mean",
        "henry_hub_quarter_mean",
        "corn_quarter_mean",
    ]
    product_price_columns = [
        *keys,
        "cf_ammonia_realized_price",
        "cf_granular_urea_realized_price",
        "cf_uan_realized_price",
        "cf_ammonium_nitrate_realized_price",
    ]
    quarterly = inputs["core_quarterly"].merge(
        inputs["quarterly_panel"][market_columns],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    quarterly = quarterly.merge(
        inputs["quarterly_nitrogen"][product_price_columns],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    return {
        "monthly": inputs["core_monthly"].copy(),
        "quarterly": quarterly,
    }
