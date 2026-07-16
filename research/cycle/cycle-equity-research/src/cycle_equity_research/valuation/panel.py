"""Build a point-in-time monthly CF valuation data layer."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ValuationDataResult:
    """Monthly valuation panel plus quality diagnostics."""

    monthly: pd.DataFrame
    diagnostics: dict


def build_monthly_valuation_panel(
    daily_panel: pd.DataFrame, quarterly_panel: pd.DataFrame, config: dict
) -> ValuationDataResult:
    """Reprice the latest filed balance sheet and TTM earnings each month."""
    cutoff = pd.Timestamp(config["analysis_end_date"])
    daily = daily_panel.copy()
    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    daily = daily.loc[daily["trade_date"] <= cutoff].sort_values("trade_date")
    _require_columns(daily, ["instrument", "trade_date", config["market_value"]["price_column"]])
    daily["__month"] = daily["trade_date"].dt.to_period("M")
    monthly = (
        daily.groupby("__month", as_index=False)
        .tail(1)[["instrument", "trade_date", config["market_value"]["price_column"]]]
        .rename(
            columns={
                "trade_date": "month_end",
                config["market_value"]["price_column"]: "market_price",
            }
        )
        .sort_values("month_end")
        .reset_index(drop=True)
    )
    monthly["panel_available_time"] = monthly["month_end"]

    quarterly = _prepare_quarterly(quarterly_panel, config)
    aligned = pd.merge_asof(
        monthly,
        quarterly,
        left_on="panel_available_time",
        right_on="fundamental_available_time",
        direction="backward",
        allow_exact_matches=True,
    )
    aligned["market_cap"] = aligned["market_price"] * aligned["shares_outstanding"]
    aligned["net_financial_debt"] = aligned["financial_debt"] - aligned["cash"]
    aligned["enterprise_value_standard"] = (
        aligned["market_cap"]
        + aligned["net_financial_debt"]
        + aligned["noncontrolling_interest"]
        + aligned["preferred_equity"]
    )
    aligned["enterprise_value_lease_adjusted"] = (
        aligned["enterprise_value_standard"] + aligned["operating_lease_liabilities"]
    )
    aligned["ev_to_reported_ttm_ebitda"] = (
        aligned["enterprise_value_standard"] / aligned["reported_ttm_ebitda"]
    )
    aligned["lease_adjusted_ev_to_reported_ttm_ebitda"] = (
        aligned["enterprise_value_lease_adjusted"] / aligned["reported_ttm_ebitda"]
    )
    aligned["equity_fcf_yield_ttm"] = aligned["free_cash_flow_ttm"] / aligned["market_cap"]
    aligned["legacy_enterprise_value_ex_nci"] = (
        aligned["market_cap"] + aligned["legacy_long_term_debt"] - aligned["cash"]
    )
    aligned["nci_and_debt_scope_adjustment"] = (
        aligned["enterprise_value_standard"] - aligned["legacy_enterprise_value_ex_nci"]
    )
    aligned["fundamental_period_age_days"] = (
        aligned["month_end"] - aligned["latest_period_end"]
    ).dt.days
    aligned["fundamental_disclosure_age_days"] = (
        aligned["month_end"] - aligned["fundamental_available_time"]
    ).dt.days
    maximum_age = int(config["quality"]["maximum_fundamental_period_age_days"])
    required = [
        "market_price",
        "shares_outstanding",
        "financial_debt",
        "cash",
        "noncontrolling_interest",
        "preferred_equity",
        "reported_ttm_ebitda",
    ]
    aligned["valuation_inputs_complete"] = aligned[required].notna().all(axis=1)
    aligned["fundamentals_fresh"] = aligned["fundamental_period_age_days"] <= maximum_age
    aligned["reported_multiple_available"] = (
        aligned["valuation_inputs_complete"]
        & aligned["fundamentals_fresh"]
        & (aligned["enterprise_value_standard"] > 0)
        & (aligned["reported_ttm_ebitda"] > 0)
    )
    aligned.loc[~aligned["reported_multiple_available"], "ev_to_reported_ttm_ebitda"] = np.nan
    aligned.loc[
        ~aligned["reported_multiple_available"], "lease_adjusted_ev_to_reported_ttm_ebitda"
    ] = np.nan

    violations = point_in_time_violations(aligned)
    diagnostics = {
        "point_in_time_violations": violations,
        "duplicate_months": int(aligned["month_end"].duplicated().sum()),
        "reported_multiple_months": int(aligned["reported_multiple_available"].sum()),
        "short_term_borrowing_zero_imputations": int(
            aligned["short_term_borrowings_assumed_zero"].sum()
        ),
        "lease_adjusted_months": int(aligned["operating_lease_liabilities"].notna().sum()),
        "nonpositive_enterprise_value_months": int(
            (aligned["enterprise_value_standard"] <= 0).fillna(False).sum()
        ),
        "nonpositive_ebitda_months": int(
            (aligned["reported_ttm_ebitda"] <= 0).fillna(False).sum()
        ),
    }
    return ValuationDataResult(monthly=aligned, diagnostics=diagnostics)


def point_in_time_violations(monthly: pd.DataFrame) -> int:
    """Count financial disclosures used before they were available."""
    used = monthly["fundamental_available_time"].notna()
    return int(
        (
            used
            & (
                monthly["fundamental_available_time"]
                > monthly["panel_available_time"]
            )
        ).sum()
    )


def _prepare_quarterly(quarterly_panel: pd.DataFrame, config: dict) -> pd.DataFrame:
    quarterly = quarterly_panel.copy().sort_values("period_end").reset_index(drop=True)
    quarterly["period_end"] = pd.to_datetime(quarterly["period_end"])
    quarterly["panel_available_time"] = pd.to_datetime(quarterly["panel_available_time"])
    ev = config["enterprise_value"]
    required = [
        "period_end",
        "panel_available_time",
        config["market_value"]["shares_column"],
        ev["financial_debt_column"],
        ev["short_term_borrowings_column"],
        ev["cash_column"],
        ev["noncontrolling_interest_column"],
        ev["preferred_equity_column"],
        *ev["lease_columns"],
        config["earnings"]["reported_ttm_ebitda_column"],
        "cf_operating_cash_flow",
        "cf_capex",
        "cf_long_term_debt",
    ]
    _require_columns(quarterly, required)
    short_borrowings = quarterly[ev["short_term_borrowings_column"]]
    lease_columns = list(ev["lease_columns"])
    prepared = pd.DataFrame(
        {
            "latest_period_end": quarterly["period_end"],
            "fundamental_available_time": quarterly["panel_available_time"],
            "shares_outstanding": quarterly[config["market_value"]["shares_column"]],
            "financial_debt": quarterly[ev["financial_debt_column"]]
            + short_borrowings.fillna(0.0),
            "short_term_borrowings_assumed_zero": short_borrowings.isna(),
            "cash": quarterly[ev["cash_column"]],
            "noncontrolling_interest": quarterly[ev["noncontrolling_interest_column"]],
            "preferred_equity": quarterly[ev["preferred_equity_column"]],
            "operating_lease_liabilities": quarterly[lease_columns].sum(
                axis=1, min_count=len(lease_columns)
            ),
            "reported_ttm_ebitda": quarterly[
                config["earnings"]["reported_ttm_ebitda_column"]
            ],
            "free_cash_flow_ttm": (
                quarterly["cf_operating_cash_flow"] - quarterly["cf_capex"]
            ).rolling(4, min_periods=4).sum(),
            "legacy_long_term_debt": quarterly["cf_long_term_debt"],
        }
    )
    return prepared.sort_values("fundamental_available_time").reset_index(drop=True)


def _require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"valuation input columns missing: {missing}")
