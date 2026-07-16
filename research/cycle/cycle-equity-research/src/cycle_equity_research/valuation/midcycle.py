"""Transparent product bridge for CF mid-cycle EBITDA scenarios."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MidcycleScenarioResult:
    """Scenario summary, product contributions, and calibration diagnostics."""

    scenarios: pd.DataFrame
    product_bridge: pd.DataFrame
    calibration: dict
    diagnostics: dict


def build_midcycle_ebitda_scenarios(
    quarterly_panel: pd.DataFrame,
    quarterly_nitrogen: pd.DataFrame,
    operating_bridge_report: dict,
    config: dict,
) -> MidcycleScenarioResult:
    """Calculate downside, base, and upside EBITDA from explicit unit economics."""
    frame = _prepare_frame(quarterly_panel, quarterly_nitrogen, config)
    parameters = operating_bridge_report["final_parameters"]
    products = list(config["products"])
    volume_products = list(config["volume_products"])
    conversion = float(
        config["market_conversion"]["usd_per_metric_ton_to_usd_per_short_ton"]
    )

    mix = pd.Series(
        {
            product: (
                frame[f"cf_{product}_sales_volume"] / frame["__total_sales_volume"]
            ).median()
            for product in volume_products
        },
        dtype=float,
    )
    mix = mix / mix.sum()
    annual_volume = frame["__total_sales_volume"].rolling(4, min_periods=4).sum()
    hh_lag = frame["__henry_distributed_lag"]
    ebitda_conversion = (
        frame["cf_ebitda_proxy"] - frame["cf_gross_profit"]
    ).rolling(4, min_periods=4).sum() / 1_000_000.0
    reported_ttm = float(frame["cf_ebitda_proxy_ttm"].dropna().iloc[-1] / 1_000_000.0)

    scenario_rows: list[dict] = []
    product_rows: list[dict] = []
    for scenario_name, rules in config["scenarios"].items():
        urea = _quantile(frame["world_bank_urea_quarter_mean"], rules["urea_quantile"])
        henry_hub = _quantile(hh_lag, rules["henry_hub_quantile"])
        total_volume = _quantile(annual_volume, rules["annual_volume_quantile"])
        conversion_residual = _quantile(
            ebitda_conversion, rules["ebitda_conversion_quantile"]
        )
        gas_parameters = parameters["realized_gas_cost"]
        realized_gas = float(gas_parameters["intercept"] + gas_parameters["slope"] * henry_hub)
        gross_profit = 0.0

        for product in products:
            price_parameters = parameters["realized_price"][product]
            realized_price = float(
                price_parameters["intercept"]
                + price_parameters["slope"] * urea * conversion
            )
            gas_intensity = float(parameters["unit_margin"][product]["gas_intensity"])
            other_cost = _quantile(
                frame[f"cf_{product}_other_cost_basis_residual"],
                rules["other_cost_quantile"],
            )
            unit_margin = realized_price - gas_intensity * realized_gas - other_cost
            product_volume = float(total_volume * mix[product])
            contribution = unit_margin * product_volume / 1_000.0
            gross_profit += contribution
            product_rows.append(
                {
                    "scenario": scenario_name,
                    "product": product,
                    "urea_usd_per_metric_ton": urea,
                    "realized_price_usd_per_short_ton": realized_price,
                    "realized_gas_usd_per_mmbtu": realized_gas,
                    "gas_intensity_mmbtu_per_short_ton": gas_intensity,
                    "other_cost_usd_per_short_ton": other_cost,
                    "unit_margin_usd_per_short_ton": unit_margin,
                    "annual_volume_thousand_short_tons": product_volume,
                    "gross_profit_usd_million": contribution,
                }
            )

        other_margin = _quantile(
            frame["cf_other_gross_margin_per_ton"],
            rules["other_product_margin_quantile"],
        )
        other_volume = float(total_volume * mix["other"])
        other_contribution = other_margin * other_volume / 1_000.0
        gross_profit += other_contribution
        product_rows.append(
            {
                "scenario": scenario_name,
                "product": "other",
                "urea_usd_per_metric_ton": urea,
                "realized_price_usd_per_short_ton": np.nan,
                "realized_gas_usd_per_mmbtu": realized_gas,
                "gas_intensity_mmbtu_per_short_ton": np.nan,
                "other_cost_usd_per_short_ton": np.nan,
                "unit_margin_usd_per_short_ton": other_margin,
                "annual_volume_thousand_short_tons": other_volume,
                "gross_profit_usd_million": other_contribution,
            }
        )
        scenario_ebitda = gross_profit + conversion_residual
        scenario_rows.append(
            {
                "scenario": scenario_name,
                "urea_usd_per_metric_ton": urea,
                "henry_hub_usd_per_mmbtu": henry_hub,
                "cf_realized_gas_usd_per_mmbtu": realized_gas,
                "annual_volume_thousand_short_tons": total_volume,
                "gross_profit_usd_million": gross_profit,
                "ebitda_conversion_usd_million": conversion_residual,
                "scenario_ebitda_usd_million": scenario_ebitda,
                "reported_ttm_ebitda_usd_million": reported_ttm,
                "scenario_vs_reported_ttm": scenario_ebitda / reported_ttm - 1.0,
            }
        )

    scenarios = pd.DataFrame(scenario_rows)
    order = {name: index for index, name in enumerate(config["scenarios"])}
    scenarios["__order"] = scenarios["scenario"].map(order)
    scenarios = scenarios.sort_values("__order").drop(columns="__order").reset_index(drop=True)
    product_bridge = pd.DataFrame(product_rows)
    product_bridge["__order"] = product_bridge["scenario"].map(order)
    product_bridge = product_bridge.sort_values(["__order", "product"]).drop(
        columns="__order"
    ).reset_index(drop=True)

    calibration = _calibration_summary(
        frame, annual_volume, hh_lag, ebitda_conversion, mix, config
    )
    tolerance = float(config["quality"]["identity_tolerance_usd_million"])
    contribution = product_bridge.groupby("scenario")["gross_profit_usd_million"].sum()
    identity_error = scenarios.set_index("scenario")["gross_profit_usd_million"] - contribution
    ordered_ebitda = scenarios.set_index("scenario").loc[
        ["downside", "base", "upside"], "scenario_ebitda_usd_million"
    ]
    diagnostics = {
        "calibration_quarters": len(frame),
        "annual_volume_windows": int(annual_volume.notna().sum()),
        "conversion_windows": int(ebitda_conversion.notna().sum()),
        "point_in_time_violations": int(
            (frame["panel_available_time"] > pd.Timestamp(config["analysis_as_of"])).sum()
        ),
        "maximum_gross_profit_identity_error_usd_million": float(identity_error.abs().max()),
        "gross_profit_identity_pass": bool(identity_error.abs().max() <= tolerance),
        "scenario_ordering_pass": bool(ordered_ebitda.is_monotonic_increasing),
    }
    return MidcycleScenarioResult(scenarios, product_bridge, calibration, diagnostics)


def scenario_sensitivities(
    result: MidcycleScenarioResult, operating_bridge_report: dict, config: dict
) -> dict:
    """Calculate local base-case EBITDA sensitivities for two observable prices."""
    base = result.product_bridge[result.product_bridge["scenario"] == "base"]
    modeled = base[base["product"] != "other"]
    parameters = operating_bridge_report["final_parameters"]
    conversion = float(
        config["market_conversion"]["usd_per_metric_ton_to_usd_per_short_ton"]
    )
    urea_effect = 0.0
    gas_effect = 0.0
    for row in modeled.itertuples(index=False):
        price_slope = float(parameters["realized_price"][row.product]["slope"])
        urea_effect += (
            10.0
            * conversion
            * price_slope
            * row.annual_volume_thousand_short_tons
            / 1_000.0
        )
        gas_effect -= (
            float(parameters["realized_gas_cost"]["slope"])
            * row.gas_intensity_mmbtu_per_short_ton
            * row.annual_volume_thousand_short_tons
            / 1_000.0
        )
    base_summary = result.scenarios.set_index("scenario").loc["base"]
    return {
        "ebitda_change_per_10_usd_metric_ton_urea": float(urea_effect),
        "ebitda_change_per_1_usd_mmbtu_henry_hub": float(gas_effect),
        "gross_profit_change_per_1_percent_volume": float(
            base_summary["gross_profit_usd_million"] * 0.01
        ),
    }


def _prepare_frame(
    quarterly_panel: pd.DataFrame, quarterly_nitrogen: pd.DataFrame, config: dict
) -> pd.DataFrame:
    frame = quarterly_panel.merge(
        quarterly_nitrogen,
        on=["instrument", "period_end", "panel_available_time"],
        how="left",
        validate="one_to_one",
    ).sort_values("period_end").reset_index(drop=True)
    frame["period_end"] = pd.to_datetime(frame["period_end"])
    frame["panel_available_time"] = pd.to_datetime(frame["panel_available_time"])
    as_of = pd.Timestamp(config["analysis_as_of"])
    frame = frame[
        (frame["period_end"] <= as_of) & (frame["panel_available_time"] <= as_of)
    ].reset_index(drop=True)
    current = float(config["market_conversion"]["henry_hub_current_quarter_weight"])
    previous = float(config["market_conversion"]["henry_hub_previous_quarter_weight"])
    frame["__henry_distributed_lag"] = (
        current * frame["henry_hub_quarter_mean"]
        + previous * frame["henry_hub_quarter_mean"].shift(1)
    )
    volume_columns = [
        f"cf_{product}_sales_volume" for product in config["volume_products"]
    ]
    frame["__total_sales_volume"] = frame[volume_columns].sum(axis=1, min_count=4)
    return frame


def _calibration_summary(
    frame: pd.DataFrame,
    annual_volume: pd.Series,
    hh_lag: pd.Series,
    ebitda_conversion: pd.Series,
    mix: pd.Series,
    config: dict,
) -> dict:
    quantiles = [0.25, 0.50, 0.75]
    return {
        "as_of": str(config["analysis_as_of"]),
        "first_period": frame["period_end"].min().isoformat(),
        "last_period": frame["period_end"].max().isoformat(),
        "quarters": len(frame),
        "urea_usd_per_metric_ton": _quantile_map(
            frame["world_bank_urea_quarter_mean"], quantiles
        ),
        "henry_hub_distributed_lag_usd_per_mmbtu": _quantile_map(hh_lag, quantiles),
        "annual_volume_thousand_short_tons": _quantile_map(annual_volume, quantiles),
        "ebitda_conversion_usd_million": _quantile_map(ebitda_conversion, quantiles),
        "normalized_product_mix": {key: float(value) for key, value in mix.items()},
        "reported_ttm_ebitda_history_usd_million": _quantile_map(
            frame["cf_ebitda_proxy_ttm"] / 1_000_000.0, quantiles
        ),
    }


def _quantile(values: pd.Series, quantile: float) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        raise ValueError("cannot calculate scenario quantile from an empty series")
    return float(clean.quantile(float(quantile)))


def _quantile_map(values: pd.Series, quantiles: list[float]) -> dict:
    return {f"q{int(q * 100):02d}": _quantile(values, q) for q in quantiles}
