"""Fixed-lag rolling and regime stability checks for M4.2."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .lead_lag import align_relationship_sample


@dataclass(frozen=True)
class StabilityResult:
    """Rolling windows, descriptive slices, and predeclared decisions."""

    rolling_windows: pd.DataFrame
    slices: pd.DataFrame
    decisions: pd.DataFrame


def run_stability_analysis(
    frames: dict[str, pd.DataFrame],
    lead_lag_config: dict,
    best_lags: pd.DataFrame,
    config: dict,
) -> StabilityResult:
    """Test M4.1 best lags without reselecting lags inside any subsample."""
    relationships = {
        relationship["id"]: relationship
        for relationship in lead_lag_config["relationships"]
    }
    roles = _relationship_roles(config["candidate_roles"])
    if set(relationships) != set(roles):
        missing = set(relationships) - set(roles)
        extra = set(roles) - set(relationships)
        raise ValueError(
            f"Candidate-role coverage differs from relationships: missing={sorted(missing)}, "
            f"extra={sorted(extra)}"
        )
    if best_lags["relationship_id"].duplicated().any():
        raise ValueError("M4.1 best-lag input contains duplicate relationships")
    best_by_id = best_lags.set_index("relationship_id")
    if set(best_by_id.index) != set(relationships):
        raise ValueError("M4.1 best-lag coverage differs from configured relationships")

    rolling_records: list[dict] = []
    slice_records: list[dict] = []
    samples: dict[str, pd.DataFrame] = {}
    for relationship_id, relationship in relationships.items():
        best = best_by_id.loc[relationship_id]
        fixed_lead = int(best["lead_periods"])
        if fixed_lead not in [int(value) for value in relationship["lead_periods"]]:
            raise ValueError(f"{relationship_id} best lag is outside the declared grid")
        frame_name = relationship["frame"]
        if frame_name not in frames:
            raise ValueError(f"Missing configured frame: {frame_name}")
        context = _add_context(frames[frame_name], relationship["frequency"])
        aligned = align_relationship_sample(
            context,
            relationship,
            lead_periods=fixed_lead,
            analysis_end_date=config["analysis_end_date"],
            context_columns=["__gas_level", "__spread_abs_change"],
        )
        samples[relationship_id] = aligned
        recomputed = _safe_correlation(
            aligned["signal_value"], aligned["target_value"]
        )
        if not np.isclose(recomputed, float(best["correlation"]), equal_nan=True):
            raise ValueError(
                f"{relationship_id} fixed-lag sample no longer matches M4.1"
            )
        rolling_records.extend(
            _rolling_records(
                aligned,
                relationship,
                fixed_lead,
                roles[relationship_id],
                config,
            )
        )
        slice_records.extend(
            _slice_records(
                aligned,
                relationship,
                fixed_lead,
                roles[relationship_id],
                config,
            )
        )

    rolling = pd.DataFrame.from_records(rolling_records).sort_values(
        ["relationship_id", "window_end"]
    ).reset_index(drop=True)
    slices = pd.DataFrame.from_records(slice_records).sort_values(
        ["relationship_id", "slice_type", "slice_name"]
    ).reset_index(drop=True)
    decisions = _build_decisions(
        best_by_id, relationships, roles, samples, rolling, slices, config
    )
    return StabilityResult(rolling, slices, decisions)


def _add_context(frame: pd.DataFrame, frequency: str) -> pd.DataFrame:
    result = frame.copy()
    if frequency == "monthly":
        date_column = "month_end"
        gas_column = "henry_hub_month_mean"
        spread_column = "global_urea_gas_spread_month_mean"
    elif frequency == "quarterly":
        date_column = "period_end"
        gas_column = "henry_hub_quarter_mean"
        spread_column = "global_urea_gas_spread_quarter_mean"
    else:
        raise ValueError(f"Unsupported frequency: {frequency}")
    missing = {date_column, gas_column, spread_column} - set(result.columns)
    if missing:
        raise ValueError(f"Stability context is missing columns: {sorted(missing)}")
    result[date_column] = pd.to_datetime(result[date_column])
    result = result.sort_values(date_column).reset_index(drop=True)
    result["__gas_level"] = pd.to_numeric(result[gas_column], errors="coerce")
    spread = pd.to_numeric(result[spread_column], errors="coerce")
    result["__spread_abs_change"] = spread.diff().abs()
    return result


def _rolling_records(
    aligned: pd.DataFrame,
    relationship: dict,
    fixed_lead: int,
    candidate_role: str,
    config: dict,
) -> list[dict]:
    frequency = relationship["frequency"]
    window_key = "event_only" if relationship.get("event_only_column") else frequency
    window = int(config["rolling"]["window_observations"][window_key])
    if len(aligned) < window:
        return []
    records: list[dict] = []
    for end in range(window - 1, len(aligned)):
        sample = aligned.iloc[end - window + 1 : end + 1]
        correlation = _safe_correlation(
            sample["signal_value"], sample["target_value"]
        )
        records.append(
            {
                "analysis_id": config["analysis_id"],
                "relationship_id": relationship["id"],
                "candidate_role": candidate_role,
                "frequency": frequency,
                "fixed_lead_periods": fixed_lead,
                "window_observations": window,
                "window_start": sample["signal_date"].iloc[0],
                "window_end": sample["target_date"].iloc[-1],
                "correlation": correlation,
                "expected_sign": relationship["expected_sign"],
                "expected_sign_matches": _expected_sign_matches(
                    correlation, relationship["expected_sign"]
                ),
            }
        )
    return records


def _slice_records(
    aligned: pd.DataFrame,
    relationship: dict,
    fixed_lead: int,
    candidate_role: str,
    config: dict,
) -> list[dict]:
    minimum_key = (
        "event_only" if relationship.get("event_only_column") else relationship["frequency"]
    )
    minimum = int(config["slices"]["minimum_observations"][minimum_key])
    groups: list[tuple[str, str, pd.Series]] = []
    target_period = pd.to_datetime(aligned["target_date"])
    season_config = config["slices"][
        "monthly_seasons"
        if relationship["frequency"] == "monthly"
        else "quarterly_seasons"
    ]
    season_value = (
        target_period.dt.month
        if relationship["frequency"] == "monthly"
        else target_period.dt.quarter
    )
    for name, values in season_config.items():
        groups.append(("season", name, season_value.isin(values)))

    gas = pd.to_numeric(aligned["__gas_level"], errors="coerce")
    gas_threshold = gas.quantile(float(config["slices"]["gas_regime_quantile"]))
    groups.extend(
        [
            ("gas_regime", "low_gas", gas.notna() & (gas <= gas_threshold)),
            ("gas_regime", "high_gas", gas.notna() & (gas > gas_threshold)),
        ]
    )
    stress = pd.to_numeric(aligned["__spread_abs_change"], errors="coerce")
    stress_threshold = stress.quantile(
        float(config["slices"]["stress_regime_quantile"])
    )
    groups.extend(
        [
            (
                "spread_stress",
                "normal_change",
                stress.notna() & (stress <= stress_threshold),
            ),
            (
                "spread_stress",
                "large_change",
                stress.notna() & (stress > stress_threshold),
            ),
        ]
    )

    records: list[dict] = []
    for slice_type, slice_name, mask in groups:
        sample = aligned[mask]
        eligible = len(sample) >= minimum
        correlation = (
            _safe_correlation(sample["signal_value"], sample["target_value"])
            if eligible
            else float("nan")
        )
        records.append(
            {
                "analysis_id": config["analysis_id"],
                "relationship_id": relationship["id"],
                "candidate_role": candidate_role,
                "frequency": relationship["frequency"],
                "fixed_lead_periods": fixed_lead,
                "slice_type": slice_type,
                "slice_name": slice_name,
                "observations": len(sample),
                "minimum_observations": minimum,
                "eligible": eligible,
                "correlation": correlation,
                "expected_sign": relationship["expected_sign"],
                "expected_sign_matches": (
                    _expected_sign_matches(correlation, relationship["expected_sign"])
                    if eligible
                    else None
                ),
                "sample_start": (
                    sample["signal_date"].min() if not sample.empty else pd.NaT
                ),
                "sample_end": (
                    sample["target_date"].max() if not sample.empty else pd.NaT
                ),
            }
        )
    return records


def _build_decisions(
    best_by_id: pd.DataFrame,
    relationships: dict[str, dict],
    roles: dict[str, str],
    samples: dict[str, pd.DataFrame],
    rolling: pd.DataFrame,
    slices: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    thresholds = config["decision_thresholds"]
    rows: list[dict] = []
    for relationship_id, relationship in relationships.items():
        best = best_by_id.loc[relationship_id]
        relationship_windows = rolling[
            rolling["relationship_id"] == relationship_id
        ]
        valid_window_sign = relationship_windows["expected_sign_matches"].dropna()
        window_sign_share = (
            float(valid_window_sign.astype(float).mean())
            if not valid_window_sign.empty
            else float("nan")
        )
        median_correlation = (
            float(relationship_windows["correlation"].median())
            if not relationship_windows.empty
            else float("nan")
        )
        relationship_slices = slices[slices["relationship_id"] == relationship_id]
        season_share = _slice_expected_share(relationship_slices, "season")
        gas_share = _slice_expected_share(relationship_slices, "gas_regime")
        stress_share = _slice_expected_share(relationship_slices, "spread_stress")
        gas_minimum_correlation = _slice_minimum_absolute_correlation(
            relationship_slices, "gas_regime"
        )
        stress_minimum_correlation = _slice_minimum_absolute_correlation(
            relationship_slices, "spread_stress"
        )
        minimum_windows = int(config["rolling"]["minimum_windows"])
        rolling_pass = bool(
            len(relationship_windows) >= minimum_windows
            and np.isfinite(window_sign_share)
            and window_sign_share
            >= float(thresholds["minimum_expected_sign_window_share"])
            and np.isfinite(median_correlation)
            and abs(median_correlation)
            >= float(thresholds["minimum_median_absolute_correlation"])
        )
        regime_minimum = float(
            thresholds["minimum_regime_expected_sign_share"]
        )
        regime_correlation_minimum = float(
            thresholds["minimum_regime_absolute_correlation"]
        )
        regime_pass = bool(
            np.isfinite(gas_share)
            and gas_share >= regime_minimum
            and np.isfinite(stress_share)
            and stress_share >= regime_minimum
            and np.isfinite(gas_minimum_correlation)
            and gas_minimum_correlation >= regime_correlation_minimum
            and np.isfinite(stress_minimum_correlation)
            and stress_minimum_correlation >= regime_correlation_minimum
        )
        decision, reason = _decision(
            roles[relationship_id],
            str(best["evidence_status"]),
            rolling_pass,
            regime_pass,
        )
        rows.append(
            {
                "analysis_id": config["analysis_id"],
                "relationship_id": relationship_id,
                "family": relationship["family"],
                "candidate_role": roles[relationship_id],
                "m4_1_evidence_status": best["evidence_status"],
                "fixed_lead_periods": int(best["lead_periods"]),
                "full_sample_observations": len(samples[relationship_id]),
                "full_sample_correlation": float(best["correlation"]),
                "rolling_window_count": len(relationship_windows),
                "rolling_median_correlation": median_correlation,
                "rolling_min_correlation": _finite_stat(
                    relationship_windows["correlation"], "min"
                ),
                "rolling_max_correlation": _finite_stat(
                    relationship_windows["correlation"], "max"
                ),
                "rolling_expected_sign_share": window_sign_share,
                "season_expected_sign_share": season_share,
                "gas_regime_expected_sign_share": gas_share,
                "stress_regime_expected_sign_share": stress_share,
                "gas_regime_minimum_absolute_correlation": gas_minimum_correlation,
                "stress_regime_minimum_absolute_correlation": stress_minimum_correlation,
                "rolling_pass": rolling_pass,
                "regime_pass": regime_pass,
                "decision": decision,
                "decision_reason": reason,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["candidate_role", "relationship_id"]
    ).reset_index(drop=True)


def _relationship_roles(groups: dict[str, list[str]]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for role, relationship_ids in groups.items():
        for relationship_id in relationship_ids:
            if relationship_id in roles:
                raise ValueError(f"Relationship has multiple candidate roles: {relationship_id}")
            roles[relationship_id] = role
    return roles


def _slice_expected_share(slices: pd.DataFrame, slice_type: str) -> float:
    selected = slices[
        (slices["slice_type"] == slice_type) & slices["eligible"]
    ]["expected_sign_matches"].dropna()
    return (
        float(selected.astype(float).mean())
        if not selected.empty
        else float("nan")
    )


def _slice_minimum_absolute_correlation(
    slices: pd.DataFrame, slice_type: str
) -> float:
    selected = pd.to_numeric(
        slices[(slices["slice_type"] == slice_type) & slices["eligible"]][
            "correlation"
        ],
        errors="coerce",
    ).dropna()
    return float(selected.abs().min()) if not selected.empty else float("nan")


def _decision(
    role: str, evidence_status: str, rolling_pass: bool, regime_pass: bool
) -> tuple[str, str]:
    if role == "diagnostic_identity":
        return "DIAGNOSTIC", "formula identity; never counted as independent evidence"
    if evidence_status != "STRONG":
        return "REJECT", f"M4.1 evidence is {evidence_status}, not STRONG"
    if not rolling_pass or not regime_pass:
        failures = []
        if not rolling_pass:
            failures.append("rolling thresholds failed")
        if not regime_pass:
            failures.append("gas/stress regime direction failed")
        return "CONDITIONAL", "; ".join(failures)
    accepted = {
        "operating_bridge": "ACCEPT_BRIDGE",
        "cycle_core_validation": "ACCEPT_CORE_VALIDATION",
        "demand_candidate": "ACCEPT_DEMAND",
        "market_confirmation": "ACCEPT_CONFIRMATION",
    }
    return accepted[role], "M4.1, rolling, gas regime, and stress regime checks passed"


def _safe_correlation(x: pd.Series, y: pd.Series) -> float:
    x_values = pd.to_numeric(x, errors="coerce").to_numpy(dtype=float)
    y_values = pd.to_numeric(y, errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(x_values) & np.isfinite(y_values)
    x_values = x_values[valid]
    y_values = y_values[valid]
    if len(x_values) < 3 or np.std(x_values) == 0 or np.std(y_values) == 0:
        return float("nan")
    return float(np.corrcoef(x_values, y_values)[0, 1])


def _expected_sign_matches(correlation: float, expected_sign: str) -> bool | None:
    if not np.isfinite(correlation):
        return None
    if expected_sign == "positive":
        return bool(correlation > 0)
    if expected_sign == "negative":
        return bool(correlation < 0)
    raise ValueError(f"Unsupported expected sign: {expected_sign}")


def _finite_stat(values: pd.Series, operation: str) -> float:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return float("nan")
    return float(getattr(numeric, operation)())
