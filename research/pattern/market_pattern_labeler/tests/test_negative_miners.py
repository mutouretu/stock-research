import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market_pattern_labeler.miners.type_n.phase1_breakout.negative_easy.downtrend_simple import (
    DowntrendSimpleConfig,
    DowntrendSimpleMiner,
)
from market_pattern_labeler.miners.type_n.phase1_breakout.negative_hard.fake_breakout import (
    FakeBreakoutConfig,
    FakeBreakoutMiner,
)
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS


class TestNegativeMiners(unittest.TestCase):
    def test_downtrend_simple_generates_negative_candidates(self):
        dates = pd.date_range("2025-01-01", periods=120, freq="B")
        close = [20 - i * 0.08 for i in range(120)]
        df = pd.DataFrame(
            {
                "trade_date": dates,
                "open": close,
                "high": [x * 1.01 for x in close],
                "low": [x * 0.99 for x in close],
                "close": close,
            }
        )

        miner = DowntrendSimpleMiner(DowntrendSimpleConfig(top_n_per_symbol=10))
        out = miner.scan_one("000001.SZ", df)

        self.assertIsInstance(out, pd.DataFrame)
        self.assertTrue(set(CANDIDATE_COLUMNS).issubset(set(out.columns)))
        self.assertGreater(len(out), 0)
        self.assertTrue((out["label"] == 0).all())

    def test_fake_breakout_generates_negative_candidates(self):
        dates = pd.date_range("2025-01-01", periods=120, freq="B")
        base = [10.0 + (i % 5) * 0.02 for i in range(100)]
        tail = [10.4, 10.7, 11.0, 10.95, 10.8, 10.75, 10.7, 10.68, 10.66, 10.64,
                10.63, 10.62, 10.61, 10.60, 10.59, 10.58, 10.57, 10.56, 10.55, 10.54]
        close = base + tail
        vol = [1000 + (i % 7) * 15 for i in range(100)] + [2200, 2600, 2800] + [1300] * 17
        df = pd.DataFrame(
            {
                "trade_date": dates,
                "open": close,
                "high": [x * 1.01 for x in close],
                "low": [x * 0.99 for x in close],
                "close": close,
                "vol": vol,
            }
        )

        miner = FakeBreakoutMiner(FakeBreakoutConfig(top_n_per_symbol=10))
        out = miner.scan_one("000002.SZ", df)

        self.assertIsInstance(out, pd.DataFrame)
        self.assertTrue(set(CANDIDATE_COLUMNS).issubset(set(out.columns)))
        self.assertGreater(len(out), 0)
        self.assertTrue((out["label"] == 0).all())


if __name__ == "__main__":
    unittest.main()
