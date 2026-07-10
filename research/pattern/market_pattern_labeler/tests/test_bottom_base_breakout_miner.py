from pathlib import Path

import pandas as pd

from market_pattern_labeler.miners.w_bottom.bottom_base_breakout import (
    BottomBaseBreakoutConfig,
    BottomBaseBreakoutMiner,
)
from market_pattern_labeler.pipelines.run_miner import run_miner


def _segment(start: float, end: float, count: int) -> list[float]:
    if count <= 1:
        return [end]
    step = (end - start) / float(count - 1)
    return [start + step * idx for idx in range(count)]


def _frame(close: list[float], start: str = "2020-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(close), freq="B")
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": close,
            "high": [value * 1.01 for value in close],
            "low": [value * 0.99 for value in close],
            "close": close,
            "vol": [1000 + idx * 10 for idx in range(len(close))],
        }
    )


def _base_breakout_prices() -> list[float]:
    return (
        _segment(120, 75, 24)
        + [76, 78, 80, 82, 79, 77, 76, 78, 81, 83, 80, 78, 77, 79, 82]
        + [80, 79, 78, 80, 82, 83, 81, 80, 79, 81, 82, 83, 81, 80, 79]
        + [82, 84, 86]
    )


def _rounding_bottom_prices() -> list[float]:
    return (
        _segment(100, 70, 24)
        + [70, 71, 72, 71, 72, 73, 74, 73, 74, 75, 74, 75, 76, 75, 76]
        + [75, 76, 77, 76, 77, 78, 77, 78, 79, 78, 79, 80, 79, 80, 82]
        + [84, 86]
    )


def _cfg(mode: str = "latest") -> BottomBaseBreakoutConfig:
    return BottomBaseBreakoutConfig.from_dict(
        {
            "scan": {
                "mode": mode,
                "asof_stride": 1,
                "min_asof_date": "2020-01-01",
                "max_candidates_per_symbol": 10,
                "min_days_between_candidates": 10,
            },
            "windows": [{"name": "test", "lookback": 50}],
            "rules": {
                "min_prior_drawdown_pct": 0.15,
                "min_base_duration_bars": 20,
                "max_base_range_pct": 0.35,
                "max_base_close_std_pct": 0.14,
                "min_neckline_rebound_from_base_low_pct": 0.06,
                "min_touches_in_base_zone": 2,
                "min_breakout_distance_pct": 0.00,
                "max_breakout_distance_pct": 0.08,
                "max_breakout_recency_bars": 5,
                "min_right_recovery_pct": 0.08,
                "min_close_vs_base_low_pct": 0.08,
            },
            "volume": {"enable": True, "ma_window": 10, "breakout_volume_ratio": 1.05},
        }
    )


def test_bottom_base_breakout_standard_pattern_hits() -> None:
    out = BottomBaseBreakoutMiner(_cfg()).scan_one("AAPL", _frame(_base_breakout_prices()))

    assert len(out) >= 1
    row = out.iloc[0]
    assert row["pattern_stage"] == "bottom_base_recent_breakout"
    assert row["miner_name"] == "bottom_base_breakout"
    assert float(row["prior_drawdown_pct"]) >= 0.15
    assert float(row["breakout_distance_pct"]) <= 0.08
    assert 0 <= float(row["candidate_score"]) <= 1


def test_bottom_base_breakout_hits_non_w_rounding_base() -> None:
    out = BottomBaseBreakoutMiner(_cfg()).scan_one("MSFT", _frame(_rounding_bottom_prices()))

    assert len(out) >= 1
    assert (out["pattern_stage"] == "bottom_base_recent_breakout").all()


def test_bottom_base_breakout_rejects_overextended_breakout() -> None:
    prices = _base_breakout_prices()[:-3] + [90, 95]

    out = BottomBaseBreakoutMiner(_cfg()).scan_one("NVDA", _frame(prices))

    assert out.empty


def test_bottom_base_breakout_requires_prior_drawdown() -> None:
    prices = _segment(100, 95, 24) + [96, 97, 98, 99, 98, 97, 96, 98, 99, 100] * 3 + [101, 104]

    out = BottomBaseBreakoutMiner(_cfg()).scan_one("META", _frame(prices))

    assert out.empty


def test_bottom_base_breakout_rejects_volatile_base() -> None:
    prices = _segment(120, 75, 24) + [75, 95, 70, 96, 72, 94, 71, 97, 73, 95] * 3 + [98, 101]

    out = BottomBaseBreakoutMiner(_cfg()).scan_one("TSLA", _frame(prices))

    assert out.empty


def test_bottom_base_breakout_historical_scan_finds_multiple_periods() -> None:
    prices = _base_breakout_prices() + [88, 87, 86, 85, 84] * 8 + _base_breakout_prices()
    out = BottomBaseBreakoutMiner(_cfg(mode="historical")).scan_one("AMD", _frame(prices))

    assert len(out) >= 2
    assert out["asof_date"].nunique() >= 2
    assert out["asof_date"].max() != out["asof_date"].min()


def test_bottom_base_breakout_latest_scan_only_checks_latest_state() -> None:
    prices = _base_breakout_prices() + [88, 87, 86, 85, 84] * 8
    out = BottomBaseBreakoutMiner(_cfg(mode="latest")).scan_one("IBM", _frame(prices))

    assert out.empty


def test_run_miner_registers_bottom_base_breakout(tmp_path: Path) -> None:
    data_dir = tmp_path / "daily"
    data_dir.mkdir()
    _frame(_base_breakout_prices()).to_parquet(data_dir / "AAPL.parquet", index=False)
    config_path = tmp_path / "bottom_base_breakout.yaml"
    config_path.write_text(
        "\n".join(
            [
                "miner: bottom_base_breakout",
                "scan:",
                "  mode: latest",
                "windows:",
                "  - name: test",
                "    lookback: 50",
                "rules:",
                "  min_prior_drawdown_pct: 0.15",
                "  min_base_duration_bars: 20",
                "  max_base_range_pct: 0.35",
                "  max_base_close_std_pct: 0.14",
                "  min_neckline_rebound_from_base_low_pct: 0.06",
                "  max_breakout_distance_pct: 0.08",
                "  max_breakout_recency_bars: 5",
            ]
        ),
        encoding="utf-8",
    )
    output_csv = tmp_path / "out.csv"

    out = run_miner(
        data_dir=str(data_dir),
        output_csv=str(output_csv),
        miner_name="bottom_base_breakout",
        config_path=str(config_path),
    )

    assert output_csv.exists()
    assert len(out) >= 1
    assert (out["miner_name"] == "bottom_base_breakout").all()
