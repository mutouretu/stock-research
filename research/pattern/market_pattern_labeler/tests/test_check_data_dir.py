from pathlib import Path

import pandas as pd
import pytest

from market_pattern_labeler.pipelines.check_data_dir import check_data_dir


def test_check_data_dir_reports_parquet_summary(tmp_path: Path) -> None:
    data_dir = tmp_path / "daily"
    data_dir.mkdir()
    frame = pd.DataFrame(
        {
            "trade_date": ["2026-01-02", "2026-01-03"],
            "open": [10.0, 10.5],
            "high": [10.6, 10.8],
            "low": [9.9, 10.1],
            "close": [10.4, 10.7],
            "vol": [1000, 1100],
            "ts_code": ["AAPL", "AAPL"],
        }
    )
    frame.to_parquet(data_dir / "AAPL.parquet", index=False)
    frame.assign(ts_code="MSFT").to_parquet(data_dir / "MSFT.parquet", index=False)

    summary = check_data_dir(data_dir, max_files=20)

    assert summary.total_files == 2
    assert summary.checked_files == 2
    assert summary.ok_files == 2
    assert summary.failed_files == 0
    assert summary.symbols_checked == 2
    assert summary.total_rows_checked == 4
    assert summary.min_rows_per_file == 2
    assert summary.max_rows_per_file == 2
    text = summary.summary_text()
    assert "data_dir_check_summary" in text
    assert "required_columns_status=ok" in text
    assert "missing_column_warnings=0" in text


def test_check_data_dir_raises_for_empty_directory(tmp_path: Path) -> None:
    data_dir = tmp_path / "daily"
    data_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="no parquet files found"):
        check_data_dir(data_dir)
