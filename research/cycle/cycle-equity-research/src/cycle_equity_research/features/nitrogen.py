"""Versioned nitrogen-fertilizer economics features."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml


def load_nitrogen_config(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"Nitrogen config must contain a YAML mapping: {path}")
    validate_nitrogen_config(config)
    return config


def validate_nitrogen_config(config: dict) -> None:
    factors = config["scenario_factors"]
    if not 0 < float(factors["low"]) < float(factors["base"]) < float(factors["high"]):
        raise ValueError("Gas-intensity scenario factors must satisfy 0 < low < base < high")
    weights = [
        float(component["weight"])
        for component in config["cf_nitrogen_basket"]["components"].values()
    ]
    if abs(sum(weights) - 1.0) > 1e-8:
        raise ValueError(f"CF nitrogen basket weights must sum to one, got {sum(weights)}")
    for name, product in config["products"].items():
        if not 0 < float(product["nitrogen_fraction"]) <= 1:
            raise ValueError(f"Invalid nitrogen fraction for {name}")
        if float(product["gas_intensity_base_mmbtu_per_short_ton"]) <= 0:
            raise ValueError(f"Invalid gas intensity for {name}")


def price_per_metric_ton_to_short_ton(value: pd.Series | float, config: dict):
    factor = float(config["unit_conversions"]["usd_per_metric_ton_to_usd_per_short_ton"])
    return value * factor


def theoretical_cash_spread(
    product_price_per_short_ton: pd.Series | float,
    gas_price_per_mmbtu: pd.Series | float,
    gas_intensity_mmbtu_per_short_ton: float,
    variable_cost_per_short_ton: float = 0.0,
):
    return (
        product_price_per_short_ton
        - gas_price_per_mmbtu * gas_intensity_mmbtu_per_short_ton
        - variable_cost_per_short_ton
    )


def build_daily_nitrogen_features(frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    required = ["instrument", "trade_date", "panel_available_time", "henry_hub_spot"]
    _require(frame, required)
    result = frame[required].copy()
    result["model_version"] = str(config["version"])
    gas = pd.to_numeric(frame["henry_hub_spot"], errors="coerce")
    for prefix, market in config["daily_market_products"].items():
        source_column = str(market["source_column"])
        _require(frame, [source_column])
        price = pd.to_numeric(frame[source_column], errors="coerce")
        if market["source_unit"] == "USD_per_metric_ton":
            price = price_per_metric_ton_to_short_ton(price, config)
        elif market["source_unit"] != "USD_per_short_ton":
            raise ValueError(f"Unsupported source unit: {market['source_unit']}")
        product = config["products"][market["product"]]
        result[f"{prefix}_price_usd_per_short_ton"] = price
        result[f"{prefix}_price_usd_per_nitrogen_ton"] = price / float(
            product["nitrogen_fraction"]
        )
        result[f"{prefix}_fertilizer_gas_ratio"] = price / gas.where(gas > 0)
        for scenario, factor in config["scenario_factors"].items():
            intensity = float(product["gas_intensity_base_mmbtu_per_short_ton"]) * float(factor)
            result[f"{prefix}_gas_intensity_{scenario}"] = intensity
            result[f"{prefix}_theoretical_cash_spread_{scenario}"] = theoretical_cash_spread(
                price,
                gas,
                intensity,
                float(product["identified_variable_cost_usd_per_short_ton"]),
            )

    global_index = config["global_fertilizer_index"]
    result["global_fertilizer_index"] = (
        pd.to_numeric(frame[global_index["source_column"]], errors="coerce")
        / float(global_index["base_price"])
        * 100
    )
    basket_parts = []
    for prefix, component in config["cf_nitrogen_basket"]["components"].items():
        index = result[f"{prefix}_price_usd_per_short_ton"] / float(component["base_price"])
        result[f"{prefix}_price_index"] = index * 100
        basket_parts.append(index * float(component["weight"]) * 100)
    result["cf_nitrogen_basket"] = pd.concat(basket_parts, axis=1).sum(
        axis=1, min_count=len(basket_parts)
    )
    return result


def build_quarterly_nitrogen_features(
    quarterly_panel: pd.DataFrame,
    daily_features: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    required = ["instrument", "period_end", "panel_available_time"]
    _require(quarterly_panel, required)
    result = quarterly_panel[required].copy()
    result["model_version"] = str(config["version"])
    gas_column = "cf_all_products_realized_natural_gas_cost"
    _require(quarterly_panel, [gas_column])
    gas = pd.to_numeric(quarterly_panel[gas_column], errors="coerce")
    result["cf_realized_natural_gas_cost"] = gas
    basket_spreads: dict[str, list[pd.Series]] = {
        scenario: [] for scenario in config["scenario_factors"]
    }
    basket_weights: list[float] = []
    full_weights = _quarterly_weights(config)
    for panel_product, configured_product in config["quarterly_cf_products"].items():
        price_col = f"cf_{panel_product}_average_selling_price"
        gross_col = f"cf_{panel_product}_gross_margin_per_ton"
        _require(quarterly_panel, [price_col, gross_col])
        price = pd.to_numeric(quarterly_panel[price_col], errors="coerce")
        gross_margin = pd.to_numeric(quarterly_panel[gross_col], errors="coerce")
        result[f"cf_{panel_product}_realized_price"] = price
        result[f"cf_{panel_product}_actual_gross_margin_per_ton"] = gross_margin
        product = config["products"][configured_product]
        for scenario, factor in config["scenario_factors"].items():
            intensity = float(product["gas_intensity_base_mmbtu_per_short_ton"]) * float(factor)
            spread = theoretical_cash_spread(
                price,
                gas,
                intensity,
                float(product["identified_variable_cost_usd_per_short_ton"]),
            )
            result[f"cf_{panel_product}_realized_gas_spread_{scenario}"] = spread
            basket_spreads[scenario].append(spread * full_weights[panel_product])
        result[f"cf_{panel_product}_other_cost_basis_residual"] = (
            result[f"cf_{panel_product}_realized_gas_spread_base"] - gross_margin
        )
        basket_weights.append(full_weights[panel_product])
    if abs(sum(basket_weights) - 1.0) > 1e-8:
        raise ValueError("Quarterly CF product weights must sum to one")
    for scenario, parts in basket_spreads.items():
        result[f"cf_realized_basket_gas_spread_{scenario}"] = pd.concat(parts, axis=1).sum(
            axis=1, min_count=len(parts)
        )

    daily = daily_features.copy()
    daily["period_end"] = pd.to_datetime(daily["trade_date"]).dt.to_period("Q").dt.end_time.dt.normalize()
    market_columns = [
        column for column in daily if column.endswith("_theoretical_cash_spread_base")
    ]
    quarterly_market = daily.groupby("period_end", as_index=False)[market_columns].mean()
    quarterly_market = quarterly_market.rename(
        columns={column: f"{column}_quarter_mean" for column in market_columns}
    )
    return result.merge(quarterly_market, on="period_end", how="left")


def _quarterly_weights(config: dict) -> dict[str, float]:
    components = config["cf_nitrogen_basket"]["components"]
    three_product = {
        "ammonia": float(components["ams_ammonia"]["weight"]),
        "granular_urea": float(components["ams_urea"]["weight"]),
        "uan": float(components["ams_uan32"]["weight"]),
    }
    an_weight = 0.117520
    scale = 1.0 - an_weight
    return {**{key: value * scale for key, value in three_product.items()}, "ammonium_nitrate": an_weight}


def _require(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")
