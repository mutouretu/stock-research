"""Expanding-window CF operating bridge for comparable future experiments."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OperatingBridgeResult:
    """Long-form predictions, aggregate metrics and final fitted parameters."""

    predictions: pd.DataFrame
    metrics: pd.DataFrame
    final_parameters: dict


def run_operating_bridge_experiment(
    quarterly_panel: pd.DataFrame,
    quarterly_nitrogen: pd.DataFrame,
    config: dict,
) -> OperatingBridgeResult:
    """Run a leakage-safe expanding-window operating bridge.

    Each prediction is made a configured number of days after quarter end. Only
    company targets disclosed by that timestamp may enter the training sample.
    """
    frame = _prepare_frame(quarterly_panel, quarterly_nitrogen, config)
    products = list(config["products"])
    volume_products = list(config["volume_products"])
    lag_days = int(config["evaluation"]["prediction_lag_days_after_period_end"])
    minimum_train = int(config["evaluation"]["minimum_training_quarters"])
    records: list[dict] = []

    for row_index, row in frame.iterrows():
        prediction_time = pd.Timestamp(row["period_end"]) + pd.Timedelta(days=lag_days)
        train = frame[
            (frame["period_end"] < row["period_end"])
            & (frame["panel_available_time"] <= prediction_time)
        ].copy()
        if len(train) < minimum_train:
            continue
        if pd.Timestamp(row["panel_available_time"]) <= prediction_time:
            raise ValueError(
                f"Target for {row['period_end']} was already public at prediction time"
            )
        _assert_market_data_available(row, prediction_time, config)
        common = {
            "experiment_id": config["experiment_id"],
            "baseline_id": "theoretical_operating_bridge",
            "period_end": pd.Timestamp(row["period_end"]),
            "prediction_time": prediction_time,
            "target_available_time": pd.Timestamp(row["panel_available_time"]),
            "train_rows": len(train),
            "train_start_period": pd.Timestamp(train["period_end"].min()),
            "train_end_period": pd.Timestamp(train["period_end"].max()),
            "train_last_available_time": pd.Timestamp(train["panel_available_time"].max()),
        }

        gas_prediction, gas_parameters = _ols_prediction(
            train["cf_realized_natural_gas_cost"],
            train["__henry_distributed_lag"],
            row["__henry_distributed_lag"],
        )
        _append_record(
            records,
            common,
            task_group="gas_cost",
            target="cf_realized_natural_gas_cost",
            product="all_products",
            actual=row["cf_realized_natural_gas_cost"],
            prediction=gas_prediction,
            naive=_last_value(train["cf_realized_natural_gas_cost"]),
            unit="USD_per_MMBtu",
            parameters=gas_parameters,
        )

        price_predictions: dict[str, float] = {}
        margin_predictions: dict[str, float] = {}
        volume_predictions: dict[str, float] = {}
        for product in products:
            price_column = f"cf_{product}_realized_price"
            price_prediction, price_parameters = _ols_prediction(
                train[price_column], train["__global_urea_short_ton"], row["__global_urea_short_ton"]
            )
            price_predictions[product] = price_prediction
            _append_record(
                records,
                common,
                task_group="realized_price",
                target=price_column,
                product=product,
                actual=row[price_column],
                prediction=price_prediction,
                naive=_last_value(train[price_column]),
                unit="USD_per_short_ton",
                parameters=price_parameters,
            )

            residual_column = f"cf_{product}_other_cost_basis_residual"
            other_cost = float(train[residual_column].dropna().mean())
            intensity = float(config["products"][product]["gas_intensity_mmbtu_per_short_ton"])
            margin_prediction = price_prediction - intensity * gas_prediction - other_cost
            margin_predictions[product] = margin_prediction
            margin_column = f"cf_{product}_actual_gross_margin_per_ton"
            _append_record(
                records,
                common,
                task_group="unit_margin",
                target=margin_column,
                product=product,
                actual=row[margin_column],
                prediction=margin_prediction,
                naive=_last_value(train[margin_column]),
                unit="USD_per_short_ton",
                parameters={
                    "gas_intensity": intensity,
                    "other_cost_basis": other_cost,
                    "price_prediction": price_prediction,
                    "gas_prediction": gas_prediction,
                },
            )

        calendar_quarter = int(pd.Timestamp(row["period_end"]).quarter)
        seasonal_train = train[train["period_end"].dt.quarter == calendar_quarter]
        for product in volume_products:
            volume_column = f"cf_{product}_sales_volume"
            volume_prediction = float(seasonal_train[volume_column].dropna().mean())
            volume_predictions[product] = volume_prediction
            _append_record(
                records,
                common,
                task_group="sales_volume",
                target=volume_column,
                product=product,
                actual=row[volume_column],
                prediction=volume_prediction,
                naive=_last_value(train[volume_column]),
                unit="thousand_short_tons",
                parameters={
                    "calendar_quarter": calendar_quarter,
                    "seasonal_training_rows": int(seasonal_train[volume_column].notna().sum()),
                },
            )

        other_margin_column = "cf_other_gross_margin_per_ton"
        other_margin = float(seasonal_train[other_margin_column].dropna().mean())
        predicted_gross_profit = sum(
            margin_predictions[product] * volume_predictions[product] / 1_000.0
            for product in products
        )
        predicted_gross_profit += (
            other_margin * volume_predictions["other"] / 1_000.0
        )
        _append_record(
            records,
            common,
            task_group="gross_profit",
            target="cf_gross_profit_usd_million",
            product="all_products",
            actual=_as_float(row["cf_gross_profit"]) / 1_000_000.0,
            prediction=predicted_gross_profit,
            naive=_last_value(train["cf_gross_profit"]) / 1_000_000.0,
            unit="USD_million",
            parameters={
                "other_margin": other_margin,
                "component_count": len(products) + 1,
            },
        )

    predictions = pd.DataFrame.from_records(records)
    if predictions.empty:
        raise ValueError("No predictions produced; lower minimum_training_quarters or add data")
    predictions = predictions.sort_values(
        ["period_end", "task_group", "product", "target"]
    ).reset_index(drop=True)
    metrics = summarize_predictions(predictions)
    final_parameters = _fit_final_parameters(frame, config)
    return OperatingBridgeResult(predictions, metrics, final_parameters)


def summarize_predictions(predictions: pd.DataFrame) -> pd.DataFrame:
    """Summarize a long prediction table using metrics reusable by later models."""
    required = {
        "task_group",
        "target",
        "product",
        "actual",
        "prediction",
        "naive_prediction",
    }
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError(f"Prediction table missing columns: {sorted(missing)}")
    rows: list[dict] = []
    for keys, group in predictions.groupby(["task_group", "target", "product"], sort=True):
        clean = group.dropna(subset=["actual", "prediction", "naive_prediction"]).copy()
        if clean.empty:
            continue
        error = clean["prediction"] - clean["actual"]
        naive_error = clean["naive_prediction"] - clean["actual"]
        baseline_mae = float(error.abs().mean())
        naive_mae = float(naive_error.abs().mean())
        actual_change = clean["actual"] - clean["naive_prediction"]
        predicted_change = clean["prediction"] - clean["naive_prediction"]
        nonzero = actual_change != 0
        direction_accuracy = (
            float(
                (np.sign(actual_change[nonzero]) == np.sign(predicted_change[nonzero])).mean()
            )
            if nonzero.any()
            else float("nan")
        )
        rows.append(
            {
                "task_group": keys[0],
                "target": keys[1],
                "product": keys[2],
                "observations": len(clean),
                "mae": baseline_mae,
                "rmse": float(np.sqrt(np.mean(np.square(error)))),
                "bias": float(error.mean()),
                "wape": _safe_ratio(float(error.abs().sum()), float(clean["actual"].abs().sum())),
                "direction_accuracy": direction_accuracy,
                "naive_mae": naive_mae,
                "improvement_vs_naive": 1.0 - _safe_ratio(baseline_mae, naive_mae),
            }
        )
    return pd.DataFrame(rows).sort_values(["task_group", "product"]).reset_index(drop=True)


def compare_candidate_predictions(
    baseline_predictions: pd.DataFrame,
    candidate_predictions: pd.DataFrame,
    *,
    candidate_id: str,
) -> pd.DataFrame:
    """Compare a later method against the locked operating-bridge rows.

    A candidate may cover a subset of targets, but it must provide every period
    present in the baseline for each selected target. This prevents a method from
    improving its score by silently omitting difficult quarters.
    """
    keys = ["period_end", "task_group", "target", "product"]
    metadata = [
        "prediction_time",
        "train_start_period",
        "train_end_period",
        "train_rows",
        "train_last_available_time",
    ]
    required = set(keys + metadata) | {"prediction"}
    missing = required - set(candidate_predictions.columns)
    if missing:
        raise ValueError(f"Candidate prediction table missing columns: {sorted(missing)}")
    if candidate_predictions.duplicated(keys).any():
        raise ValueError("Candidate prediction table contains duplicate experiment keys")
    target_keys = candidate_predictions[["task_group", "target", "product"]].drop_duplicates()
    expected = baseline_predictions.merge(
        target_keys, on=["task_group", "target", "product"], how="inner"
    ).dropna(subset=["actual", "prediction"])
    expected_keys = set(map(tuple, expected[keys].itertuples(index=False, name=None)))
    candidate_keys = set(
        map(tuple, candidate_predictions[keys].itertuples(index=False, name=None))
    )
    if expected_keys != candidate_keys:
        missing_rows = len(expected_keys - candidate_keys)
        extra_rows = len(candidate_keys - expected_keys)
        raise ValueError(
            f"Candidate coverage differs from baseline: missing={missing_rows}, extra={extra_rows}"
        )
    comparison = expected.merge(
        candidate_predictions[keys + metadata + ["prediction"]].rename(
            columns={
                "prediction": "candidate_prediction",
                **{column: f"candidate_{column}" for column in metadata},
            }
        ),
        on=keys,
        how="inner",
        validate="one_to_one",
    )
    for column in metadata:
        candidate_column = f"candidate_{column}"
        if column.endswith("_time") or column.endswith("_period"):
            matches = pd.to_datetime(comparison[column]) == pd.to_datetime(
                comparison[candidate_column]
            )
        else:
            matches = comparison[column] == comparison[candidate_column]
        if not bool(matches.all()):
            raise ValueError(f"Candidate experiment metadata differs from baseline: {column}")
    if bool(
        (
            pd.to_datetime(comparison["candidate_train_last_available_time"])
            > pd.to_datetime(comparison["candidate_prediction_time"])
        ).any()
    ):
        raise ValueError("Candidate training data extends beyond its prediction cutoff")
    evaluation = comparison[
        ["task_group", "target", "product", "actual", "candidate_prediction", "prediction"]
    ].rename(
        columns={
            "candidate_prediction": "prediction",
            "prediction": "naive_prediction",
        }
    )
    metrics = summarize_predictions(evaluation).rename(
        columns={
            "naive_mae": "operating_bridge_mae",
            "improvement_vs_naive": "improvement_vs_operating_bridge",
        }
    )
    metrics.insert(0, "candidate_id", candidate_id)
    return metrics


def _prepare_frame(
    quarterly_panel: pd.DataFrame, quarterly_nitrogen: pd.DataFrame, config: dict
) -> pd.DataFrame:
    frame = quarterly_panel.merge(
        quarterly_nitrogen,
        on=["instrument", "period_end", "panel_available_time"],
        how="left",
        suffixes=("", "_nitrogen"),
    ).sort_values("period_end").reset_index(drop=True)
    frame["period_end"] = pd.to_datetime(frame["period_end"])
    frame["panel_available_time"] = pd.to_datetime(frame["panel_available_time"])
    urea = config["market_features"]["global_urea"]
    frame["__global_urea_short_ton"] = (
        frame[urea["value_column"]] * float(urea["conversion_to_usd_per_short_ton"])
    )
    henry = config["market_features"]["henry_hub"]
    current_weight = float(henry["current_quarter_weight"])
    previous_weight = float(henry["previous_quarter_weight"])
    frame["__henry_distributed_lag"] = (
        current_weight * frame[henry["value_column"]]
        + previous_weight * frame[henry["value_column"]].shift(1)
    )
    return frame


def _assert_market_data_available(row: pd.Series, prediction_time: pd.Timestamp, config: dict) -> None:
    for name in ("global_urea", "henry_hub"):
        column = config["market_features"][name]["available_time_column"]
        available = pd.Timestamp(row[column]) if pd.notna(row[column]) else pd.NaT
        if pd.notna(available) and available > prediction_time:
            raise ValueError(
                f"{name} for {row['period_end']} was available {available}, "
                f"after prediction cutoff {prediction_time}"
            )


def _ols_prediction(y: pd.Series, x: pd.Series, new_x) -> tuple[float, dict]:
    data = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if len(data) < 3 or pd.isna(new_x) or data["x"].nunique() < 2:
        return float("nan"), {"intercept": float("nan"), "slope": float("nan"), "rows": len(data)}
    design = np.column_stack([np.ones(len(data)), data["x"].to_numpy(dtype=float)])
    intercept, slope = np.linalg.lstsq(design, data["y"].to_numpy(dtype=float), rcond=None)[0]
    prediction = float(intercept + slope * float(new_x))
    return prediction, {"intercept": float(intercept), "slope": float(slope), "rows": len(data)}


def _append_record(
    records: list[dict],
    common: dict,
    *,
    task_group: str,
    target: str,
    product: str,
    actual,
    prediction,
    naive,
    unit: str,
    parameters: dict,
) -> None:
    records.append(
        {
            **common,
            "task_group": task_group,
            "target": target,
            "product": product,
            "actual": _as_float(actual),
            "prediction": _as_float(prediction),
            "naive_prediction": _as_float(naive),
            "unit": unit,
            "parameters": _parameter_string(parameters),
        }
    )


def _fit_final_parameters(frame: pd.DataFrame, config: dict) -> dict:
    parameters: dict[str, dict] = {"realized_price": {}, "unit_margin": {}}
    gas_prediction, gas = _ols_prediction(
        frame["cf_realized_natural_gas_cost"],
        frame["__henry_distributed_lag"],
        frame["__henry_distributed_lag"].dropna().iloc[-1],
    )
    gas["last_fitted_prediction"] = gas_prediction
    parameters["realized_gas_cost"] = gas
    for product, product_config in config["products"].items():
        _, price = _ols_prediction(
            frame[f"cf_{product}_realized_price"],
            frame["__global_urea_short_ton"],
            frame["__global_urea_short_ton"].dropna().iloc[-1],
        )
        parameters["realized_price"][product] = price
        residual = frame[f"cf_{product}_other_cost_basis_residual"].dropna()
        parameters["unit_margin"][product] = {
            "gas_intensity": float(product_config["gas_intensity_mmbtu_per_short_ton"]),
            "other_cost_basis_mean": float(residual.mean()),
            "other_cost_basis_median": float(residual.median()),
        }
    return parameters


def _last_value(values: pd.Series) -> float:
    clean = values.dropna()
    return float(clean.iloc[-1]) if not clean.empty else float("nan")


def _as_float(value) -> float:
    return float(value) if pd.notna(value) else float("nan")


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else float("nan")


def _parameter_string(parameters: dict) -> str:
    return ";".join(f"{key}={value:.12g}" for key, value in sorted(parameters.items()))
