import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market_pattern_labeler.miners.type_n.phase1_breakout.positive import TypeNConfig, TypeNMiner
from market_pattern_labeler.schemas.candidate_columns import CANDIDATE_COLUMNS


class TestTypeNMiner(unittest.TestCase):
    def test_scan_one_generates_candidates_on_spike(self):
        dates = pd.date_range("2025-10-01", periods=100, freq="B")
        close = [10.0 + (i % 5) * 0.02 for i in range(95)] + [10.4, 10.7, 11.0, 11.3, 11.5]
        vol = [1000 + (i % 7) * 20 for i in range(95)] + [1800, 2200, 2600, 3000, 3200]

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

        cfg = TypeNConfig(
            lookback_window=60,
            min_history=70,
            max_base_range_pct=0.2,
            min_ret_1d=0.01,
            min_ret_3d=0.03,
            min_vol_ratio_1d=1.2,
            min_vol_ratio_3d=1.1,
            breakout_tolerance=0.02,
            min_candidate_score=4,
            top_n_per_symbol=20,
        )
        miner = TypeNMiner(cfg)

        out = miner.scan_one("000001.SZ", df)
        self.assertIsInstance(out, pd.DataFrame)
        self.assertTrue(set(CANDIDATE_COLUMNS).issubset(set(out.columns)))
        self.assertGreater(len(out), 0)

    def test_runup_rule_filters_late_stage_spike(self):
        dates = pd.date_range("2025-01-01", periods=220, freq="B")
        # First 160 bars trend up a lot, last bars spike with volume.
        base = [10.0 + i * 0.06 for i in range(200)]
        close = base + [22.8, 23.3, 23.8, 24.3, 24.7, 25.0, 25.2, 25.3, 25.5, 25.6, 25.8, 26.0, 26.1, 26.2, 26.4, 26.6, 26.7, 26.8, 26.9, 27.0]
        vol = [1200 + (i % 9) * 40 for i in range(210)] + [2600, 2800, 3000, 3200, 3400, 3600, 3500, 3400, 3300, 3200]

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

        cfg_no_filter = TypeNConfig(
            lookback_window=60,
            min_history=80,
            min_candidate_score=4,
            top_n_per_symbol=20,
            enable_runup_rule=False,
        )
        cfg_filter = TypeNConfig(
            lookback_window=60,
            min_history=80,
            min_candidate_score=4,
            top_n_per_symbol=20,
            enable_runup_rule=True,
            runup_window=150,
            max_runup_pct=0.3,
        )
        out_no_filter = TypeNMiner(cfg_no_filter).scan_one("000002.SZ", df)
        out_filter = TypeNMiner(cfg_filter).scan_one("000002.SZ", df)

        self.assertGreater(len(out_no_filter), 0)
        self.assertEqual(len(out_filter), 0)


if __name__ == "__main__":
    unittest.main()
