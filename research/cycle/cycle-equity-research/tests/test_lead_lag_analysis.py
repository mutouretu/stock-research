from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from cycle_equity_research.analysis.lead_lag import run_lead_lag_analysis


def _config(relationship: dict, *, minimum: int = 24) -> dict:
    return {
        "analysis_id": "synthetic_lead_lag",
        "analysis_end_date": "2030-12-31",
        "inference": {
            "alpha": 0.05,
            "stability_min_absolute_correlation": 0.10,
            "minimum_observations": {"monthly": minimum, "quarterly": minimum},
            "hac_max_lag": {"monthly": 3, "quarterly": 2},
        },
        "relationships": [relationship],
    }


def _monthly_relationship() -> dict:
    return {
        "id": "signal_to_target",
        "family": "synthetic",
        "frame": "monthly",
        "clock": "availability_time",
        "frequency": "monthly",
        "signal": "signal",
        "target": "target",
        "signal_transform": {"method": "level", "periods": 1},
        "target_transform": {"method": "level", "periods": 1},
        "signal_available_time_columns": ["signal_available_time"],
        "lead_periods": [0, 1, 2, 3, 4],
        "expected_sign": "positive",
    }


def test_positive_lead_means_signal_precedes_target() -> None:
    generator = np.random.default_rng(42)
    dates = pd.date_range("2010-01-31", periods=120, freq="ME")
    signal = generator.normal(size=len(dates))
    target = np.full(len(dates), np.nan)
    target[2:] = signal[:-2] + generator.normal(scale=0.03, size=len(dates) - 2)
    frame = pd.DataFrame(
        {
            "month_end": dates,
            "signal": signal,
            "target": target,
            "signal_available_time": dates,
        }
    )

    result = run_lead_lag_analysis(
        {"monthly": frame}, _config(_monthly_relationship())
    )

    best = result.best_lags.iloc[0]
    assert best["lead_periods"] == 2
    assert best["correlation"] > 0.99
    assert best["evidence_status"] == "STRONG"


def test_availability_clock_rejects_future_signal_timestamp() -> None:
    dates = pd.date_range("2020-01-31", periods=48, freq="ME")
    frame = pd.DataFrame(
        {
            "month_end": dates,
            "signal": np.arange(len(dates), dtype=float),
            "target": np.arange(len(dates), dtype=float),
            "signal_available_time": dates,
        }
    )
    frame.loc[20, "signal_available_time"] = frame.loc[20, "month_end"] + pd.Timedelta(
        days=1
    )

    with pytest.raises(ValueError, match="availability violations"):
        run_lead_lag_analysis(
            {"monthly": frame}, _config(_monthly_relationship())
        )


def test_availability_clock_requires_timestamp_columns() -> None:
    dates = pd.date_range("2020-01-31", periods=48, freq="ME")
    frame = pd.DataFrame(
        {
            "month_end": dates,
            "signal": np.arange(len(dates), dtype=float),
            "target": np.arange(len(dates), dtype=float),
        }
    )
    relationship = _monthly_relationship()
    relationship.pop("signal_available_time_columns")

    with pytest.raises(ValueError, match="requires signal timestamps"):
        run_lead_lag_analysis({"monthly": frame}, _config(relationship))


def test_event_filter_does_not_change_monthly_lag_unit() -> None:
    dates = pd.date_range("2020-01-31", periods=30, freq="ME")
    event_indexes = np.arange(2, 27, 3)
    signal = np.zeros(len(dates), dtype=float)
    event_period = pd.Series(pd.NaT, index=range(len(dates)), dtype="datetime64[ns]")
    target = np.zeros(len(dates), dtype=float)
    for event_number, index in enumerate(event_indexes, start=1):
        signal[index:] = float(event_number)
        event_period.iloc[index:] = dates[index]
        target[index + 1] = float(event_number)
    frame = pd.DataFrame(
        {
            "month_end": dates,
            "signal": signal,
            "target": target,
            "event_period": event_period,
            "signal_available_time": dates,
        }
    )
    relationship = _monthly_relationship()
    relationship["event_only_column"] = "event_period"
    relationship["lead_periods"] = [1]

    result = run_lead_lag_analysis(
        {"monthly": frame}, _config(relationship, minimum=6)
    )

    best = result.best_lags.iloc[0]
    assert best["lead_periods"] == 1
    assert best["observations"] == len(event_indexes)
    assert best["correlation"] == pytest.approx(1.0)


def test_weak_half_sample_cannot_be_labeled_strong() -> None:
    generator = np.random.default_rng(7)
    dates = pd.date_range("2010-01-31", periods=120, freq="ME")
    signal = generator.normal(size=len(dates))
    target = np.concatenate(
        [generator.normal(size=60), signal[60:] + generator.normal(scale=0.05, size=60)]
    )
    frame = pd.DataFrame(
        {
            "month_end": dates,
            "signal": signal,
            "target": target,
            "signal_available_time": dates,
        }
    )
    relationship = deepcopy(_monthly_relationship())
    relationship["lead_periods"] = [0]

    result = run_lead_lag_analysis(
        {"monthly": frame}, _config(relationship)
    )

    best = result.best_lags.iloc[0]
    assert best["adjusted_significant"]
    assert best["stability_status"] == "UNSTABLE"
    assert best["evidence_status"] == "UNSTABLE"


def test_formula_identity_is_labeled_diagnostic() -> None:
    generator = np.random.default_rng(11)
    dates = pd.date_range("2010-01-31", periods=80, freq="ME")
    signal = generator.normal(size=len(dates))
    frame = pd.DataFrame(
        {
            "month_end": dates,
            "signal": signal,
            "target": -signal,
            "signal_available_time": dates,
        }
    )
    relationship = _monthly_relationship()
    relationship["lead_periods"] = [0]
    relationship["expected_sign"] = "negative"
    relationship["relationship_role"] = "diagnostic_identity"

    result = run_lead_lag_analysis(
        {"monthly": frame}, _config(relationship)
    )

    assert result.best_lags.iloc[0]["evidence_status"] == "DIAGNOSTIC"
