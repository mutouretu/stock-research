"""M5.3 valuation matrix and current-price implied operating assumptions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ValuationRangeResult:
    """Scenario/multiple matrix, implied assumptions, snapshot, and diagnostics."""

    valuation_matrix: pd.DataFrame
    implied_assumptions: pd.DataFrame
    snapshot: dict
    diagnostics: dict


def build_valuation_range(
    monthly_valuation: pd.DataFrame,
    midcycle_scenarios: pd.DataFrame,
    midcycle_report: dict,
    cycle_state_current: dict,
    config: dict,
) -> ValuationRangeResult:
    """Convert operating scenarios to equity value without hiding the matrix."""
    as_of = pd.Timestamp(config["analysis_as_of"])
    history = monthly_valuation.copy()
    history["month_end"] = pd.to_datetime(history["month_end"])
    history = history[history["month_end"] <= as_of].sort_values("month_end")
    if history.empty:
        raise ValueError("valuation history is empty at analysis_as_of")
    current = history.iloc[-1]
    valid = history.loc[history["reported_multiple_available"]].copy()
    multiples = {
        name: float(valid["ev_to_reported_ttm_ebitda"].quantile(float(quantile)))
        for name, quantile in config["multiple_cases"].items()
    }
    required_scenarios = list(config["quality"]["required_scenarios"])
    scenario_frame = midcycle_scenarios.set_index("scenario")
    missing = sorted(set(required_scenarios) - set(scenario_frame.index))
    if missing:
        raise ValueError(f"midcycle scenarios missing: {missing}")

    net_debt = float(current["financial_debt"] - current["cash"])
    nci = float(current["noncontrolling_interest"])
    preferred = float(current["preferred_equity"])
    non_equity_claims = net_debt + nci + preferred
    shares = float(current["shares_outstanding"])
    current_ev = float(current["enterprise_value_standard"])
    current_price = float(current["market_price"])

    matrix_rows: list[dict] = []
    for scenario_name in required_scenarios:
        ebitda_million = float(
            scenario_frame.loc[scenario_name, "scenario_ebitda_usd_million"]
        )
        for multiple_name, multiple in multiples.items():
            enterprise_value = ebitda_million * 1_000_000.0 * multiple
            raw_equity = enterprise_value - non_equity_claims
            floor_equity = max(0.0, raw_equity)
            per_share = floor_equity / shares
            matrix_rows.append(
                {
                    "scenario": scenario_name,
                    "multiple_case": multiple_name,
                    "scenario_ebitda_usd_million": ebitda_million,
                    "ev_to_ebitda_multiple": multiple,
                    "enterprise_value_usd": enterprise_value,
                    "net_financial_debt_usd": net_debt,
                    "noncontrolling_interest_usd": nci,
                    "preferred_equity_usd": preferred,
                    "raw_equity_value_usd": raw_equity,
                    "equity_value_floor_zero_usd": floor_equity,
                    "shares_outstanding": shares,
                    "per_share_value_usd": per_share,
                    "upside_to_current_price": per_share / current_price - 1.0,
                    "current_ev_to_scenario_ebitda": current_ev
                    / (ebitda_million * 1_000_000.0),
                }
            )
    matrix = pd.DataFrame(matrix_rows)
    scenario_order = {name: index for index, name in enumerate(required_scenarios)}
    multiple_order = {name: index for index, name in enumerate(config["multiple_cases"])}
    matrix["__scenario_order"] = matrix["scenario"].map(scenario_order)
    matrix["__multiple_order"] = matrix["multiple_case"].map(multiple_order)
    matrix = matrix.sort_values(["__scenario_order", "__multiple_order"]).drop(
        columns=["__scenario_order", "__multiple_order"]
    ).reset_index(drop=True)

    reference_name = str(config["implied_operations"]["reference_scenario"])
    reference = scenario_frame.loc[reference_name]
    reference_ebitda = float(reference["scenario_ebitda_usd_million"])
    reference_urea = float(reference["urea_usd_per_metric_ton"])
    urea_sensitivity_per_dollar = float(
        midcycle_report["sensitivities_usd_million"][
            "ebitda_change_per_10_usd_metric_ton_urea"
        ]
        / 10.0
    )
    if urea_sensitivity_per_dollar <= 0:
        raise ValueError("urea EBITDA sensitivity must be positive")
    calibration_urea = midcycle_report["calibration"]["urea_usd_per_metric_ton"]
    implied_rows = []
    for multiple_name, multiple in multiples.items():
        implied_ebitda = current_ev / 1_000_000.0 / multiple
        implied_urea = reference_urea + (
            implied_ebitda - reference_ebitda
        ) / urea_sensitivity_per_dollar
        implied_rows.append(
            {
                "multiple_case": multiple_name,
                "ev_to_ebitda_multiple": multiple,
                "current_enterprise_value_usd": current_ev,
                "implied_ebitda_usd_million": implied_ebitda,
                "implied_urea_usd_per_metric_ton": implied_urea,
                "urea_vs_historical_median": implied_urea
                / float(calibration_urea["q50"])
                - 1.0,
                "urea_iqr_position": _iqr_position(
                    implied_urea,
                    float(calibration_urea["q25"]),
                    float(calibration_urea["q75"]),
                ),
            }
        )
    implied = pd.DataFrame(implied_rows)

    base_matrix = matrix[matrix["scenario"] == reference_name].set_index("multiple_case")
    snapshot = {
        "analysis_as_of": str(config["analysis_as_of"]),
        "market_price_date": pd.Timestamp(current["month_end"]).isoformat(),
        "market_price_usd": current_price,
        "current_enterprise_value_usd": current_ev,
        "shares_outstanding": shares,
        "net_financial_debt_usd": net_debt,
        "noncontrolling_interest_usd": nci,
        "preferred_equity_usd": preferred,
        "multiple_cases": multiples,
        "base_per_share_low_usd": float(base_matrix.loc["low", "per_share_value_usd"]),
        "base_per_share_median_usd": float(
            base_matrix.loc["median", "per_share_value_usd"]
        ),
        "base_per_share_high_usd": float(base_matrix.loc["high", "per_share_value_usd"]),
        "cycle_state_as_of": cycle_state_current.get("month_end"),
        "cycle_state": cycle_state_current.get("state"),
        "cycle_state_reason": cycle_state_current.get("raw_state_reason"),
        "confirmation_overlay": cycle_state_current.get("confirmation_overlay"),
    }
    tolerance = float(config["quality"]["identity_tolerance_usd"])
    ev_identity_error = (
        matrix["raw_equity_value_usd"]
        + matrix["net_financial_debt_usd"]
        + matrix["noncontrolling_interest_usd"]
        + matrix["preferred_equity_usd"]
        - matrix["enterprise_value_usd"]
    ).abs()
    diagnostics = {
        "multiple_history_months": len(valid),
        "point_in_time_violations": int(
            (history["fundamental_available_time"] > history["panel_available_time"])
            .fillna(False)
            .sum()
        ),
        "matrix_rows": len(matrix),
        "maximum_equity_bridge_error_usd": float(ev_identity_error.max()),
        "equity_bridge_pass": bool(ev_identity_error.max() <= tolerance),
        "matrix_values_finite": bool(
            np.isfinite(
                matrix[
                    [
                        "scenario_ebitda_usd_million",
                        "ev_to_ebitda_multiple",
                        "enterprise_value_usd",
                        "per_share_value_usd",
                    ]
                ].to_numpy(dtype=float)
            ).all()
        ),
    }
    return ValuationRangeResult(matrix, implied, snapshot, diagnostics)


def _iqr_position(value: float, q25: float, q75: float) -> str:
    if value < q25:
        return "BELOW_IQR"
    if value > q75:
        return "ABOVE_IQR"
    return "WITHIN_IQR"
