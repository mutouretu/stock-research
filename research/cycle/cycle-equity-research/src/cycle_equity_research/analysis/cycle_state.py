"""Point-in-time rule-based operating-cycle states for CF."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


STATES = ("RECOVERY", "EXPANSION", "PEAK_RISK", "CONTRACTION", "TROUGH", "MIXED")


@dataclass(frozen=True)
class CycleStateResult:
    """Monthly state history and transition episodes."""

    monthly: pd.DataFrame
    episodes: pd.DataFrame


def build_cycle_states(monthly_panel: pd.DataFrame, config: dict) -> CycleStateResult:
    """Build a causal state timeline from one non-duplicated core signal."""
    frame = monthly_panel.copy()
    frame["month_end"] = pd.to_datetime(frame["month_end"])
    frame["panel_available_time"] = pd.to_datetime(frame["panel_available_time"])
    frame = frame.loc[
        frame["month_end"] <= pd.Timestamp(config["analysis_end_date"])
    ].sort_values("month_end").reset_index(drop=True)
    _validate_unique_months(frame)

    signal_config = config["core_signal"]
    signal = pd.to_numeric(frame[signal_config["column"]], errors="coerce")
    source_times = [
        pd.to_datetime(frame[column])
        for column in signal_config["source_available_time_columns"]
    ]
    availability_ok = pd.Series(True, index=frame.index)
    for source_time in source_times:
        availability_ok &= source_time.notna() & (
            source_time <= frame["panel_available_time"]
        )
    core_available = signal.notna() & availability_ok

    window = int(signal_config["level_window_months"])
    minimum = int(signal_config["minimum_history_months"])
    momentum_periods = int(signal_config["momentum_months"])
    level_z = expanding_trailing_zscore(signal, window=window, minimum=minimum)
    momentum = signal.diff(momentum_periods)
    momentum_z = expanding_trailing_zscore(
        momentum, window=window, minimum=minimum
    )
    clip = float(signal_config["z_clip"])
    weights = signal_config["score_weights"]
    score = (
        float(weights["level"]) * level_z.clip(-clip, clip)
        + float(weights["momentum"]) * momentum_z.clip(-clip, clip)
    )

    raw_states: list[str] = []
    raw_reasons: list[str] = []
    for available, level, direction in zip(core_available, level_z, momentum_z):
        if not available:
            raw_states.append("MIXED")
            raw_reasons.append("DATA_GAP")
        elif not np.isfinite(level) or not np.isfinite(direction):
            raw_states.append("MIXED")
            raw_reasons.append("WARMUP")
        else:
            raw_states.append(classify_raw_state(level, direction, config))
            raw_reasons.append("RULE")

    state_rows = apply_state_machine(
        raw_states, raw_reasons, level_z.tolist(), momentum_z.tolist(), config
    )
    state_frame = pd.DataFrame(state_rows)
    confirmation = build_confirmation_overlay(frame, config)

    output = pd.DataFrame(
        {
            "instrument": frame["instrument"],
            "month_end": frame["month_end"],
            "panel_available_time": frame["panel_available_time"],
            "core_signal": signal,
            "core_signal_available": core_available,
            "level_z": level_z,
            f"momentum_{momentum_periods}m": momentum,
            "momentum_z": momentum_z,
            "cycle_score": score,
            "raw_state": raw_states,
            "raw_state_reason": raw_reasons,
        }
    )
    output = pd.concat([output, state_frame, confirmation], axis=1)
    return CycleStateResult(monthly=output, episodes=build_episodes(output))


def expanding_trailing_zscore(
    values: pd.Series, *, window: int, minimum: int
) -> pd.Series:
    """Normalize using only the current and preceding observations."""
    rolling = values.rolling(window=window, min_periods=minimum)
    mean = rolling.mean()
    standard_deviation = rolling.std(ddof=0).replace(0.0, np.nan)
    return (values - mean) / standard_deviation


def classify_raw_state(level_z: float, momentum_z: float, config: dict) -> str:
    """Apply predeclared two-dimensional entry rules without valuation inputs."""
    thresholds = config["state_thresholds"]
    if _matches(level_z, momentum_z, thresholds["peak_risk"]):
        return "PEAK_RISK"
    if _matches(level_z, momentum_z, thresholds["expansion"]):
        return "EXPANSION"
    if _matches(level_z, momentum_z, thresholds["trough"]):
        return "TROUGH"
    if _matches(level_z, momentum_z, thresholds["contraction"]):
        return "CONTRACTION"
    if _matches(level_z, momentum_z, thresholds["recovery"]):
        return "RECOVERY"
    return "MIXED"


def apply_state_machine(
    raw_states: list[str],
    raw_reasons: list[str],
    levels: list[float],
    momentums: list[float],
    config: dict,
) -> list[dict]:
    """Apply hysteresis, confirmation, and a hard data-gap safety override."""
    rules = config["hysteresis"]
    confirmation_months = int(rules["confirmation_months"])
    minimum_state_months = int(rules["minimum_state_months"])
    current = "MIXED"
    age = 0
    pending: str | None = None
    pending_count = 0
    rows: list[dict] = []

    for raw, reason, level, momentum in zip(
        raw_states, raw_reasons, levels, momentums
    ):
        previous = current
        transition_reason = "UNCHANGED"
        if reason in {"DATA_GAP", "WARMUP"}:
            current = "MIXED"
            pending = None
            pending_count = 0
            transition_reason = reason
        else:
            effective = raw
            if current != "MIXED" and raw != current and _hold_current_state(
                current, level, momentum, rules["hold_thresholds"]
            ):
                effective = current
            if effective == current:
                pending = None
                pending_count = 0
            else:
                if pending == effective:
                    pending_count += 1
                else:
                    pending = effective
                    pending_count = 1
                duration_ok = current == "MIXED" or age >= minimum_state_months
                if pending_count >= confirmation_months and duration_ok:
                    current = effective
                    pending = None
                    pending_count = 0
                    transition_reason = "CONFIRMED_RULE"

        changed = current != previous
        age = 1 if changed or age == 0 else age + 1
        rows.append(
            {
                "state": current,
                "state_reason": transition_reason,
                "state_age_months": age,
                "state_changed": changed,
                "pending_state": pending,
                "pending_months": pending_count,
            }
        )
    return rows


def build_confirmation_overlay(frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Create company and market labels that never feed back into the state."""
    confirmation = config["confirmation"]
    company_value = pd.to_numeric(
        frame[confirmation["company_column"]], errors="coerce"
    )
    company_time = pd.to_datetime(
        frame[confirmation["company_available_time_column"]]
    )
    company_age = (frame["panel_available_time"] - company_time).dt.days
    company_valid = (
        company_value.notna()
        & company_time.notna()
        & (company_time <= frame["panel_available_time"])
        & company_age.between(0, int(confirmation["company_max_age_days"]))
    )
    company_direction = _directions(
        company_value,
        float(confirmation["company_direction_threshold"]),
        company_valid,
    )
    market_value = pd.to_numeric(frame[confirmation["market_column"]], errors="coerce")
    market_direction = _directions(
        market_value,
        float(confirmation["market_direction_threshold"]),
        market_value.notna(),
    )
    labels = [
        _combine_confirmation(company, market)
        for company, market in zip(company_direction, market_direction)
    ]
    return pd.DataFrame(
        {
            "company_confirmation_value": company_value,
            "company_confirmation_age_days": company_age,
            "company_confirmation": company_direction,
            "market_confirmation_value": market_value,
            "market_confirmation": market_direction,
            "confirmation_overlay": labels,
        }
    )


def build_episodes(monthly: pd.DataFrame) -> pd.DataFrame:
    """Collapse consecutive monthly states into auditable episodes."""
    group = monthly["state"].ne(monthly["state"].shift()).cumsum()
    rows = []
    for _, episode in monthly.groupby(group, sort=False):
        rows.append(
            {
                "state": episode["state"].iloc[0],
                "start_month": episode["month_end"].iloc[0],
                "end_month": episode["month_end"].iloc[-1],
                "months": len(episode),
                "start_score": episode["cycle_score"].iloc[0],
                "end_score": episode["cycle_score"].iloc[-1],
                "end_confirmation": episode["confirmation_overlay"].iloc[-1],
            }
        )
    return pd.DataFrame(rows)


def point_in_time_violations(monthly: pd.DataFrame, config: dict) -> int:
    """Count source timestamps later than the panel timestamp on valid signals."""
    valid = monthly[config["core_signal"]["column"]].notna()
    violations = pd.Series(False, index=monthly.index)
    for column in config["core_signal"]["source_available_time_columns"]:
        source_time = pd.to_datetime(monthly[column])
        violations |= valid & (
            source_time.isna()
            | (source_time > pd.to_datetime(monthly["panel_available_time"]))
        )
    company = config["confirmation"]["company_available_time_column"]
    company_time = pd.to_datetime(monthly[company])
    company_value = monthly[config["confirmation"]["company_column"]]
    violations |= company_value.notna() & (
        company_time.isna()
        | (company_time > pd.to_datetime(monthly["panel_available_time"]))
    )
    return int(violations.sum())


def _matches(level: float, momentum: float, thresholds: dict) -> bool:
    checks = {
        "level_min": level >= thresholds.get("level_min", -np.inf),
        "level_max": level <= thresholds.get("level_max", np.inf),
        "momentum_min": momentum >= thresholds.get("momentum_min", -np.inf),
        "momentum_max": momentum <= thresholds.get("momentum_max", np.inf),
    }
    return all(checks.values())


def _hold_current_state(
    state: str, level: float, momentum: float, thresholds: dict
) -> bool:
    return state in thresholds and _matches(level, momentum, thresholds[state])


def _directions(
    values: pd.Series, threshold: float, valid: pd.Series
) -> pd.Series:
    result = pd.Series("UNAVAILABLE", index=values.index, dtype="object")
    result.loc[valid & (values > threshold)] = "POSITIVE"
    result.loc[valid & (values < -threshold)] = "NEGATIVE"
    result.loc[valid & values.between(-threshold, threshold)] = "NEUTRAL"
    return result


def _combine_confirmation(company: str, market: str) -> str:
    if company == market == "POSITIVE":
        return "CONFIRMED_POSITIVE"
    if company == market == "NEGATIVE":
        return "CONFIRMED_NEGATIVE"
    if {company, market} == {"POSITIVE", "NEGATIVE"}:
        return "DIVERGENT"
    directional = [value for value in (company, market) if value in {"POSITIVE", "NEGATIVE"}]
    if directional:
        return f"PARTIAL_{directional[0]}"
    if company == market == "UNAVAILABLE":
        return "UNAVAILABLE"
    return "NEUTRAL"


def _validate_unique_months(frame: pd.DataFrame) -> None:
    if frame["month_end"].duplicated().any():
        raise ValueError("monthly panel contains duplicate month_end values")
    if not frame["month_end"].is_monotonic_increasing:
        raise ValueError("monthly panel must be sorted by month_end")
