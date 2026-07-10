from pathlib import Path

from research_data_core.data import DatasetCatalog, DatasetConfig


def test_config_and_catalog_load_yaml(tmp_path: Path) -> None:
    path = tmp_path / "sample.yaml"
    path.write_text(
        """dataset_id: sample.one
storage: csv
path: sample.csv
entity_col: item_id
time_col: event_time
available_time_col: null
columns: {value: source_value}
required_columns: [item_id, event_time]
""",
        encoding="utf-8",
    )
    config = DatasetConfig.from_yaml(path)
    catalog = DatasetCatalog(tmp_path)
    assert config.columns == {"value": "source_value"}
    assert catalog.list_dataset_ids() == ["sample.one"]
    assert catalog.get("sample.one") == config
