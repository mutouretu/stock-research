from datetime import date
from pathlib import Path

import pandas as pd

from cycle_equity_research.quality.report import build_data_quality_report


def test_quality_report_passes_valid_dataset(tmp_path: Path) -> None:
    data_path = tmp_path / "dataset.parquet"
    pd.DataFrame(
        {
            "series_id": ["TEST", "TEST"],
            "observation_date": pd.to_datetime(["2026-07-01", "2026-07-02"]),
            "available_time": pd.to_datetime(["2026-07-02", "2026-07-03"]),
            "value": [1.0, 2.0],
            "unit": ["USD", "USD"],
        }
    ).to_parquet(data_path, index=False)
    config = tmp_path / "quality.yaml"
    config.write_text(
        f"""
subject: CF
milestone: 1
datasets:
  - dataset_id: test.series
    path: {data_path}
    date_col: observation_date
    available_time_col: available_time
    required_columns: [series_id, observation_date, available_time, value, unit]
    key_columns: [series_id, observation_date]
    expected_units: [USD]
    min_rows: 2
    max_staleness_days: 10
pending_p0_sources: []
""",
        encoding="utf-8",
    )

    report = build_data_quality_report(config, root=tmp_path, as_of=date(2026, 7, 5))

    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.datasets[0].status == "PASS"


def test_quality_report_flags_missing_file(tmp_path: Path) -> None:
    config = tmp_path / "quality.yaml"
    config.write_text(
        """
subject: CF
milestone: 1
datasets:
  - dataset_id: missing.series
    path: missing.parquet
    date_col: observation_date
pending_p0_sources: [source_a]
""",
        encoding="utf-8",
    )

    report = build_data_quality_report(config, root=tmp_path, as_of=date(2026, 7, 5))

    assert report.error_count == 1
    assert report.datasets[0].status == "ERROR"
    assert report.pending_p0_sources == ("source_a",)
