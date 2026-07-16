from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from cycle_equity_research.analysis.stability import run_stability_analysis


RELATIONSHIP_ID = "synthetic_fixed_lag"


def _frames() -> dict[str, pd.DataFrame]:
    generator = np.random.default_rng(123)
    dates = pd.date_range("2010-01-31", periods=120, freq="ME")
    signal = generator.normal(size=len(dates))
    target = np.full(len(dates), np.nan)
    target[2:] = signal[:-2]
    return {
        "monthly": pd.DataFrame(
            {
                "month_end": dates,
                "signal": signal,
                "target": target,
                "signal_available_time": dates,
                "henry_hub_month_mean": np.tile([2.0, 5.0], len(dates) // 2),
                "global_urea_gas_spread_month_mean": generator.normal(
                    size=len(dates)
                ).cumsum(),
            }
        )
    }


def _lead_lag_config() -> dict:
    return {
        "relationships": [
            {
                "id": RELATIONSHIP_ID,
                "family": "synthetic",
                "frame": "monthly",
                "clock": "availability_time",
                "frequency": "monthly",
                "signal": "signal",
                "target": "target",
                "signal_transform": {"method": "level", "periods": 1},
                "target_transform": {"method": "level", "periods": 1},
                "signal_available_time_columns": ["signal_available_time"],
                "lead_periods": [0, 1, 2, 3],
                "expected_sign": "positive",
            }
        ]
    }


def _best_lags(evidence: str = "STRONG") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "relationship_id": RELATIONSHIP_ID,
                "lead_periods": 2,
                "correlation": 1.0,
                "evidence_status": evidence,
            }
        ]
    )


def _config() -> dict:
    return {
        "analysis_id": "synthetic_stability",
        "analysis_end_date": "2030-12-31",
        "rolling": {
            "window_observations": {
                "monthly": 20,
                "quarterly": 12,
                "event_only": 12,
            },
            "minimum_windows": 8,
        },
        "slices": {
            "minimum_observations": {
                "monthly": 8,
                "quarterly": 6,
                "event_only": 6,
            },
            "gas_regime_quantile": 0.50,
            "stress_regime_quantile": 0.75,
            "monthly_seasons": {
                "spring_application": [3, 4, 5, 6],
                "fall_application": [9, 10, 11],
                "off_season": [1, 2, 7, 8, 12],
            },
            "quarterly_seasons": {
                "spring_half": [1, 2],
                "fall_and_other_half": [3, 4],
            },
        },
        "decision_thresholds": {
            "minimum_expected_sign_window_share": 0.75,
            "minimum_median_absolute_correlation": 0.20,
            "minimum_regime_expected_sign_share": 0.75,
            "minimum_regime_absolute_correlation": 0.10,
        },
        "candidate_roles": {"cycle_core_validation": [RELATIONSHIP_ID]},
    }


def test_stability_keeps_m4_1_lag_fixed_in_every_window() -> None:
    result = run_stability_analysis(
        _frames(), _lead_lag_config(), _best_lags(), _config()
    )

    assert set(result.rolling_windows["fixed_lead_periods"]) == {2}
    assert len(result.rolling_windows) == 99
    assert np.allclose(result.rolling_windows["correlation"], 1.0)
    decision = result.decisions.iloc[0]
    assert decision["rolling_expected_sign_share"] == 1.0
    assert decision["gas_regime_expected_sign_share"] == 1.0
    assert decision["stress_regime_expected_sign_share"] == 1.0
    assert decision["decision"] == "ACCEPT_CORE_VALIDATION"


def test_stability_rejects_drift_from_locked_m4_1_sample() -> None:
    best = _best_lags()
    best.loc[0, "correlation"] = 0.5

    with pytest.raises(ValueError, match="no longer matches M4.1"):
        run_stability_analysis(
            _frames(), _lead_lag_config(), best, _config()
        )


def test_unsorted_input_produces_the_same_stability_results() -> None:
    ordered = run_stability_analysis(
        _frames(), _lead_lag_config(), _best_lags(), _config()
    )
    shuffled_frames = _frames()
    shuffled_frames["monthly"] = shuffled_frames["monthly"].sample(
        frac=1.0, random_state=99
    )

    shuffled = run_stability_analysis(
        shuffled_frames, _lead_lag_config(), _best_lags(), _config()
    )

    pd.testing.assert_frame_equal(ordered.rolling_windows, shuffled.rolling_windows)
    pd.testing.assert_frame_equal(ordered.slices, shuffled.slices)
    pd.testing.assert_frame_equal(ordered.decisions, shuffled.decisions)


def test_m4_1_unstable_relationship_remains_rejected() -> None:
    result = run_stability_analysis(
        _frames(), _lead_lag_config(), _best_lags("UNSTABLE"), _config()
    )

    decision = result.decisions.iloc[0]
    assert decision["rolling_pass"]
    assert decision["regime_pass"]
    assert decision["decision"] == "REJECT"
    assert "M4.1 evidence is UNSTABLE" in decision["decision_reason"]


def test_weak_regime_makes_a_strong_relationship_conditional() -> None:
    config = _config()
    config["decision_thresholds"]["minimum_regime_absolute_correlation"] = 1.1

    result = run_stability_analysis(
        _frames(), _lead_lag_config(), _best_lags(), config
    )

    decision = result.decisions.iloc[0]
    assert decision["rolling_pass"]
    assert not decision["regime_pass"]
    assert decision["decision"] == "CONDITIONAL"


def test_every_relationship_requires_exactly_one_candidate_role() -> None:
    config = deepcopy(_config())
    config["candidate_roles"] = {}

    with pytest.raises(ValueError, match="coverage differs"):
        run_stability_analysis(
            _frames(), _lead_lag_config(), _best_lags(), config
        )
