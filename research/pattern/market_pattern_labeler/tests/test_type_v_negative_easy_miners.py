import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market_pattern_labeler.miners.type_v.negative_easy.steady_downtrend import (
    SteadyDowntrendConfig,
    SteadyDowntrendMiner,
)
from market_pattern_labeler.miners.type_v.negative_easy.steady_uptrend import (
    SteadyUptrendConfig,
    SteadyUptrendMiner,
)
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS


def _daily_frame(close: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=len(close), freq="B")
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": close,
            "high": [x * 1.01 for x in close],
            "low": [x * 0.99 for x in close],
            "close": close,
            "vol": [1000 + (i % 5) * 10 for i in range(len(close))],
        }
    )


class TestTypeVNegativeEasyMiners(unittest.TestCase):
    def test_steady_uptrend_generates_negative_candidates(self):
        close = [10.0 + i * 0.06 for i in range(220)]
        miner = SteadyUptrendMiner(SteadyUptrendConfig(top_n_per_symbol=10))

        out = miner.scan_one("000001.SZ", _daily_frame(close))

        self.assertIsInstance(out, pd.DataFrame)
        self.assertTrue(set(CANDIDATE_COLUMNS).issubset(set(out.columns)))
        self.assertGreater(len(out), 0)
        self.assertTrue((out["label"] == 0).all())
        self.assertTrue((out["miner_name"] == "steady_uptrend").all())
        self.assertTrue(out["rule_flags"].str.contains("up_60d").any())

    def test_steady_downtrend_generates_negative_candidates(self):
        close = [24.0 - i * 0.055 for i in range(220)]
        miner = SteadyDowntrendMiner(SteadyDowntrendConfig(top_n_per_symbol=10))

        out = miner.scan_one("000002.SZ", _daily_frame(close))

        self.assertIsInstance(out, pd.DataFrame)
        self.assertTrue(set(CANDIDATE_COLUMNS).issubset(set(out.columns)))
        self.assertGreater(len(out), 0)
        self.assertTrue((out["label"] == 0).all())
        self.assertTrue((out["miner_name"] == "steady_downtrend").all())
        self.assertTrue(out["rule_flags"].str.contains("down_60d").any())


if __name__ == "__main__":
    unittest.main()
