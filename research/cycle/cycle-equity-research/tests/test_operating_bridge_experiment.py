from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest
import yaml

from cycle_equity_research.experiments.operating_bridge import (
    compare_candidate_predictions,
    run_operating_bridge_experiment,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs/experiments/cf_operating_bridge_v1.yaml"


def _config() -> dict:
    config = yaml.safe_load(CONFIG_PATH.read_text())
    config["evaluation"]["minimum_training_quarters"] = 4
    return config


def _frames(periods: int = 12) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2015-03-31", periods=periods, freq="QE")
    quarterly_rows = []
    nitrogen_rows = []
    previous_henry = None
    products = {
        "ammonia": (50.0, 1.1, 28.0, 200.0, 800.0),
        "granular_urea": (80.0, 0.9, 19.0, 140.0, 1_100.0),
        "uan": (40.0, 0.7, 13.0, 115.0, 1_600.0),
        "ammonium_nitrate": (90.0, 0.6, 14.0, 185.0, 450.0),
    }
    for index, period_end in enumerate(dates):
        urea_metric = 250.0 + index * 8.0
        urea_short = urea_metric * 0.90718474
        henry = 2.5 + index * 0.08
        lagged_henry = henry if previous_henry is None else (henry + previous_henry) / 2.0
        gas = -0.2 + 1.1 * lagged_henry
        quarter = period_end.quarter
        quarterly_row = {
            "instrument": "CF",
            "period_end": period_end,
            "panel_available_time": period_end + pd.Timedelta(days=35),
            "world_bank_urea_quarter_mean": urea_metric,
            "world_bank_urea_quarter_mean__available_time": period_end
            + pd.Timedelta(days=10),
            "henry_hub_quarter_mean": henry,
            "henry_hub_quarter_mean__available_time": period_end
            + pd.Timedelta(days=1),
            "cf_other_sales_volume": 500.0 + quarter * 5.0,
            "cf_other_gross_margin_per_ton": 25.0 + quarter,
        }
        nitrogen_row = {
            "instrument": "CF",
            "period_end": period_end,
            "panel_available_time": period_end + pd.Timedelta(days=35),
            "cf_realized_natural_gas_cost": gas,
        }
        gross_profit = quarterly_row["cf_other_sales_volume"] * quarterly_row[
            "cf_other_gross_margin_per_ton"
        ] / 1_000.0
        for product, (intercept, slope, intensity, residual, base_volume) in products.items():
            price = intercept + slope * urea_short
            margin = price - intensity * gas - residual
            volume = base_volume + quarter * 20.0 + index
            quarterly_row[f"cf_{product}_sales_volume"] = volume
            nitrogen_row[f"cf_{product}_realized_price"] = price
            nitrogen_row[f"cf_{product}_actual_gross_margin_per_ton"] = margin
            nitrogen_row[f"cf_{product}_other_cost_basis_residual"] = residual
            gross_profit += margin * volume / 1_000.0
        quarterly_row["cf_gross_profit"] = gross_profit * 1_000_000.0
        quarterly_rows.append(quarterly_row)
        nitrogen_rows.append(nitrogen_row)
        previous_henry = henry
    return pd.DataFrame(quarterly_rows), pd.DataFrame(nitrogen_rows)


def test_expanding_experiment_has_no_future_target_leakage() -> None:
    quarterly, nitrogen = _frames()
    result = run_operating_bridge_experiment(quarterly, nitrogen, _config())

    assert (result.predictions["train_last_available_time"] <= result.predictions["prediction_time"]).all()
    assert (result.predictions["prediction_time"] < result.predictions["target_available_time"]).all()
    assert result.predictions["period_end"].nunique() == 8


def test_future_actuals_do_not_change_an_earlier_prediction() -> None:
    quarterly, nitrogen = _frames()
    original = run_operating_bridge_experiment(quarterly, nitrogen, _config()).predictions
    first_period = original["period_end"].min()
    changed_quarterly = quarterly.copy()
    changed_nitrogen = nitrogen.copy()
    changed_quarterly.loc[
        changed_quarterly["period_end"] >= first_period, "cf_gross_profit"
    ] *= 100.0
    for column in changed_nitrogen.columns:
        if column.endswith("_realized_price") or column.endswith("_gross_margin_per_ton"):
            changed_nitrogen.loc[changed_nitrogen["period_end"] >= first_period, column] *= 100.0
    changed = run_operating_bridge_experiment(
        changed_quarterly, changed_nitrogen, _config()
    ).predictions
    keys = ["period_end", "task_group", "target", "product"]
    left = original[original["period_end"] == first_period].set_index(keys)["prediction"]
    right = changed[changed["period_end"] == first_period].set_index(keys)["prediction"]

    pd.testing.assert_series_equal(left, right)


def test_unit_margin_prediction_reconciles_to_operating_bridge_formula() -> None:
    quarterly, nitrogen = _frames()
    predictions = run_operating_bridge_experiment(quarterly, nitrogen, _config()).predictions
    period = predictions["period_end"].min()
    selected = predictions[predictions["period_end"] == period]
    gas = selected.loc[selected["task_group"] == "gas_cost", "prediction"].iloc[0]
    price = selected.loc[
        (selected["task_group"] == "realized_price")
        & (selected["product"] == "granular_urea"),
        "prediction",
    ].iloc[0]
    margin_row = selected.loc[
        (selected["task_group"] == "unit_margin")
        & (selected["product"] == "granular_urea")
    ].iloc[0]
    parameters = dict(item.split("=") for item in margin_row["parameters"].split(";"))

    expected = price - float(parameters["gas_intensity"]) * gas - float(
        parameters["other_cost_basis"]
    )
    assert margin_row["prediction"] == pytest.approx(expected)


def test_candidate_comparison_requires_locked_coverage() -> None:
    quarterly, nitrogen = _frames()
    baseline = run_operating_bridge_experiment(quarterly, nitrogen, _config()).predictions
    complete = baseline.dropna(subset=["actual", "prediction"])
    candidate = complete[
        [
            "period_end",
            "task_group",
            "target",
            "product",
            "prediction_time",
            "train_start_period",
            "train_end_period",
            "train_rows",
            "train_last_available_time",
        ]
    ].copy()
    candidate["prediction"] = complete["actual"].to_numpy()

    metrics = compare_candidate_predictions(
        baseline, candidate, candidate_id="perfect_candidate"
    )

    assert (metrics["mae"] == 0).all()
    comparable = metrics["improvement_vs_operating_bridge"].dropna()
    assert (comparable == 1).all()
    assert metrics["improvement_vs_operating_bridge"].isna().sum() == 1
    with pytest.raises(ValueError, match="coverage differs"):
        compare_candidate_predictions(
            baseline, candidate.iloc[:-1], candidate_id="cherry_picked"
        )
    wrong_cutoff = candidate.copy()
    wrong_cutoff["prediction_time"] += pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="metadata differs"):
        compare_candidate_predictions(
            baseline, wrong_cutoff, candidate_id="different_cutoff"
        )


def test_experiment_rejects_targets_public_before_prediction_cutoff() -> None:
    quarterly, nitrogen = _frames()
    config = deepcopy(_config())
    quarterly.loc[4, "panel_available_time"] = quarterly.loc[4, "period_end"] + pd.Timedelta(
        days=10
    )
    nitrogen.loc[4, "panel_available_time"] = quarterly.loc[4, "panel_available_time"]

    with pytest.raises(ValueError, match="already public"):
        run_operating_bridge_experiment(quarterly, nitrogen, config)
