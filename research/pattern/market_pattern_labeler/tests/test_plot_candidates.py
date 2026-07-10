from pathlib import Path

import pandas as pd

from market_pattern_labeler.review.plot_candidates import (
    plot_candidate,
    plot_candidates_batch,
    select_candidates,
)


def _candidate(ts_code: str = "AAPL", asof_date: str = "2026-01-30", score: float = 0.9) -> dict:
    return {
        "sample_id": f"{ts_code}_{asof_date}",
        "ts_code": ts_code,
        "asof_date": asof_date,
        "pattern_stage": "w_bottom_breakout",
        "candidate_score": score,
        "window": "short",
        "left_bottom_date": "2026-01-09",
        "left_bottom_price": 70.0,
        "middle_peak_date": "2026-01-16",
        "neckline_price": 85.0,
        "right_bottom_date": "2026-01-23",
        "right_bottom_price": 72.0,
        "current_close": 86.0,
        "prior_high_date": "2026-01-02",
        "prior_high_price": 100.0,
        "prior_drawdown_pct": 0.30,
        "middle_rebound_pct": 0.21,
        "bottom_similarity_pct": 0.03,
        "neckline_distance_pct": -0.01,
        "volume_ratio_20": 1.3,
    }


def _daily_frame(periods: int = 40) -> pd.DataFrame:
    close = (
        [100, 95, 88, 80, 72, 70, 73, 78, 83, 85]
        + [82, 78, 74, 72, 75, 80, 84, 86, 87, 86]
        + [86 + (idx % 3) for idx in range(max(0, periods - 20))]
    )
    dates = pd.date_range("2026-01-01", periods=len(close), freq="B")
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": close,
            "high": [value * 1.01 for value in close],
            "low": [value * 0.99 for value in close],
            "close": close,
            "vol": [1000 + idx * 10 for idx in range(len(close))],
            "ts_code": ["AAPL"] * len(close),
        }
    )


def test_select_candidates_filters_sorts_and_samples() -> None:
    df = pd.DataFrame(
        [
            _candidate("AAPL", score=0.7),
            {**_candidate("MSFT", score=0.9), "pattern_stage": "w_bottom_forming"},
            _candidate("NVDA", score=0.8),
        ]
    )

    top = select_candidates(df, stage="w_bottom_breakout", top_n=2, sample="top")
    random_one = select_candidates(df, top_n=2, sample="random", random_seed=7)
    random_two = select_candidates(df, top_n=2, sample="random", random_seed=7)

    assert top["ts_code"].tolist() == ["NVDA", "AAPL"]
    assert random_one["ts_code"].tolist() == random_two["ts_code"].tolist()


def test_select_candidates_year_stratified_balances_years() -> None:
    df = pd.DataFrame(
        [
            _candidate("A2022", asof_date="2022-01-10", score=0.99),
            _candidate("B2022", asof_date="2022-02-10", score=0.98),
            _candidate("C2022", asof_date="2022-03-10", score=0.97),
            _candidate("A2023", asof_date="2023-01-10", score=0.80),
            _candidate("B2023", asof_date="2023-02-10", score=0.79),
            _candidate("A2024", asof_date="2024-01-10", score=0.70),
        ]
    )

    selected = select_candidates(df, top_n=4, sample="year_stratified")

    assert selected["ts_code"].tolist() == ["A2022", "A2023", "A2024", "B2022"]
    assert pd.to_datetime(selected["asof_date"]).dt.year.value_counts().loc[2022] == 2


def test_plot_candidate_generates_png(tmp_path: Path) -> None:
    output_path = tmp_path / "candidate.png"

    anchor_date = plot_candidate(pd.Series(_candidate()), _daily_frame(), output_path, pre_days=20, post_days=5)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert anchor_date == "2026-01-26"


def test_plot_candidates_batch_writes_review_csv(tmp_path: Path) -> None:
    data_dir = tmp_path / "daily"
    data_dir.mkdir()
    _daily_frame().to_parquet(data_dir / "AAPL.parquet", index=False)
    _daily_frame().assign(ts_code="MSFT").to_parquet(data_dir / "MSFT.parquet", index=False)
    candidates_path = tmp_path / "candidates.csv"
    pd.DataFrame([_candidate("AAPL", score=0.8), _candidate("MSFT", score=0.9)]).to_csv(
        candidates_path, index=False
    )
    output_dir = tmp_path / "charts"

    summary = plot_candidates_batch(
        candidates_path=candidates_path,
        data_dir=data_dir,
        output_dir=output_dir,
        top_n=2,
        pre_days=20,
        post_days=5,
    )
    review = pd.read_csv(output_dir / "review.csv")

    assert summary.charts_generated == 2
    assert (output_dir / "review.csv").exists()
    assert (output_dir / "index.html").exists()
    assert "chart_path" in review.columns
    assert "chart_anchor_date" in review.columns
    assert "manual_review" in review.columns
    assert "review_note" in review.columns
    assert all((output_dir / path).exists() for path in review["chart_path"])


def test_plot_candidates_batch_skips_missing_symbol(tmp_path: Path) -> None:
    data_dir = tmp_path / "daily"
    data_dir.mkdir()
    _daily_frame().to_parquet(data_dir / "AAPL.parquet", index=False)
    candidates_path = tmp_path / "candidates.csv"
    pd.DataFrame([_candidate("AAPL", score=0.8), _candidate("MISSING", score=0.9)]).to_csv(
        candidates_path, index=False
    )

    summary = plot_candidates_batch(
        candidates_path=candidates_path,
        data_dir=data_dir,
        output_dir=tmp_path / "charts",
        top_n=2,
        pre_days=20,
        post_days=5,
    )

    assert summary.charts_generated == 1
    assert summary.skipped_candidates == 1


def test_plot_candidate_uses_nearest_not_later_asof_date(tmp_path: Path) -> None:
    output_path = tmp_path / "candidate.png"
    candidate = pd.Series(_candidate(asof_date="2026-01-31"))

    plot_candidate(candidate, _daily_frame(), output_path, pre_days=20, post_days=5)

    assert output_path.exists()


def test_plot_candidate_can_anchor_on_asof_date(tmp_path: Path) -> None:
    output_path = tmp_path / "candidate.png"
    candidate = pd.Series(_candidate(asof_date="2026-02-25"))

    anchor_date = plot_candidate(candidate, _daily_frame(), output_path, pre_days=20, post_days=5, anchor="asof")

    assert output_path.exists()
    assert anchor_date == "2026-02-25"
