from pathlib import Path

import pandas as pd

from market_pattern_labeler.cli.main import build_parser
from market_pattern_labeler.labels.build_ml_labels import (
    NegativeAcceptance,
    assign_time_split,
    build_ml_labels,
    build_positive_labels,
    sample_downtrend_continuation,
    sample_random_non_events,
    sample_weak_base_non_breakout,
)


def _frame(close: list[float], start: str = "2020-01-01", symbol: str = "AAPL") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(close), freq="B")
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": close,
            "high": [value * 1.01 for value in close],
            "low": [value * 0.99 for value in close],
            "close": close,
            "vol": [1000 + idx for idx in range(len(close))],
            "ts_code": [symbol] * len(close),
        }
    )


def _positive_candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": "AAPL",
                "asof_date": "2021-06-01",
                "confidence": 0.8,
                "candidate_score": 0.7,
                "miner_name": "long_base_breakout",
                "pattern_stage": "long_base_recent_breakout",
                "base_duration_bars": 504,
            }
        ]
    )


def _downtrend_frame() -> pd.DataFrame:
    close = [120 - idx * 0.18 for idx in range(360)]
    return _frame(close, symbol="DOWN")


def _weak_base_frame() -> pd.DataFrame:
    decline = [130 - idx * 0.21 for idx in range(330)]
    base = [64 + (idx % 20) * 0.25 for idx in range(260)]
    return _frame(decline + base, symbol="WEAK")


def _random_frame(symbol: str = "RAND") -> pd.DataFrame:
    close = [80 + (idx % 40) * 0.08 for idx in range(620)]
    return _frame(close, symbol=symbol)


def test_build_positive_labels_sets_required_fields() -> None:
    out, warnings = build_positive_labels(_positive_candidates())

    assert not warnings
    row = out.iloc[0]
    assert row["sample_id"] == "AAPL_2021-06-01_long_base_breakout_pos"
    assert row["label"] == 1
    assert row["label_source"] == "rule_long_base_breakout"
    assert row["pattern_type"] == "long_base_breakout"
    assert row["source_miner"] == "long_base_breakout"


def test_build_positive_labels_dedupes_by_best_score() -> None:
    candidates = pd.DataFrame(
        [
            {"ts_code": "AAPL", "asof_date": "2021-06-01", "candidate_score": 0.2},
            {"ts_code": "AAPL", "asof_date": "2021-06-01", "candidate_score": 0.9},
        ]
    )

    out, _ = build_positive_labels(candidates)

    assert len(out) == 1
    assert float(out.iloc[0]["candidate_score"]) == 0.9


def test_sample_random_non_events_excludes_positive_window() -> None:
    daily = {"AAPL": _random_frame("AAPL"), "MSFT": _random_frame("MSFT")}
    acceptance = NegativeAcceptance(
        positive_dates_by_symbol={"AAPL": [pd.Timestamp("2021-06-01")]},
        positive_exclusion_days=60,
        max_negative_per_symbol=20,
    )

    out, _ = sample_random_non_events(
        daily_by_symbol=daily,
        target_count=12,
        acceptance=acceptance,
        rng=__import__("numpy").random.default_rng(7),
    )

    assert len(out) == 12
    aapl_dates = pd.to_datetime(out.loc[out["ts_code"] == "AAPL", "asof_date"])
    assert all(abs(date - pd.Timestamp("2021-06-01")) > pd.Timedelta(days=60) for date in aapl_dates)


def test_sample_downtrend_continuation_hits_downtrend() -> None:
    acceptance = NegativeAcceptance(
        positive_dates_by_symbol={},
        positive_exclusion_days=60,
        max_negative_per_symbol=10,
    )

    out, _ = sample_downtrend_continuation(
        daily_by_symbol={"DOWN": _downtrend_frame()},
        target_count=3,
        acceptance=acceptance,
        rng=__import__("numpy").random.default_rng(11),
    )

    assert len(out) >= 1
    assert set(out["label_source"]) == {"downtrend_continuation"}
    assert (out["label"] == 0).all()


def test_sample_weak_base_non_breakout_hits_consolidation() -> None:
    acceptance = NegativeAcceptance(
        positive_dates_by_symbol={},
        positive_exclusion_days=60,
        max_negative_per_symbol=10,
    )

    out, _ = sample_weak_base_non_breakout(
        daily_by_symbol={"WEAK": _weak_base_frame()},
        target_count=3,
        acceptance=acceptance,
        rng=__import__("numpy").random.default_rng(13),
    )

    assert len(out) >= 1
    assert set(out["label_source"]) == {"weak_base_non_breakout"}
    assert (out["label"] == 0).all()


def test_assign_time_split_uses_date_boundaries() -> None:
    labels = pd.DataFrame(
        {
            "asof_date": ["2021-01-01", "2023-06-01", "2025-03-01"],
            "label": [1, 0, 0],
        }
    )

    out = assign_time_split(labels, train_end="2022-12-31", valid_end="2024-12-31")

    assert out["split"].tolist() == ["train", "valid", "test"]


def test_build_ml_labels_writes_csv_and_report(tmp_path: Path) -> None:
    data_dir = tmp_path / "daily"
    data_dir.mkdir()
    _random_frame("RAND").to_parquet(data_dir / "RAND.parquet", index=False)
    _downtrend_frame().to_parquet(data_dir / "DOWN.parquet", index=False)
    _weak_base_frame().to_parquet(data_dir / "WEAK.parquet", index=False)
    candidates_path = tmp_path / "candidates.csv"
    pd.DataFrame(
        [
            {"ts_code": "RAND", "asof_date": "2021-06-01", "candidate_score": 0.8, "confidence": 0.7},
            {"ts_code": "DOWN", "asof_date": "2021-04-01", "candidate_score": 0.7, "confidence": 0.7},
        ]
    ).to_csv(candidates_path, index=False)
    output = tmp_path / "labels.csv"

    summary = build_ml_labels(
        positive_candidates=candidates_path,
        data_dir=data_dir,
        output=output,
        negative_ratio=3,
        positive_exclusion_days=30,
        random_seed=42,
    )
    labels = pd.read_csv(output)

    assert output.exists()
    assert (tmp_path / "labels_report.md").exists()
    assert summary.positive_samples == 2
    assert summary.negative_samples == 6
    assert {"random_non_event", "downtrend_continuation", "weak_base_non_breakout"}.issubset(
        set(labels["label_source"])
    )
    assert {"sample_id", "ts_code", "asof_date", "label", "label_source", "split"}.issubset(labels.columns)


def test_build_ml_labels_respects_min_asof_date_and_reports_availability(tmp_path: Path) -> None:
    data_dir = tmp_path / "daily"
    data_dir.mkdir()
    _random_frame("RAND").to_parquet(data_dir / "RAND.parquet", index=False)
    _downtrend_frame().to_parquet(data_dir / "DOWN.parquet", index=False)
    _weak_base_frame().to_parquet(data_dir / "WEAK.parquet", index=False)
    candidates_path = tmp_path / "candidates.csv"
    pd.DataFrame(
        [
            {"ts_code": "RAND", "asof_date": "2020-06-01", "candidate_score": 0.8, "confidence": 0.7},
            {"ts_code": "RAND", "asof_date": "2021-06-01", "candidate_score": 0.9, "confidence": 0.7},
        ]
    ).to_csv(candidates_path, index=False)
    output = tmp_path / "labels.csv"

    summary = build_ml_labels(
        positive_candidates=candidates_path,
        data_dir=data_dir,
        output=output,
        negative_ratio=1,
        positive_exclusion_days=30,
        min_asof_date="2021-01-01",
        random_seed=42,
    )
    labels = pd.read_csv(output)
    report_text = (tmp_path / "labels_report.md").read_text(encoding="utf-8")

    assert summary.positive_samples == 1
    assert pd.to_datetime(labels["asof_date"]).min() >= pd.Timestamp("2021-01-01")
    assert "## Data Availability Validation" in report_text
    assert "availability_status: ok" in report_text
    assert "drop positive rows before min_asof_date=2021-01-01: 1" in report_text


def test_cli_registers_build_ml_labels() -> None:
    parser = build_parser()

    args = parser.parse_args(["build-ml-labels", "--min-asof-date", "2004-01-01"])

    assert args.command == "build-ml-labels"
    assert args.negative_ratio == 3.0
    assert args.min_asof_date == "2004-01-01"
