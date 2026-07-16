"""Point-in-time extraction of CF quarterly financial facts."""

from __future__ import annotations

import pandas as pd


def extract_quarterly_financials(
    facts: pd.DataFrame,
    periods: pd.DataFrame,
    metrics: list[dict],
) -> pd.DataFrame:
    """Extract instant facts and quarter-only flows, deriving Q4 from annual less Q1-Q3."""
    source = facts.copy()
    for column in ("period_start", "period_end", "filing_date"):
        source[column] = pd.to_datetime(source[column], errors="coerce")
    output = periods[["period_end"]].copy()
    for metric in metrics:
        values: list[float] = []
        available: list[pd.Timestamp] = []
        for period_end, cutoff in periods[["period_end", "panel_available_time"]].itertuples(
            index=False, name=None
        ):
            value, filing = _financial_value(
                source,
                pd.Timestamp(period_end),
                pd.Timestamp(cutoff),
                list(metric["concepts"]),
                str(metric["kind"]),
            )
            values.append(value)
            available.append(filing)
        name = str(metric["output_col"])
        output[name] = values
        output[f"{name}__available_time"] = available
    return output


def _financial_value(
    facts: pd.DataFrame,
    period_end: pd.Timestamp,
    cutoff: pd.Timestamp,
    concepts: list[str],
    kind: str,
) -> tuple[float, pd.Timestamp]:
    if kind == "latest_instant":
        latest = facts[
            facts["concept"].isin(concepts)
            & (facts["filing_date"] <= cutoff)
            & (facts["period_end"] <= cutoff)
            & facts["period_start"].isna()
        ].copy()
        return _preferred(latest, concepts)
    eligible = facts[
        facts["concept"].isin(concepts)
        & (facts["period_end"] == period_end)
        & (facts["filing_date"] <= cutoff)
        & facts["form"].isin(["10-Q", "10-K"])
    ].copy()
    if kind == "instant":
        eligible = eligible[eligible["period_start"].isna()]
        return _preferred(eligible, concepts)
    if kind != "flow":
        raise ValueError(f"Unsupported financial metric kind: {kind}")
    duration = (eligible["period_end"] - eligible["period_start"]).dt.days
    quarter = eligible[duration.between(70, 100)]
    if not quarter.empty:
        return _preferred(quarter, concepts)
    duration_ranges = {2: (150, 210), 3: (240, 300), 4: (330, 370)}
    if period_end.quarter not in duration_ranges:
        return float("nan"), pd.NaT
    low, high = duration_ranges[period_end.quarter]
    cumulative_value, cumulative_filing = _preferred(eligible[duration.between(low, high)], concepts)
    if pd.isna(cumulative_value):
        return float("nan"), pd.NaT
    prior_end = period_end - pd.offsets.QuarterEnd()
    prior = facts[
        facts["concept"].isin(concepts)
        & (facts["period_end"] == prior_end)
        & (facts["filing_date"] <= cutoff)
        & facts["form"].eq("10-Q")
    ].copy()
    prior_duration = (prior["period_end"] - prior["period_start"]).dt.days
    prior_limit = {2: (70, 100), 3: (150, 210), 4: (240, 300)}[period_end.quarter]
    prior_value, _ = _preferred(prior[prior_duration.between(*prior_limit)], concepts)
    if pd.isna(prior_value):
        return float("nan"), pd.NaT
    return float(cumulative_value - prior_value), cumulative_filing


def _preferred(frame: pd.DataFrame, concepts: list[str]) -> tuple[float, pd.Timestamp]:
    for concept in concepts:
        rows = frame[frame["concept"] == concept].sort_values("filing_date")
        if not rows.empty:
            row = rows.iloc[-1]
            return float(row["value"]), pd.Timestamp(row["filing_date"])
    return float("nan"), pd.NaT
