"""Low-degree-of-freedom lead/lag analysis with explicit time conventions."""

from __future__ import annotations

from dataclasses import dataclass
from math import erfc, sqrt

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LeadLagResult:
    """Full lag grid and one transparent best-lag summary per relationship."""

    lag_grid: pd.DataFrame
    best_lags: pd.DataFrame


def run_lead_lag_analysis(
    frames: dict[str, pd.DataFrame], config: dict
) -> LeadLagResult:
    """Evaluate configured relationships without treating correlation as causality.

    The lag sign is fixed throughout the project: a row with ``lead_periods=k``
    pairs signal ``x(t)`` with target ``y(t+k)``. Positive values therefore mean
    that the signal leads the target.
    """
    inference = config["inference"]
    analysis_end = pd.Timestamp(config["analysis_end_date"])
    records: list[dict] = []

    for relationship in config["relationships"]:
        frame_name = relationship["frame"]
        if frame_name not in frames:
            raise ValueError(f"Missing configured frame: {frame_name}")
        frequency = relationship["frequency"]
        minimum = int(inference["minimum_observations"][frequency])
        hac_max_lag = int(inference["hac_max_lag"][frequency])

        for lead in relationship["lead_periods"]:
            lead = int(lead)
            aligned = align_relationship_sample(
                frames[frame_name],
                relationship,
                lead_periods=lead,
                analysis_end_date=analysis_end,
            )
            statistics = _relationship_statistics(
                aligned["signal_value"].to_numpy(dtype=float),
                aligned["target_value"].to_numpy(dtype=float),
                minimum_observations=minimum,
                hac_max_lag=hac_max_lag,
                stability_threshold=float(
                    inference["stability_min_absolute_correlation"]
                ),
            )
            correlation = statistics["correlation"]
            expected_sign = relationship.get("expected_sign", "unspecified")
            records.append(
                {
                    "analysis_id": config["analysis_id"],
                    "relationship_id": relationship["id"],
                    "family": relationship["family"],
                    "relationship_role": relationship.get(
                        "relationship_role", "candidate"
                    ),
                    "clock": relationship["clock"],
                    "frequency": frequency,
                    "signal": relationship["signal"],
                    "target": relationship["target"],
                    "signal_transform": _transform_label(
                        relationship["signal_transform"]
                    ),
                    "target_transform": _transform_label(
                        relationship["target_transform"]
                    ),
                    "lead_periods": lead,
                    "observations": len(aligned),
                    "sample_start": (
                        aligned["signal_date"].min() if not aligned.empty else pd.NaT
                    ),
                    "sample_end": (
                        aligned["target_date"].max() if not aligned.empty else pd.NaT
                    ),
                    "event_only": bool(relationship.get("event_only_column")),
                    "point_in_time_violations": 0,
                    "expected_sign": expected_sign,
                    "expected_sign_matches": _expected_sign_matches(
                        correlation, expected_sign
                    ),
                    **statistics,
                }
            )

    grid = pd.DataFrame.from_records(records)
    if grid.empty:
        raise ValueError("No lead/lag rows were produced")
    grid["q_value_within_relationship"] = grid.groupby(
        "relationship_id", sort=False
    )["p_value_hac"].transform(_benjamini_hochberg)
    grid["q_value_global"] = _benjamini_hochberg(grid["p_value_hac"])
    alpha = float(inference["alpha"])
    grid["adjusted_significant"] = grid["q_value_within_relationship"] <= alpha
    grid["global_adjusted_significant"] = grid["q_value_global"] <= alpha
    grid["absolute_correlation"] = grid["correlation"].abs()
    grid["rank_within_relationship"] = grid.groupby(
        "relationship_id", sort=False
    )["absolute_correlation"].rank(method="first", ascending=False)
    grid = grid.sort_values(["relationship_id", "lead_periods"]).reset_index(drop=True)
    best = _select_best_lags(grid)
    best["evidence_status"] = best.apply(_evidence_status, axis=1)
    return LeadLagResult(lag_grid=grid, best_lags=best)


def align_relationship_sample(
    frame: pd.DataFrame,
    relationship: dict,
    *,
    lead_periods: int,
    analysis_end_date,
    context_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Align one fixed-lag sample and preserve optional signal-date context."""
    frequency = relationship["frequency"]
    date_column = relationship.get(
        "date_column", "month_end" if frequency == "monthly" else "period_end"
    )
    context_columns = list(context_columns or [])
    _require_columns(frame, relationship, date_column)
    missing_context = set(context_columns) - set(frame.columns)
    if missing_context:
        raise ValueError(
            f"{relationship['id']} missing context columns: {sorted(missing_context)}"
        )
    prepared = frame.copy()
    prepared[date_column] = pd.to_datetime(prepared[date_column])
    prepared = prepared[
        prepared[date_column] <= pd.Timestamp(analysis_end_date)
    ].sort_values(date_column)
    if prepared[date_column].duplicated().any():
        raise ValueError(
            f"{relationship['id']} has duplicate dates in {date_column}"
        )
    prepared = prepared.reset_index(drop=True)
    violations = _point_in_time_violations(prepared, relationship, date_column)
    if violations:
        raise ValueError(
            f"{relationship['id']} has {violations} signal availability violations"
        )
    signal = _transform(
        prepared[relationship["signal"]], relationship["signal_transform"]
    )
    target = _transform(
        prepared[relationship["target"]], relationship["target_transform"]
    )
    lead = int(lead_periods)
    aligned = pd.DataFrame(
        {
            "signal_date": prepared[date_column],
            "target_date": prepared[date_column].shift(-lead),
            "signal_value": signal,
            "target_value": target.shift(-lead),
            "event": _event_mask(
                prepared, relationship.get("event_only_column")
            ),
        }
    )
    for column in context_columns:
        aligned[column] = prepared[column]
    aligned = aligned[aligned["event"]].dropna(
        subset=["signal_value", "target_value", "signal_date", "target_date"]
    )
    return aligned.reset_index(drop=True)


def _require_columns(
    frame: pd.DataFrame, relationship: dict, date_column: str
) -> None:
    if (
        relationship["clock"] == "availability_time"
        and not relationship.get("signal_available_time_columns")
    ):
        raise ValueError(
            f"{relationship['id']} availability_time clock requires signal timestamps"
        )
    required = {
        date_column,
        relationship["signal"],
        relationship["target"],
        *relationship.get("signal_available_time_columns", []),
    }
    if relationship.get("event_only_column"):
        required.add(relationship["event_only_column"])
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            f"{relationship['id']} missing columns: {sorted(missing)}"
        )


def _point_in_time_violations(
    frame: pd.DataFrame, relationship: dict, date_column: str
) -> int:
    if relationship["clock"] != "availability_time":
        return 0
    signal_present = frame[relationship["signal"]].notna()
    date = pd.to_datetime(frame[date_column])
    violations = pd.Series(False, index=frame.index)
    for column in relationship.get("signal_available_time_columns", []):
        available = pd.to_datetime(frame[column], errors="coerce")
        violations |= signal_present & (available.isna() | (available > date))
    return int(violations.sum())


def _transform(series: pd.Series, specification: dict) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    method = specification["method"]
    periods = int(specification.get("periods", 1))
    if method == "level":
        return values
    if method == "difference":
        return values.diff(periods)
    if method == "pct_change":
        return values.pct_change(periods=periods, fill_method=None)
    raise ValueError(f"Unsupported transform method: {method}")


def _transform_label(specification: dict) -> str:
    method = specification["method"]
    periods = int(specification.get("periods", 1))
    return method if method == "level" else f"{method}_{periods}"


def _event_mask(frame: pd.DataFrame, event_column: str | None) -> pd.Series:
    if not event_column:
        return pd.Series(True, index=frame.index)
    values = frame[event_column]
    return values.notna() & values.ne(values.shift(1))


def _relationship_statistics(
    x: np.ndarray,
    y: np.ndarray,
    *,
    minimum_observations: int,
    hac_max_lag: int,
    stability_threshold: float,
) -> dict:
    n = len(x)
    empty = {
        "correlation": float("nan"),
        "hac_slope": float("nan"),
        "hac_standard_error": float("nan"),
        "hac_t_stat": float("nan"),
        "p_value_hac": float("nan"),
        "hac_ci_lower": float("nan"),
        "hac_ci_upper": float("nan"),
        "first_half_correlation": float("nan"),
        "second_half_correlation": float("nan"),
        "direction_stable": False,
        "stability_status": "INSUFFICIENT",
    }
    if n < minimum_observations or np.std(x) == 0 or np.std(y) == 0:
        return empty
    correlation = float(np.corrcoef(x, y)[0, 1])
    slope, standard_error = _standardized_hac_slope(x, y, hac_max_lag)
    t_stat = slope / standard_error if standard_error > 0 else float("nan")
    p_value = erfc(abs(t_stat) / sqrt(2.0)) if np.isfinite(t_stat) else float("nan")
    split = n // 2
    first = _safe_correlation(x[:split], y[:split])
    second = _safe_correlation(x[split:], y[split:])
    direction_stable = bool(
        np.isfinite(first)
        and np.isfinite(second)
        and np.sign(correlation) == np.sign(first) == np.sign(second)
    )
    stable = bool(
        direction_stable
        and abs(first) >= stability_threshold
        and abs(second) >= stability_threshold
    )
    return {
        "correlation": correlation,
        "hac_slope": slope,
        "hac_standard_error": standard_error,
        "hac_t_stat": t_stat,
        "p_value_hac": p_value,
        "hac_ci_lower": slope - 1.96 * standard_error,
        "hac_ci_upper": slope + 1.96 * standard_error,
        "first_half_correlation": first,
        "second_half_correlation": second,
        "direction_stable": direction_stable,
        "stability_status": "STABLE" if stable else "UNSTABLE",
    }


def _standardized_hac_slope(
    x: np.ndarray, y: np.ndarray, max_lag: int
) -> tuple[float, float]:
    x_standard = (x - np.mean(x)) / np.std(x)
    y_standard = (y - np.mean(y)) / np.std(y)
    design = np.column_stack([np.ones(len(x_standard)), x_standard])
    inverse = np.linalg.pinv(design.T @ design)
    beta = inverse @ design.T @ y_standard
    residual = y_standard - design @ beta
    meat = np.zeros((2, 2), dtype=float)
    for index in range(len(x_standard)):
        vector = design[index][:, None]
        meat += residual[index] ** 2 * (vector @ vector.T)
    effective_lag = min(max_lag, max(len(x_standard) - 2, 0))
    for lag in range(1, effective_lag + 1):
        weight = 1.0 - lag / (effective_lag + 1.0)
        cross = np.zeros((2, 2), dtype=float)
        for index in range(lag, len(x_standard)):
            current = design[index][:, None]
            previous = design[index - lag][:, None]
            cross += residual[index] * residual[index - lag] * (
                current @ previous.T
            )
        meat += weight * (cross + cross.T)
    covariance = inverse @ meat @ inverse
    covariance *= len(x_standard) / max(len(x_standard) - design.shape[1], 1)
    variance = max(float(covariance[1, 1]), 0.0)
    return float(beta[1]), sqrt(variance)


def _safe_correlation(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _expected_sign_matches(correlation: float, expected_sign: str) -> bool | None:
    if not np.isfinite(correlation) or expected_sign == "unspecified":
        return None
    if expected_sign == "positive":
        return bool(correlation > 0)
    if expected_sign == "negative":
        return bool(correlation < 0)
    raise ValueError(f"Unsupported expected sign: {expected_sign}")


def _benjamini_hochberg(values: pd.Series) -> pd.Series:
    result = pd.Series(float("nan"), index=values.index, dtype=float)
    clean = pd.to_numeric(values, errors="coerce").dropna().sort_values()
    count = len(clean)
    if not count:
        return result
    adjusted = clean.to_numpy(dtype=float) * count / np.arange(1, count + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    result.loc[clean.index] = np.minimum(adjusted, 1.0)
    return result


def _select_best_lags(grid: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.Series] = []
    for _, group in grid.groupby("relationship_id", sort=True):
        eligible = group.dropna(subset=["absolute_correlation"])
        if eligible.empty:
            rows.append(group.sort_values("lead_periods").iloc[0])
            continue
        chosen = eligible.sort_values(
            ["absolute_correlation", "lead_periods"], ascending=[False, True]
        ).iloc[0]
        rows.append(chosen)
    return pd.DataFrame(rows).reset_index(drop=True)


def _evidence_status(row: pd.Series) -> str:
    if row["relationship_role"] == "diagnostic_identity":
        return "DIAGNOSTIC"
    if row["stability_status"] == "INSUFFICIENT":
        return "INSUFFICIENT"
    if row["stability_status"] != "STABLE":
        return "UNSTABLE"
    if row["expected_sign_matches"] is False:
        return "CONTRADICTORY"
    if bool(row["adjusted_significant"]) and bool(
        row["global_adjusted_significant"]
    ):
        return "STRONG"
    return "DIRECTIONAL"
