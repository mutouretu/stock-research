import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market_pattern_labeler.miners.type_v.positive.bottom_rebound import (
    BottomReboundConfig,
    BottomReboundMiner,
)
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS


def _bottom_rebound_frame(rebound_tail: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2025-09-01", periods=140, freq="B")
    down = [20.0 - i * 0.095 for i in range(100)]
    base = [10.0 + (i % 4) * 0.03 for i in range(30)]
    close = down + base + rebound_tail
    vol = [1000 + (i % 5) * 20 for i in range(130)] + [1500, 1600, 1700, 1800, 1900, 2000, 2100, 2200, 2300, 2400]
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": close,
            "high": [x * 1.015 for x in close],
            "low": [x * 0.985 for x in close],
            "close": close,
            "vol": vol,
            "amount": [100000.0] * len(close),
        }
    )


class TestBottomReboundMiner(unittest.TestCase):
    def test_scan_one_generates_candidates_after_midterm_bottom_rebound(self):
        tail = [10.05, 10.08, 10.1, 10.12, 10.2, 10.35, 10.55, 10.75, 10.95, 11.2]
        df = _bottom_rebound_frame(tail)
        miner = BottomReboundMiner(
            BottomReboundConfig(
                bottom_window=90,
                rebound_window=10,
                min_history=120,
                min_drawdown_from_window_high=0.2,
                max_position_in_bottom_range=0.5,
                min_rebound_from_recent_low=0.05,
                max_rebound_from_recent_low=0.3,
                min_ret_3d=0.02,
                min_ret_10d=0.05,
                min_vol_ratio_3d=1.05,
                min_candidate_score=7,
                top_n_per_symbol=10,
            )
        )

        out = miner.scan_one("000001.SZ", df)

        self.assertIsInstance(out, pd.DataFrame)
        self.assertTrue(set(CANDIDATE_COLUMNS).issubset(set(out.columns)))
        self.assertGreater(len(out), 0)
        self.assertTrue((out["miner_name"] == "bottom_rebound").all())
        self.assertTrue(out["rule_flags"].str.contains("drawdown_ok").any())
        self.assertTrue(out["rule_flags"].str.contains("rebound_ok").any())

    def test_scan_one_filters_overextended_rebound_date(self):
        tail = [10.05, 10.1, 10.2, 10.5, 11.0, 11.8, 12.6, 13.5, 14.2, 14.8]
        df = _bottom_rebound_frame(tail)
        miner = BottomReboundMiner(
            BottomReboundConfig(
                bottom_window=90,
                rebound_window=10,
                min_history=120,
                min_drawdown_from_window_high=0.2,
                max_position_in_bottom_range=0.8,
                min_rebound_from_recent_low=0.05,
                max_rebound_from_recent_low=0.3,
                min_candidate_score=5,
                top_n_per_symbol=10,
            )
        )

        out = miner.scan_one("000002.SZ", df)

        self.assertNotIn("2026-03-13", set(out["asof_date"].astype(str)))


if __name__ == "__main__":
    unittest.main()
