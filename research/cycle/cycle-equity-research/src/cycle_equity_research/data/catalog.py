"""Dataset contract catalog for cycle-equity research."""

from pathlib import Path

from research_data_core.data import DatasetCatalog


def load_dataset_catalog(config_dir: str | Path) -> DatasetCatalog:
    return DatasetCatalog(config_dir)
