from pathlib import Path

import pandas as pd

from research_data_core.data import DatasetConfig, DatasetLoader


def _config(storage: str, path: Path) -> DatasetConfig:
    return DatasetConfig(
        dataset_id=f"sample.{storage}",
        storage=storage,
        path=str(path),
        entity_col="item_id",
        time_col="event_time",
        columns={"value": "source_value"},
        required_columns=("item_id", "event_time", "source_value"),
    )


def test_loader_reads_csv_and_normalizes_fields(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    pd.DataFrame(
        {"item_id": ["a"], "event_time": ["2026-01-01"], "source_value": [3.0]}
    ).to_csv(path, index=False)
    frame = DatasetLoader(_config("csv", path)).load(normalize_entity_time=True)
    assert list(frame.columns) == ["entity_id", "time", "value"]


def test_loader_reads_bounded_parquet_directory(tmp_path: Path) -> None:
    directory = tmp_path / "entities"
    directory.mkdir()
    for index in range(2):
        pd.DataFrame(
            {"item_id": [index], "event_time": [index], "source_value": [index]}
        ).to_parquet(directory / f"{index}.parquet")
    frame = DatasetLoader(_config("parquet_by_entity", directory)).load(max_files=1)
    assert len(frame) == 1
    assert "value" in frame
