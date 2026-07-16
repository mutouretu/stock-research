from copy import deepcopy

import numpy as np
import pandas as pd

from cycle_equity_research.analysis.cycle_state import (
    apply_state_machine,
    build_cycle_states,
    classify_raw_state,
    point_in_time_violations,
)


def _config() -> dict:
    return {
        "analysis_id": "synthetic_cycle_state",
        "analysis_end_date": "2030-12-31",
        "core_signal": {
            "column": "spread",
            "source_available_time_columns": ["gas_time", "urea_time"],
            "level_window_months": 36,
            "minimum_history_months": 12,
            "momentum_months": 3,
            "z_clip": 2.0,
            "score_weights": {"level": 0.5, "momentum": 0.5},
        },
        "state_thresholds": {
            "expansion": {"level_min": 0.25, "momentum_min": 0.25},
            "peak_risk": {"level_min": 0.75, "momentum_max": -0.25},
            "contraction": {"level_max": -0.25, "momentum_max": -0.25},
            "trough": {"level_max": -0.75, "momentum_min": 0.25},
            "recovery": {"level_max": 0.25, "momentum_min": 0.25},
        },
        "hysteresis": {
            "confirmation_months": 2,
            "minimum_state_months": 3,
            "hold_thresholds": {
                "EXPANSION": {"level_min": 0.10, "momentum_min": 0.10},
                "PEAK_RISK": {"level_min": 0.50, "momentum_max": 0.10},
                "CONTRACTION": {"level_max": -0.10, "momentum_max": -0.10},
                "TROUGH": {"level_max": -0.50, "momentum_min": -0.10},
                "RECOVERY": {"level_max": 0.40, "momentum_min": 0.10},
            },
        },
        "confirmation": {
            "company_column": "margin_change",
            "company_available_time_column": "company_time",
            "company_max_age_days": 180,
            "company_direction_threshold": 0.01,
            "market_column": "momentum_6m",
            "market_direction_threshold": 0.10,
        },
    }


def _panel(periods: int = 84) -> pd.DataFrame:
    dates = pd.date_range("2015-01-31", periods=periods, freq="ME")
    x = np.arange(periods, dtype=float)
    spread = 220 + 0.35 * x + 35 * np.sin(x / 5)
    return pd.DataFrame(
        {
            "instrument": "CF",
            "month_end": dates,
            "panel_available_time": dates,
            "spread": spread,
            "gas_time": dates,
            "urea_time": dates - pd.Timedelta(days=10),
            "margin_change": np.where(x % 12 < 6, 0.03, -0.03),
            "company_time": dates - pd.Timedelta(days=20),
            "momentum_6m": np.where(x % 10 < 5, 0.2, -0.2),
        }
    )


def test_raw_state_rules_cover_all_named_states() -> None:
    config = _config()
    cases = {
        (0.5, 0.5): "EXPANSION",
        (1.0, -0.5): "PEAK_RISK",
        (-0.5, -0.5): "CONTRACTION",
        (-1.0, 0.5): "TROUGH",
        (0.0, 0.5): "RECOVERY",
        (0.0, 0.0): "MIXED",
    }
    for values, expected in cases.items():
        assert classify_raw_state(*values, config) == expected


def test_state_machine_requires_confirmation_and_minimum_duration() -> None:
    config = _config()
    raw = [
        "EXPANSION",
        "EXPANSION",
        "CONTRACTION",
        "CONTRACTION",
        "CONTRACTION",
        "CONTRACTION",
    ]
    rows = apply_state_machine(
        raw,
        ["RULE"] * len(raw),
        [1.0, 1.0, -1.0, -1.0, -1.0, -1.0],
        [1.0, 1.0, -1.0, -1.0, -1.0, -1.0],
        config,
    )
    assert [row["state"] for row in rows] == [
        "MIXED",
        "EXPANSION",
        "EXPANSION",
        "EXPANSION",
        "CONTRACTION",
        "CONTRACTION",
    ]


def test_data_gap_immediately_overrides_hysteresis() -> None:
    config = _config()
    rows = apply_state_machine(
        ["EXPANSION", "EXPANSION", "EXPANSION", "MIXED"],
        ["RULE", "RULE", "RULE", "DATA_GAP"],
        [1.0, 1.0, 1.0, np.nan],
        [1.0, 1.0, 1.0, np.nan],
        config,
    )
    assert rows[-2]["state"] == "EXPANSION"
    assert rows[-1]["state"] == "MIXED"
    assert rows[-1]["state_reason"] == "DATA_GAP"


def test_future_mutation_cannot_change_past_states() -> None:
    config = _config()
    panel = _panel()
    baseline = build_cycle_states(panel, config).monthly
    mutated = panel.copy()
    mutated.loc[mutated.index[-6:], "spread"] *= 10
    changed = build_cycle_states(mutated, config).monthly
    pd.testing.assert_frame_equal(
        baseline.iloc[:-6].reset_index(drop=True),
        changed.iloc[:-6].reset_index(drop=True),
    )


def test_confirmation_overlay_does_not_change_economic_state() -> None:
    config = _config()
    panel = _panel()
    baseline = build_cycle_states(panel, config).monthly
    reversed_confirmation = panel.copy()
    reversed_confirmation["margin_change"] *= -1
    reversed_confirmation["momentum_6m"] *= -1
    changed = build_cycle_states(reversed_confirmation, config).monthly
    pd.testing.assert_series_equal(baseline["state"], changed["state"])
    assert not baseline["confirmation_overlay"].equals(
        changed["confirmation_overlay"]
    )


def test_unavailable_core_signal_is_mixed_and_reported_as_data_gap() -> None:
    config = _config()
    panel = _panel()
    panel.loc[panel.index[-1], "spread"] = np.nan
    result = build_cycle_states(panel, config).monthly.iloc[-1]
    assert result["state"] == "MIXED"
    assert result["raw_state_reason"] == "DATA_GAP"
    assert not result["core_signal_available"]


def test_point_in_time_violation_is_detected() -> None:
    config = _config()
    panel = _panel(24)
    panel.loc[3, "urea_time"] = panel.loc[3, "panel_available_time"] + pd.Timedelta(
        days=1
    )
    assert point_in_time_violations(panel, config) == 1


def test_build_is_deterministic_and_months_are_unique() -> None:
    config = deepcopy(_config())
    panel = _panel()
    first = build_cycle_states(panel, config)
    second = build_cycle_states(panel, config)
    pd.testing.assert_frame_equal(first.monthly, second.monthly)
    pd.testing.assert_frame_equal(first.episodes, second.episodes)
    assert first.monthly["month_end"].is_unique
