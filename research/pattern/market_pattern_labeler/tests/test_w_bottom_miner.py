from pathlib import Path

import pandas as pd

from market_pattern_labeler.miners.w_bottom.w_bottom import (
    WBottomConfig,
    WBottomMiner,
    find_local_highs,
    find_local_lows,
)
from market_pattern_labeler.pipelines.run_miner import run_miner


def _segment(start: float, end: float, count: int) -> list[float]:
    if count <= 1:
        return [end]
    step = (end - start) / float(count - 1)
    return [start + step * idx for idx in range(count)]


def _w_bottom_prices() -> list[float]:
    return (
        _segment(100, 70, 20)
        + _segment(71, 85, 10)
        + _segment(84, 72, 10)
        + _segment(73, 86, 10)
    )


def _frame(close: list[float], *, symbol_volume: bool = False) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=len(close), freq="B")
    data = {
        "trade_date": dates,
        "open": close,
        "high": [price * 1.01 for price in close],
        "low": [price * 0.99 for price in close],
        "close": close,
    }
    if symbol_volume:
        data["symbol"] = ["AAPL"] * len(close)
        data["volume"] = [1000 + idx * 5 for idx in range(len(close))]
    else:
        data["vol"] = [1000 + idx * 5 for idx in range(len(close))]
    return pd.DataFrame(data)


def _cfg() -> WBottomConfig:
    return WBottomConfig.from_dict(
        {
            "windows": [{"name": "test", "lookback": 50}],
            "rules": {
                "min_prior_drawdown_pct": 0.20,
                "min_middle_rebound_pct": 0.08,
                "max_bottom_price_diff_pct": 0.12,
                "max_right_bottom_break_pct": 0.10,
                "min_bottom_separation_days": 10,
                "max_bottom_separation_days": 40,
                "min_days_after_right_bottom": 5,
                "forming_neckline_distance_pct": 0.08,
                "breakout_neckline_buffer_pct": 0.00,
                "extrema_order": 2,
            },
            "volume": {"enable": True, "ma_window": 10, "breakout_volume_ratio": 1.05},
        }
    )


def test_find_local_extrema() -> None:
    close = pd.Series([5, 4, 3, 4, 5, 4, 6, 4, 3, 4])

    lows = find_local_lows(close, order=1)
    highs = find_local_highs(close, order=1)

    assert 2 in lows
    assert 8 in lows
    assert 4 in highs
    assert 6 in highs


def test_w_bottom_standard_pattern_hits() -> None:
    out = WBottomMiner(_cfg()).scan_one("AAPL", _frame(_w_bottom_prices()))

    assert len(out) >= 1
    row = out.iloc[0]
    assert row["pattern_stage"] in ["w_bottom_forming", "w_bottom_breakout"]
    assert abs(float(row["left_bottom_price"]) - 70.0) < 0.01
    assert abs(float(row["right_bottom_price"]) - 72.0) < 0.01
    assert abs(float(row["neckline_price"]) - 85.0) < 0.01
    assert 0 <= float(row["candidate_score"]) <= 1
    assert "prior_drawdown_ok" in row["rule_flags"]


def test_w_bottom_requires_prior_drawdown() -> None:
    close = (
        _segment(100, 95, 20)
        + _segment(96, 105, 10)
        + _segment(104, 96, 10)
        + _segment(97, 105, 10)
    )

    out = WBottomMiner(_cfg()).scan_one("MSFT", _frame(close))

    assert out.empty


def test_w_bottom_rejects_deep_right_bottom_break() -> None:
    close = (
        _segment(100, 70, 20)
        + _segment(71, 85, 10)
        + _segment(84, 55, 10)
        + _segment(56, 80, 10)
    )

    out = WBottomMiner(_cfg()).scan_one("NVDA", _frame(close))

    assert out.empty


def test_w_bottom_accepts_us_symbol_volume_shape() -> None:
    out = WBottomMiner(_cfg()).scan_one("BRK-B", _frame(_w_bottom_prices(), symbol_volume=True))

    assert len(out) >= 1
    assert (out["ts_code"] == "BRK-B").all()
    assert out["volume_ratio_20"].notna().all()


def test_run_miner_registers_w_bottom(tmp_path: Path) -> None:
    data_dir = tmp_path / "daily"
    data_dir.mkdir()
    _frame(_w_bottom_prices(), symbol_volume=True).to_parquet(data_dir / "BF-B.parquet", index=False)
    config_path = tmp_path / "w_bottom.yaml"
    config_path.write_text(
        "\n".join(
            [
                "miner: w_bottom",
                "windows:",
                "  - name: test",
                "    lookback: 50",
                "rules:",
                "  min_prior_drawdown_pct: 0.20",
                "  min_middle_rebound_pct: 0.08",
                "  max_bottom_price_diff_pct: 0.12",
                "  max_right_bottom_break_pct: 0.10",
                "  min_bottom_separation_days: 10",
                "  max_bottom_separation_days: 40",
                "  min_days_after_right_bottom: 5",
                "  extrema_order: 2",
            ]
        ),
        encoding="utf-8",
    )
    output_csv = tmp_path / "w_bottom.csv"

    out = run_miner(
        data_dir=str(data_dir),
        output_csv=str(output_csv),
        miner_name="w_bottom",
        config_path=str(config_path),
    )

    assert output_csv.exists()
    assert len(out) >= 1
    assert "left_bottom_date" in out.columns
    assert "neckline_price" in out.columns
    assert (out["miner_name"] == "w_bottom").all()
