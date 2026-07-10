import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market_pattern_labeler.pipelines.run_miner import run_miner


def _steady_uptrend_frame() -> pd.DataFrame:
    close = [10.0 + i * 0.06 for i in range(220)]
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


def test_run_miner_uses_dataclass_defaults_when_config_is_omitted(tmp_path: Path) -> None:
    data_dir = tmp_path / "daily"
    data_dir.mkdir()
    _steady_uptrend_frame().to_parquet(data_dir / "000001.SZ.parquet", index=False)
    output_csv = tmp_path / "steady_uptrend.csv"

    out = run_miner(
        data_dir=str(data_dir),
        output_csv=str(output_csv),
        miner_name="steady_uptrend",
    )

    assert output_csv.exists()
    assert len(out) > 0
    assert len(out) <= 8000
    assert (out["label"] == 0).all()
    assert (out["miner_name"] == "steady_uptrend").all()
