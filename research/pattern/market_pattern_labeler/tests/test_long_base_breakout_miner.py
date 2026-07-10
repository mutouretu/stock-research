from pathlib import Path

import pandas as pd

from market_pattern_labeler.miners.w_bottom.long_base_breakout import (
    LongBaseBreakoutConfig,
    LongBaseBreakoutMiner,
    count_separated_support_touches,
)
from market_pattern_labeler.pipelines.run_miner import run_miner


def _segment(start: float, end: float, count: int) -> list[float]:
    if count <= 1:
        return [end]
    step = (end - start) / float(count - 1)
    return [start + step * idx for idx in range(count)]


def _frame(close: list[float], start: str = "2018-01-01", ts_code: str = "AAPL") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(close), freq="B")
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": close,
            "high": [value * 1.01 for value in close],
            "low": [value * 0.99 for value in close],
            "close": close,
            "vol": [1000 + idx * 3 for idx in range(len(close))],
            "ts_code": [ts_code] * len(close),
        }
    )


def _long_base_prices(final_close: float = 78.0) -> list[float]:
    base: list[float] = []
    pattern = [62, 64, 67, 70, 74, 72, 68, 64, 61, 63, 66, 69, 72, 70, 66, 63]
    while len(base) < 220:
        base.extend(pattern)
    base = base[:220]
    right_side = _segment(72, 74, 40)
    return _segment(100, 60, 30) + base + right_side + [74, 75, 76, final_close]


def _rounding_long_base_prices() -> list[float]:
    base = [60 + min(idx, 170) * 0.08 + (idx % 9) * 0.25 for idx in range(260)]
    return _segment(100, 60, 30) + base + [73, 75, 76, 77]


def _cfg(mode: str = "latest") -> LongBaseBreakoutConfig:
    return LongBaseBreakoutConfig.from_dict(
        {
            "scan": {
                "mode": mode,
                "asof_stride": 1,
                "min_asof_date": "2018-01-01",
                "max_candidates_per_symbol": 10,
                "min_days_between_candidates": 60,
            },
            "windows": [{"name": "test_long", "lookback": 294}],
            "rules": {
                "min_prior_drawdown_pct": 0.20,
                "min_base_duration_bars": 252,
                "support_zone_tolerance_pct": 0.15,
                "min_support_touches": 2,
                "min_support_touch_separation_bars": 40,
                "max_support_zone_std_pct": 0.12,
                "min_neckline_rebound_from_support_pct": 0.15,
                "max_neckline_to_prior_high_ratio": 0.90,
                "min_breakout_distance_pct": 0.00,
                "max_breakout_distance_pct": 0.10,
                "max_breakout_recency_bars": 20,
                "min_right_side_duration_bars": 40,
            },
            "volume": {"enable": True, "ma_window": 20, "breakout_volume_ratio": 1.05},
            "monthly_trend": {"enable": False},
        }
    )


def test_count_separated_support_touches() -> None:
    count, indices = count_separated_support_touches(
        close=pd.Series([61, 62, 70, 61, 62, 71, 61]),
        support_zone_upper=63,
        min_separation_bars=3,
    )

    assert count == 3
    assert indices == [0, 3, 6]


def test_long_base_breakout_hits_long_base() -> None:
    out = LongBaseBreakoutMiner(_cfg()).scan_one("AAPL", _frame(_long_base_prices()))

    assert len(out) >= 1
    row = out.iloc[0]
    assert row["pattern_stage"] == "long_base_recent_breakout"
    assert int(row["base_duration_bars"]) >= 252
    assert float(row["breakout_distance_pct"]) <= 0.10
    assert int(row["support_touch_count"]) >= 2


def test_long_base_breakout_hits_non_w_rounding_base() -> None:
    out = LongBaseBreakoutMiner(_cfg()).scan_one("MSFT", _frame(_rounding_long_base_prices()))

    assert len(out) >= 1
    assert (out["miner_name"] == "long_base_breakout").all()


def test_long_base_breakout_rejects_short_base() -> None:
    prices = _segment(100, 60, 20) + [62, 64, 66, 68, 70, 72] * 10 + [76]

    out = LongBaseBreakoutMiner(_cfg()).scan_one("NVDA", _frame(prices))

    assert out.empty


def test_long_base_breakout_rejects_unstable_support() -> None:
    volatile = _segment(100, 60, 30) + ([60, 85, 58, 88, 62, 90, 57, 86] * 34)[:260] + [92]

    out = LongBaseBreakoutMiner(_cfg()).scan_one("TSLA", _frame(volatile))

    assert out.empty


def test_long_base_breakout_requires_multiple_support_touches() -> None:
    base = [80 + (idx % 5) for idx in range(260)]
    prices = _segment(100, 60, 30) + [60] + base + [86]

    out = LongBaseBreakoutMiner(_cfg()).scan_one("META", _frame(prices))

    assert out.empty


def test_long_base_breakout_rejects_overextended_breakout() -> None:
    out = LongBaseBreakoutMiner(_cfg()).scan_one("AMD", _frame(_long_base_prices(final_close=95.0)))

    assert out.empty


def test_long_base_breakout_historical_scan_multiple_periods() -> None:
    prices = _long_base_prices() + [76, 74, 72, 70, 68] * 30 + _long_base_prices()
    out = LongBaseBreakoutMiner(_cfg(mode="historical")).scan_one("IBM", _frame(prices))

    assert len(out) >= 2
    assert out["asof_date"].nunique() >= 2


def test_long_base_breakout_monthly_trend_filter_rejects_without_long_uptrend() -> None:
    cfg = _cfg()
    cfg.monthly_trend.enable = True
    cfg.monthly_trend.min_months = 36

    out = LongBaseBreakoutMiner(cfg).scan_one("IBM", _frame(_long_base_prices()))

    assert out.empty


def test_run_miner_symbols_filter(tmp_path: Path) -> None:
    data_dir = tmp_path / "daily"
    data_dir.mkdir()
    _frame(_long_base_prices(), ts_code="OLED").to_parquet(data_dir / "OLED.parquet", index=False)
    _frame(_long_base_prices(), ts_code="DELL").to_parquet(data_dir / "DELL.parquet", index=False)
    output_csv = tmp_path / "out.csv"
    config_path = tmp_path / "long_base_breakout.yaml"
    config_path.write_text(
        """
long_base_breakout:
  scan:
    mode: latest
    max_candidates_per_symbol: 10
  windows:
    - name: test_long
      lookback: 294
  rules:
    min_base_duration_bars: 252
    min_support_touch_separation_bars: 40
    max_breakout_recency_bars: 20
""".strip(),
        encoding="utf-8",
    )

    out = run_miner(
        data_dir=str(data_dir),
        output_csv=str(output_csv),
        miner_name="long_base_breakout",
        config_path=str(config_path),
        symbols="OLED",
    )

    assert output_csv.exists()
    assert not out.empty
    assert set(out["ts_code"]) <= {"OLED"}
