import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market_pattern_labeler.miners.type_n.phase1_breakout.rules.runup import RunupRule, RunupRuleConfig


class TestRunupRule(unittest.TestCase):
    def test_evaluate_marks_high_runup_as_not_ok(self):
        close = pd.Series([10.0, 10.5, 11.0, 15.0, 17.0])
        rule = RunupRule(RunupRuleConfig(window=3, max_runup_pct=0.4, score_weight=2))

        result = rule.evaluate(close)

        self.assertTrue(pd.isna(result.runup_pct.iloc[0]))
        self.assertTrue(pd.isna(result.runup_pct.iloc[1]))
        self.assertTrue(bool(result.ok.iloc[2]))
        self.assertFalse(bool(result.ok.iloc[-1]))
        self.assertEqual(int(result.score_bonus.iloc[2]), 2)
        self.assertEqual(int(result.score_bonus.iloc[-1]), 0)


if __name__ == "__main__":
    unittest.main()
