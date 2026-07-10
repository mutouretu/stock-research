import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market_pattern_labeler.data.daily_loader import iter_daily_frames


class TestDailyLoader(unittest.TestCase):
    def test_iter_daily_frames_infer_ts_code_and_sort(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            p = data_dir / "000001.SZ.parquet"
            df = pd.DataFrame(
                {
                    "trade_date": ["2026-01-03", "2026-01-01", "2026-01-02"],
                    "open": [10.0, 9.8, 9.9],
                    "high": [10.2, 10.0, 10.1],
                    "low": [9.7, 9.6, 9.8],
                    "close": [10.1, 9.9, 10.0],
                    "vol": [1000, 900, 950],
                }
            )
            df.to_parquet(p, index=False)

            rows = list(iter_daily_frames(data_dir))
            self.assertEqual(len(rows), 1)

            ts_code, loaded = rows[0]
            self.assertEqual(ts_code, "000001.SZ")
            self.assertEqual(loaded["trade_date"].astype(str).tolist()[0][:10], "2026-01-01")
            self.assertEqual(loaded["trade_date"].astype(str).tolist()[-1][:10], "2026-01-03")

    def test_iter_daily_frames_accepts_us_symbol_and_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            df = pd.DataFrame(
                {
                    "symbol": ["AAPL", "AAPL", "AAPL"],
                    "trade_date": ["2026-01-01", "2026-01-02", "2026-01-02"],
                    "open": [10.0, 10.5, 10.6],
                    "high": [10.2, 10.8, 10.9],
                    "low": [9.8, 10.2, 10.3],
                    "close": [10.1, 10.7, 10.8],
                    "volume": [1000, 1100, 1200],
                    "adj_close": [10.1, 10.7, 10.8],
                    "market": ["US", "US", "US"],
                }
            )
            df.to_parquet(data_dir / "AAPL.parquet", index=False)

            rows = list(iter_daily_frames(data_dir))

            self.assertEqual(len(rows), 1)
            ts_code, loaded = rows[0]
            self.assertEqual(ts_code, "AAPL")
            self.assertIn("ts_code", loaded.columns)
            self.assertIn("vol", loaded.columns)
            self.assertIn("adj_close", loaded.columns)
            self.assertIn("market", loaded.columns)
            self.assertEqual(loaded["ts_code"].iloc[0], "AAPL")
            self.assertEqual(loaded["vol"].tolist(), [1000, 1200])
            self.assertEqual(len(loaded), 2)

    def test_iter_daily_frames_infers_us_symbol_from_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            df = pd.DataFrame(
                {
                    "trade_date": ["2026-01-01"],
                    "open": [10.0],
                    "high": [10.2],
                    "low": [9.8],
                    "close": [10.1],
                    "vol": [1000],
                }
            )
            df.to_parquet(data_dir / "BRK-B.parquet", index=False)

            rows = list(iter_daily_frames(data_dir))

            self.assertEqual(len(rows), 1)
            ts_code, loaded = rows[0]
            self.assertEqual(ts_code, "BRK-B")
            self.assertEqual(loaded["ts_code"].iloc[0], "BRK-B")

    def test_iter_daily_frames_keeps_a_share_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            df = pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": ["2026-01-01"],
                    "open": [10.0],
                    "high": [10.2],
                    "low": [9.8],
                    "close": [10.1],
                    "vol": [1000],
                    "amount": [10000],
                }
            )
            df.to_parquet(data_dir / "000001.SZ.parquet", index=False)

            rows = list(iter_daily_frames(data_dir))

            self.assertEqual(len(rows), 1)
            ts_code, loaded = rows[0]
            self.assertEqual(ts_code, "000001.SZ")
            self.assertIn("amount", loaded.columns)

    def test_iter_daily_frames_accepts_common_us_symbol_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            for symbol in ["AAPL", "MSFT", "NVDA", "BRK-B", "BF-B"]:
                pd.DataFrame(
                    {
                        "symbol": [symbol],
                        "trade_date": ["2026-01-01"],
                        "open": [10.0],
                        "high": [10.2],
                        "low": [9.8],
                        "close": [10.1],
                        "volume": [1000],
                    }
                ).to_parquet(data_dir / f"{symbol}.parquet", index=False)

            rows = list(iter_daily_frames(data_dir))

            self.assertEqual([ts_code for ts_code, _ in rows], ["AAPL", "BF-B", "BRK-B", "MSFT", "NVDA"])


if __name__ == "__main__":
    unittest.main()
