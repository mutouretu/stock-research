import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market_pattern_labeler.miners.type_v.positive.range_support_rebound import (
    RangeSupportReboundConfig,
    RangeSupportReboundMiner,
)
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS


def _range_support_rebound_frame() -> pd.DataFrame:
    early = [11.2 + (i % 10) * 0.03 for i in range(110)]
    range_body = [
        10.15,
        10.35,
        10.8,
        11.2,
        11.55,
        11.8,
        11.4,
        10.9,
        10.45,
        10.2,
    ] * 9
    tail = [10.12, 10.08, 10.15, 10.22, 10.32, 10.45, 10.58, 10.70, 10.82, 10.95]
    close = early + range_body + tail
    dates = pd.date_range("2025-01-01", periods=len(close), freq="B")
    vol = [1000 + (i % 5) * 15 for i in range(len(close) - len(tail))] + [
        1150,
        1180,
        1220,
        1260,
        1300,
        1360,
        1420,
        1480,
        1540,
        1600,
    ]
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": close,
            "high": [x * 1.01 for x in close],
            "low": [x * 0.99 for x in close],
            "close": close,
            "vol": vol,
        }
    )


class TestRangeSupportReboundMiner(unittest.TestCase):
    def test_scan_one_generates_candidates_after_range_support_rebound(self):
        miner = RangeSupportReboundMiner(RangeSupportReboundConfig(top_n_per_symbol=10))

        out = miner.scan_one("000001.SZ", _range_support_rebound_frame())

        self.assertIsInstance(out, pd.DataFrame)
        self.assertTrue(set(CANDIDATE_COLUMNS).issubset(set(out.columns)))
        self.assertGreater(len(out), 0)
        self.assertTrue((out["miner_name"] == "range_support_rebound").all())
        self.assertTrue(out["rule_flags"].str.contains("range_sideways").any())
        self.assertTrue(out["rule_flags"].str.contains("recent_support_touch").any())
        self.assertTrue(out["rule_flags"].str.contains("rebound_ok").any())


if __name__ == "__main__":
    unittest.main()
