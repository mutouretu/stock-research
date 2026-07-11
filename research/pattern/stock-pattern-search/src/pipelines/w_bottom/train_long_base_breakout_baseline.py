from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.paths import get_shared_us_daily_dir  # noqa: E402

DEFAULT_US_DAILY_DIR = get_shared_us_daily_dir()


META_COLUMNS = [
    "sample_id",
    "ts_code",
    "asof_date",
    "label",
    "label_source",
    "confidence",
    "pattern_type",
    "source_miner",
    "split",
]
SUPPORTED_MODELS = ["logistic_regression", "lightgbm", "xgboost"]


@dataclass(frozen=True)
class BuildResult:
    dataset: pd.DataFrame
    feature_columns: list[str]
    skipped_samples: int
    skip_examples: list[str]


def load_labels(labels_path: str | Path) -> pd.DataFrame:
    path = Path(labels_path)
    if not path.exists():
        raise FileNotFoundError(f"labels CSV not found: {path}")
    labels = pd.read_csv(path)
    required = {"sample_id", "ts_code", "asof_date", "label", "split"}
    missing = sorted(required - set(labels.columns))
    if missing:
        raise ValueError(f"labels CSV missing required columns: {missing}")
    out = labels.copy()
    out["ts_code"] = out["ts_code"].astype(str).str.upper().str.strip()
    out["asof_date"] = pd.to_datetime(out["asof_date"], errors="coerce")
    out["label"] = pd.to_numeric(out["label"], errors="coerce").astype("Int64")
    out["split"] = out["split"].astype(str).str.lower().str.strip()
    for col in META_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    out = out.dropna(subset=["ts_code", "asof_date", "label"])
    out = out[out["split"].isin(["train", "valid", "test"])].copy()
    if out.empty:
        raise ValueError(f"labels CSV has no usable rows: {path}")
    return out.reset_index(drop=True)


def load_daily_for_symbol(daily_dir: str | Path, ts_code: str) -> pd.DataFrame:
    path = Path(daily_dir) / f"{ts_code}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"daily parquet not found for {ts_code}: {path}")
    df = pd.read_parquet(path)
    required = {"trade_date", "open", "high", "low", "close"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"daily parquet missing columns for {ts_code}: {missing}")
    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce")
    for col in ["open", "high", "low", "close", "vol", "volume"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "vol" not in out.columns and "volume" in out.columns:
        out["vol"] = out["volume"]
    if "vol" not in out.columns:
        out["vol"] = 0.0
    out = out.dropna(subset=["trade_date", "open", "high", "low", "close"])
    out = out[out["close"] > 0].drop_duplicates("trade_date", keep="last")
    return out.sort_values("trade_date").reset_index(drop=True)


def build_tabular_dataset(
    labels: pd.DataFrame,
    *,
    daily_dir: str | Path,
    min_history: int = 252,
    max_window: int = 504,
) -> BuildResult:
    daily_cache: dict[str, pd.DataFrame] = {}
    records: list[dict[str, Any]] = []
    skipped = 0
    skip_examples: list[str] = []

    for row in labels.itertuples(index=False):
        sample_id = str(getattr(row, "sample_id"))
        ts_code = str(getattr(row, "ts_code")).upper()
        asof_date = pd.Timestamp(getattr(row, "asof_date"))
        try:
            if ts_code not in daily_cache:
                daily_cache[ts_code] = load_daily_for_symbol(daily_dir, ts_code)
            daily = daily_cache[ts_code]
            asof_idx = _nearest_not_later_idx(daily["trade_date"], asof_date)
            if asof_idx is None:
                raise ValueError(f"asof_date not covered by daily data: {asof_date.date()}")
            if asof_idx + 1 < min_history:
                raise ValueError(f"insufficient history: have={asof_idx + 1}, need={min_history}")
            start_idx = max(0, asof_idx - int(max_window) + 1)
            window = daily.iloc[start_idx : asof_idx + 1].copy().reset_index(drop=True)
            features = build_daily_features(window)
            meta = {col: getattr(row, col, pd.NA) for col in META_COLUMNS if hasattr(row, col)}
            meta["asof_date"] = asof_date.strftime("%Y-%m-%d")
            meta["label"] = int(getattr(row, "label"))
            records.append({**meta, **features})
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            if len(skip_examples) < 20:
                skip_examples.append(f"{sample_id}: {exc}")

    if not records:
        raise RuntimeError("No usable samples were built from labels and daily data")

    dataset = pd.DataFrame(records)
    feature_columns = [col for col in dataset.columns if col not in META_COLUMNS]
    return BuildResult(
        dataset=dataset,
        feature_columns=feature_columns,
        skipped_samples=skipped,
        skip_examples=skip_examples,
    )


def build_daily_features(window: pd.DataFrame) -> dict[str, float]:
    close = pd.to_numeric(window["close"], errors="coerce").astype(float)
    high = pd.to_numeric(window["high"], errors="coerce").astype(float)
    low = pd.to_numeric(window["low"], errors="coerce").astype(float)
    vol = pd.to_numeric(window["vol"], errors="coerce").fillna(0.0).astype(float)
    ret = close.pct_change()

    features: dict[str, float] = {
        "history_bars": float(len(window)),
        "current_close": _last(close),
    }
    for period in [5, 10, 20, 60, 120, 252]:
        features[f"ret_{period}d"] = _pct_change(close, period)
        features[f"volatility_{period}d"] = float(ret.tail(period).std(ddof=0)) if len(ret) >= period else np.nan
        features[f"range_{period}d_pct"] = _range_pct(high, low, period)
        features[f"close_pos_{period}d"] = _close_position(close, high, low, period)

    for period in [20, 60, 120, 200]:
        ma = close.rolling(period).mean()
        features[f"close_vs_ma{period}"] = _safe_div(_last(close), _last(ma)) - 1.0
        features[f"ma{period}_slope_20d"] = _pct_change(ma.dropna(), 20)

    features["ma20_vs_ma60"] = _safe_div(_last(close.rolling(20).mean()), _last(close.rolling(60).mean())) - 1.0
    features["ma60_vs_ma120"] = _safe_div(_last(close.rolling(60).mean()), _last(close.rolling(120).mean())) - 1.0
    features["drawdown_from_252d_high"] = _safe_div(_last(close), float(high.tail(252).max())) - 1.0
    features["drawdown_from_504d_high"] = _safe_div(_last(close), float(high.tail(504).max())) - 1.0
    features["distance_from_252d_low"] = _safe_div(_last(close), float(low.tail(252).min())) - 1.0
    features["distance_from_504d_low"] = _safe_div(_last(close), float(low.tail(504).min())) - 1.0
    features["max_drawdown_252d"] = _max_drawdown(close.tail(252))
    features["max_drawdown_504d"] = _max_drawdown(close.tail(504))
    features["volume_ratio_20_60"] = _safe_div(float(vol.tail(20).mean()), float(vol.tail(60).mean()))
    features["volume_ratio_20_120"] = _safe_div(float(vol.tail(20).mean()), float(vol.tail(120).mean()))
    features["volume_cv_120"] = _safe_div(float(vol.tail(120).std(ddof=0)), float(vol.tail(120).mean()))
    features["breakout_distance_60d"] = _safe_div(_last(close), float(high.iloc[:-1].tail(60).max())) - 1.0
    features["breakout_distance_120d"] = _safe_div(_last(close), float(high.iloc[:-1].tail(120).max())) - 1.0
    features["days_since_252d_high"] = _days_since_extreme(high.tail(252), mode="max")
    features["days_since_252d_low"] = _days_since_extreme(low.tail(252), mode="min")
    return {key: float(value) if pd.notna(value) else np.nan for key, value in features.items()}


def train_baseline_classifier(
    dataset: pd.DataFrame,
    feature_columns: list[str],
    *,
    output_dir: str | Path,
    threshold: float = 0.5,
    random_seed: int = 42,
) -> dict[str, Any]:
    return train_single_classifier(
        dataset,
        feature_columns,
        model_name="logistic_regression",
        output_dir=output_dir,
        threshold=threshold,
        random_seed=random_seed,
    )


def train_single_classifier(
    dataset: pd.DataFrame,
    feature_columns: list[str],
    *,
    model_name: str,
    output_dir: str | Path,
    threshold: float = 0.5,
    random_seed: int = 42,
) -> dict[str, Any]:
    normalized_model_name = normalize_model_name(model_name)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    train = dataset[dataset["split"].astype(str) == "train"].copy()
    valid = dataset[dataset["split"].astype(str) == "valid"].copy()
    test = dataset[dataset["split"].astype(str) == "test"].copy()
    if train.empty:
        raise ValueError("No train samples found")
    if valid.empty:
        raise ValueError("No valid samples found")

    X_train = train[feature_columns].apply(pd.to_numeric, errors="coerce")
    y_train = train["label"].astype(int).to_numpy()
    model = build_classifier_pipeline(normalized_model_name, y_train=y_train, random_seed=random_seed)
    model.fit(X_train, y_train)

    metrics: dict[str, Any] = {}
    predictions: dict[str, pd.DataFrame] = {}
    for split_name, split_df in [("train", train), ("valid", valid), ("test", test)]:
        if split_df.empty:
            continue
        X = split_df[feature_columns].apply(pd.to_numeric, errors="coerce")
        y = split_df["label"].astype(int).to_numpy()
        score = model.predict_proba(X)[:, 1]
        split_metrics = compute_metrics(y, score, threshold=threshold)
        metrics[split_name] = split_metrics
        pred = split_df[META_COLUMNS].copy()
        pred["score"] = score
        pred["pred_label"] = (score >= threshold).astype(int)
        predictions[split_name] = pred
        pred.to_csv(out_dir / f"{split_name}_predictions.csv", index=False)

    joblib.dump(model, out_dir / "model.joblib")
    (out_dir / "feature_columns.json").write_text(json.dumps(feature_columns, indent=2), encoding="utf-8")
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return {
        "model_name": normalized_model_name,
        "model_dir": str(out_dir),
        "metrics": metrics,
        "predictions": predictions,
    }


def train_classifiers(
    dataset: pd.DataFrame,
    feature_columns: list[str],
    *,
    model_names: list[str],
    output_dir: str | Path,
    threshold: float = 0.5,
    random_seed: int = 42,
) -> dict[str, Any]:
    normalized_names = [normalize_model_name(name) for name in model_names]
    if len(set(normalized_names)) != len(normalized_names):
        raise ValueError(f"Duplicate model names after normalization: {model_names}")

    out_dir = Path(output_dir)
    results: dict[str, Any] = {}
    for model_name in normalized_names:
        model_dir = out_dir if len(normalized_names) == 1 else out_dir / "models" / model_name
        results[model_name] = train_single_classifier(
            dataset,
            feature_columns,
            model_name=model_name,
            output_dir=model_dir,
            threshold=threshold,
            random_seed=random_seed,
        )

    model_metrics = {model_name: result["metrics"] for model_name, result in results.items()}
    (out_dir / "model_metrics.json").write_text(json.dumps(model_metrics, indent=2), encoding="utf-8")
    return {"models": results, "metrics": model_metrics}


def normalize_model_name(model_name: str) -> str:
    name = model_name.strip().lower().replace("-", "_")
    aliases = {
        "lr": "logistic_regression",
        "logistic": "logistic_regression",
        "lgbm": "lightgbm",
        "xgb": "xgboost",
    }
    normalized = aliases.get(name, name)
    if normalized not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported model '{model_name}'. Choose from: {SUPPORTED_MODELS}")
    return normalized


def build_classifier_pipeline(model_name: str, *, y_train: np.ndarray, random_seed: int) -> Pipeline:
    if model_name == "logistic_regression":
        classifier = LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            random_state=int(random_seed),
        )
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("classifier", classifier),
            ]
        )

    if model_name == "lightgbm":
        from lightgbm import LGBMClassifier

        classifier = LGBMClassifier(
            n_estimators=300,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.9,
            colsample_bytree=0.9,
            min_child_samples=10,
            class_weight="balanced",
            random_state=int(random_seed),
            n_jobs=-1,
            verbosity=-1,
        )
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("classifier", classifier),
            ]
        )

    if model_name == "xgboost":
        from xgboost import XGBClassifier

        positives = float(np.sum(y_train == 1))
        negatives = float(np.sum(y_train == 0))
        scale_pos_weight = negatives / positives if positives > 0 else 1.0
        classifier = XGBClassifier(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=4,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="binary:logistic",
            eval_metric="logloss",
            scale_pos_weight=scale_pos_weight,
            random_state=int(random_seed),
            n_jobs=-1,
        )
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("classifier", classifier),
            ]
        )

    raise ValueError(f"Unsupported model: {model_name}")


def run_pipeline(
    *,
    labels_path: str | Path = "../market_pattern_labeler/outputs/labels_long_base_breakout.csv",
    daily_dir: str | Path = DEFAULT_US_DAILY_DIR,
    output_dir: str | Path = "outputs/models/w_bottom/long_base_breakout_baseline",
    min_history: int = 252,
    max_window: int = 504,
    threshold: float = 0.5,
    random_seed: int = 42,
    require_temporal_split: bool = True,
    models: list[str] | None = None,
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = load_labels(labels_path)
    build_result = build_tabular_dataset(
        labels,
        daily_dir=daily_dir,
        min_history=min_history,
        max_window=max_window,
    )
    dataset = build_result.dataset
    feature_columns = build_result.feature_columns
    temporal_split = describe_temporal_split(dataset)
    if require_temporal_split:
        validate_temporal_split(temporal_split)

    dataset.to_parquet(out_dir / "dataset.parquet", index=False)
    dataset[META_COLUMNS].to_parquet(out_dir / "sample_meta.parquet", index=False)
    dataset[["sample_id", *feature_columns]].to_parquet(out_dir / "X_tabular.parquet", index=False)

    model_names = models or ["logistic_regression"]
    train_result = train_classifiers(
        dataset,
        feature_columns,
        model_names=model_names,
        output_dir=out_dir,
        threshold=threshold,
        random_seed=random_seed,
    )
    ensemble_summary = build_lgbm_xgboost_ensemble(train_result, out_dir, threshold=threshold)
    report = build_report(
        labels_path=Path(labels_path),
        daily_dir=Path(daily_dir),
        output_dir=out_dir,
        dataset=dataset,
        feature_columns=feature_columns,
        temporal_split=temporal_split,
        skipped_samples=build_result.skipped_samples,
        skip_examples=build_result.skip_examples,
        model_metrics=train_result["metrics"],
        ensemble_summary=ensemble_summary,
    )
    report_path = out_dir / "evaluation_report.md"
    report_path.write_text(report, encoding="utf-8")

    summary = {
        "labels_path": str(labels_path),
        "daily_dir": str(daily_dir),
        "output_dir": str(out_dir),
        "samples": int(len(dataset)),
        "features": int(len(feature_columns)),
        "skipped_samples": int(build_result.skipped_samples),
        "temporal_split": temporal_split,
        "metrics": train_result["metrics"],
        "models": {
            model_name: {
                "model_dir": result["model_dir"],
                "metrics_path": str(Path(result["model_dir"]) / "metrics.json"),
            }
            for model_name, result in train_result["models"].items()
        },
        "ensemble": ensemble_summary,
        "report_path": str(report_path),
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def build_lgbm_xgboost_ensemble(
    train_result: dict[str, Any],
    output_dir: str | Path,
    *,
    threshold: float = 0.5,
    latest_top_n: int = 100,
) -> dict[str, Any] | None:
    model_results = train_result.get("models", {})
    if "lightgbm" not in model_results or "xgboost" not in model_results:
        return None

    out_dir = Path(output_dir)
    frames: list[pd.DataFrame] = []
    for split_name in ["train", "valid", "test"]:
        lgbm_pred = model_results["lightgbm"]["predictions"].get(split_name)
        xgb_pred = model_results["xgboost"]["predictions"].get(split_name)
        if lgbm_pred is None or xgb_pred is None:
            continue

        lgbm_cols = [*META_COLUMNS, "score", "pred_label"]
        xgb_cols = [*META_COLUMNS, "score", "pred_label"]
        merged = lgbm_pred[lgbm_cols].merge(
            xgb_pred[xgb_cols],
            on=META_COLUMNS,
            how="inner",
            suffixes=("_lgbm", "_xgb"),
        )
        merged = merged.rename(
            columns={
                "score_lgbm": "lgbm_score",
                "pred_label_lgbm": "lgbm_pred_label",
                "score_xgb": "xgb_score",
                "pred_label_xgb": "xgb_pred_label",
            }
        )
        frames.append(merged)

    if not frames:
        return None

    ensemble = pd.concat(frames, ignore_index=True)
    ensemble["asof_date"] = pd.to_datetime(ensemble["asof_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    ensemble["ensemble_score"] = ensemble[["lgbm_score", "xgb_score"]].mean(axis=1)
    ensemble["score_gap"] = (ensemble["lgbm_score"] - ensemble["xgb_score"]).abs()
    ensemble["ensemble_pred_label"] = (ensemble["ensemble_score"] >= threshold).astype(int)
    ensemble["model_agreement"] = (ensemble["lgbm_pred_label"] == ensemble["xgb_pred_label"]).astype(int)
    ensemble = ensemble.sort_values(["asof_date", "ensemble_score"], ascending=[False, False]).reset_index(drop=True)

    ensemble_path = out_dir / "ensemble_lgbm_xgboost_predictions.csv"
    ensemble.to_csv(ensemble_path, index=False)

    latest_date = str(ensemble["asof_date"].max())
    latest = ensemble[ensemble["asof_date"] == latest_date].sort_values("ensemble_score", ascending=False)
    latest_predictions_path = out_dir / "latest_ensemble_predictions.csv"
    latest.to_csv(latest_predictions_path, index=False)

    latest_candidates = latest[latest["ensemble_pred_label"] == 1].copy()
    latest_candidates = latest_candidates.head(latest_top_n)
    latest_candidates_path = out_dir / "latest_ensemble_candidates.csv"
    latest_candidates.to_csv(latest_candidates_path, index=False)

    split_summary = {
        split_name: {
            "samples": int(len(split_df)),
            "candidates": int(split_df["ensemble_pred_label"].sum()),
            "agreement_rate": float(split_df["model_agreement"].mean()) if len(split_df) else np.nan,
            "mean_score": float(split_df["ensemble_score"].mean()) if len(split_df) else np.nan,
        }
        for split_name, split_df in ensemble.groupby("split")
    }
    summary = {
        "ensemble_path": str(ensemble_path),
        "latest_predictions_path": str(latest_predictions_path),
        "latest_candidates_path": str(latest_candidates_path),
        "latest_date": latest_date,
        "latest_rows": int(len(latest)),
        "latest_candidates": int(len(latest_candidates)),
        "threshold": float(threshold),
        "split_summary": split_summary,
    }
    report_path = out_dir / "ensemble_lgbm_xgboost_report.md"
    report_path.write_text(build_ensemble_report(summary, latest_candidates), encoding="utf-8")
    summary["report_path"] = str(report_path)
    return summary


def compute_metrics(y_true: np.ndarray, y_score: np.ndarray, threshold: float = 0.5) -> dict[str, Any]:
    y_pred = (np.asarray(y_score) >= threshold).astype(int)
    y_true = np.asarray(y_true).astype(int)
    out: dict[str, Any] = {
        "samples": int(len(y_true)),
        "positive_rate": float(np.mean(y_true)) if len(y_true) else np.nan,
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": np.nan,
        "pr_auc": np.nan,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
    }
    if len(np.unique(y_true)) >= 2:
        out["roc_auc"] = float(roc_auc_score(y_true, y_score))
        out["pr_auc"] = float(average_precision_score(y_true, y_score))
    return out


def describe_temporal_split(dataset: pd.DataFrame) -> dict[str, dict[str, Any]]:
    split_order = ["train", "valid", "test"]
    dates = pd.to_datetime(dataset["asof_date"], errors="coerce")
    df = dataset.assign(_asof_date=dates)
    summary: dict[str, dict[str, Any]] = {}
    for split_name in split_order:
        split_df = df[df["split"].astype(str) == split_name]
        if split_df.empty:
            summary[split_name] = {"min": None, "max": None, "samples": 0}
            continue
        summary[split_name] = {
            "min": split_df["_asof_date"].min().strftime("%Y-%m-%d"),
            "max": split_df["_asof_date"].max().strftime("%Y-%m-%d"),
            "samples": int(len(split_df)),
        }
    return summary


def validate_temporal_split(temporal_split: dict[str, dict[str, Any]]) -> None:
    required = ["train", "valid", "test"]
    missing = [split for split in required if temporal_split.get(split, {}).get("samples", 0) <= 0]
    if missing:
        raise ValueError(f"Temporal split requires non-empty splits: {missing}")

    train_max = pd.Timestamp(temporal_split["train"]["max"])
    valid_min = pd.Timestamp(temporal_split["valid"]["min"])
    valid_max = pd.Timestamp(temporal_split["valid"]["max"])
    test_min = pd.Timestamp(temporal_split["test"]["min"])
    if not train_max < valid_min:
        raise ValueError(
            "Temporal split violation: train max date must be earlier than valid min date "
            f"({train_max.date()} >= {valid_min.date()})"
        )
    if not valid_max < test_min:
        raise ValueError(
            "Temporal split violation: valid max date must be earlier than test min date "
            f"({valid_max.date()} >= {test_min.date()})"
        )


def build_report(
    *,
    labels_path: Path,
    daily_dir: Path,
    output_dir: Path,
    dataset: pd.DataFrame,
    feature_columns: list[str],
    temporal_split: dict[str, dict[str, Any]],
    skipped_samples: int,
    skip_examples: list[str],
    model_metrics: dict[str, dict[str, Any]],
    ensemble_summary: dict[str, Any] | None = None,
) -> str:
    lines = [
        "# Long Base Breakout Baseline Report",
        "",
        "## Inputs",
        f"- labels_path: `{labels_path}`",
        f"- daily_dir: `{daily_dir}`",
        f"- output_dir: `{output_dir}`",
        "",
        "## Dataset",
        f"- samples: {len(dataset)}",
        f"- features: {len(feature_columns)}",
        f"- skipped_samples: {skipped_samples}",
        f"- date_range: {dataset['asof_date'].min()} to {dataset['asof_date'].max()}",
        "",
        "## Label Distribution",
        _series_to_markdown(dataset["label"].value_counts().sort_index()),
        "",
        "## Split Distribution",
        _series_to_markdown(dataset["split"].value_counts()),
        "",
        "## Temporal Split Check",
        _frame_to_markdown(
            pd.DataFrame(
                [
                    {
                        "split": split_name,
                        "min_asof_date": values["min"],
                        "max_asof_date": values["max"],
                        "samples": values["samples"],
                    }
                    for split_name, values in temporal_split.items()
                ]
            )
        ),
        "",
        "## Label x Split",
        _frame_to_markdown(pd.crosstab(dataset["label"], dataset["split"])),
        "",
        "## Metrics Summary",
        _frame_to_markdown(_build_metrics_summary_frame(model_metrics)),
        "",
        "## Metrics Detail",
    ]
    if ensemble_summary is not None:
        lines.extend(
            [
                "## LGBM XGBoost Ensemble",
                f"- latest_date: {ensemble_summary['latest_date']}",
                f"- latest_rows: {ensemble_summary['latest_rows']}",
                f"- latest_candidates: {ensemble_summary['latest_candidates']}",
                f"- ensemble_path: `{ensemble_summary['ensemble_path']}`",
                f"- latest_candidates_path: `{ensemble_summary['latest_candidates_path']}`",
                f"- report_path: `{ensemble_summary['report_path']}`",
                "",
                _frame_to_markdown(_build_ensemble_split_summary_frame(ensemble_summary)),
                "",
            ]
        )
    for model_name, metrics in model_metrics.items():
        lines.extend([f"### {model_name}", ""])
        for split_name, split_metrics in metrics.items():
            lines.extend([f"#### {split_name}", _metrics_to_markdown(split_metrics), ""])
    lines.extend(
        [
            "## Top Feature Missing Rates",
            _series_to_markdown(dataset[feature_columns].isna().mean().sort_values(ascending=False).head(20)),
            "",
            "## Skip Examples",
        ]
    )
    lines.extend([f"- {item}" for item in skip_examples] or ["- none"])
    lines.append("")
    return "\n".join(lines)


def build_ensemble_report(summary: dict[str, Any], latest_candidates: pd.DataFrame) -> str:
    lines = [
        "# LGBM XGBoost Ensemble Report",
        "",
        f"- latest_date: {summary['latest_date']}",
        f"- latest_rows: {summary['latest_rows']}",
        f"- latest_candidates: {summary['latest_candidates']}",
        f"- threshold: {summary['threshold']}",
        f"- ensemble_path: `{summary['ensemble_path']}`",
        f"- latest_predictions_path: `{summary['latest_predictions_path']}`",
        f"- latest_candidates_path: `{summary['latest_candidates_path']}`",
        "",
        "## Split Summary",
        _frame_to_markdown(_build_ensemble_split_summary_frame(summary)),
        "",
        "## Latest Candidates Top 30",
    ]
    display_cols = [
        "ts_code",
        "asof_date",
        "ensemble_score",
        "lgbm_score",
        "xgb_score",
        "score_gap",
        "model_agreement",
        "label",
        "label_source",
        "pattern_type",
    ]
    existing_cols = [col for col in display_cols if col in latest_candidates.columns]
    lines.append(_frame_to_markdown(latest_candidates[existing_cols].head(30)))
    lines.append("")
    return "\n".join(lines)


def _build_ensemble_split_summary_frame(summary: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for split_name, values in summary["split_summary"].items():
        rows.append(
            {
                "split": split_name,
                "samples": values["samples"],
                "candidates": values["candidates"],
                "agreement_rate": _format_metric(values["agreement_rate"]),
                "mean_score": _format_metric(values["mean_score"]),
            }
        )
    return pd.DataFrame(rows)


def _build_metrics_summary_frame(model_metrics: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for model_name, metrics in model_metrics.items():
        for split_name, split_metrics in metrics.items():
            rows.append(
                {
                    "model": model_name,
                    "split": split_name,
                    "samples": split_metrics.get("samples"),
                    "positive_rate": _format_metric(split_metrics.get("positive_rate")),
                    "precision": _format_metric(split_metrics.get("precision")),
                    "recall": _format_metric(split_metrics.get("recall")),
                    "f1": _format_metric(split_metrics.get("f1")),
                    "roc_auc": _format_metric(split_metrics.get("roc_auc")),
                    "pr_auc": _format_metric(split_metrics.get("pr_auc")),
                }
            )
    return pd.DataFrame(rows)


def _format_metric(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _nearest_not_later_idx(dates: pd.Series, target: pd.Timestamp) -> int | None:
    normalized = pd.to_datetime(dates, errors="coerce")
    eligible = normalized[normalized <= pd.Timestamp(target)]
    if eligible.empty:
        return None
    return int(eligible.index[-1])


def _last(series: pd.Series) -> float:
    return float(series.iloc[-1]) if len(series) else np.nan


def _safe_div(num: float, den: float) -> float:
    if pd.isna(num) or pd.isna(den) or abs(float(den)) <= 1e-12:
        return np.nan
    return float(num) / float(den)


def _pct_change(series: pd.Series, period: int) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) <= period:
        return np.nan
    return _safe_div(float(clean.iloc[-1]), float(clean.iloc[-1 - period])) - 1.0


def _range_pct(high: pd.Series, low: pd.Series, period: int) -> float:
    h = float(high.tail(period).max())
    l = float(low.tail(period).min())
    return _safe_div(h, l) - 1.0


def _close_position(close: pd.Series, high: pd.Series, low: pd.Series, period: int) -> float:
    c = _last(close)
    h = float(high.tail(period).max())
    l = float(low.tail(period).min())
    return _safe_div(c - l, h - l)


def _max_drawdown(close: pd.Series) -> float:
    clean = pd.to_numeric(close, errors="coerce").dropna()
    if clean.empty:
        return np.nan
    peak = clean.cummax()
    drawdown = clean / peak - 1.0
    return float(drawdown.min())


def _days_since_extreme(series: pd.Series, mode: str) -> float:
    clean = pd.to_numeric(series, errors="coerce").reset_index(drop=True)
    if clean.empty:
        return np.nan
    idx = int(clean.idxmax() if mode == "max" else clean.idxmin())
    return float(len(clean) - 1 - idx)


def _metrics_to_markdown(metrics: dict[str, Any]) -> str:
    rows = []
    for key, value in metrics.items():
        if key == "confusion_matrix":
            rows.append({"metric": key, "value": str(value)})
        elif isinstance(value, float):
            rows.append({"metric": key, "value": f"{value:.6f}"})
        else:
            rows.append({"metric": key, "value": value})
    return _frame_to_markdown(pd.DataFrame(rows))


def _series_to_markdown(series: pd.Series) -> str:
    if series.empty:
        return "_none_"
    frame = series.rename("value").reset_index()
    frame.columns = ["key", "value"]
    return _frame_to_markdown(frame)


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_none_"
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
        if frame.columns[0] == "index":
            frame = frame.rename(columns={"index": "key"})
    columns = [str(col) for col in frame.columns]
    rows = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        rows.append("| " + " | ".join(str(row[col]).replace("|", "\\|") for col in frame.columns) + " |")
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train long-base breakout tabular baseline.")
    parser.add_argument("--labels-path", default="../market_pattern_labeler/outputs/labels_long_base_breakout.csv")
    parser.add_argument("--daily-dir", default=str(DEFAULT_US_DAILY_DIR))
    parser.add_argument("--output-dir", default="outputs/models/w_bottom/long_base_breakout_baseline")
    parser.add_argument("--min-history", type=int, default=252)
    parser.add_argument("--max-window", type=int, default=504)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["logistic_regression"],
        help="Models to train. Choices/aliases: logistic_regression/lr, lightgbm/lgbm, xgboost/xgb.",
    )
    parser.add_argument(
        "--allow-non-temporal-split",
        action="store_true",
        help="Do not fail when train/valid/test dates overlap.",
    )
    args = parser.parse_args()

    summary = run_pipeline(
        labels_path=args.labels_path,
        daily_dir=args.daily_dir,
        output_dir=args.output_dir,
        min_history=args.min_history,
        max_window=args.max_window,
        threshold=args.threshold,
        random_seed=args.random_seed,
        require_temporal_split=not args.allow_non_temporal_split,
        models=args.models,
    )
    print("Long-base baseline finished:")
    for key, value in summary.items():
        if key != "metrics":
            print(f"  {key}: {value}")
    for model_name, metrics_by_split in summary["metrics"].items():
        for split_name, metrics in metrics_by_split.items():
            print(f"  {model_name}_{split_name}_f1: {metrics['f1']:.6f}")
            print(f"  {model_name}_{split_name}_roc_auc: {metrics['roc_auc']:.6f}")


if __name__ == "__main__":
    main()
