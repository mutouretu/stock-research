"""Catalog of YAML dataset definitions."""

from pathlib import Path

from research_data_core.data.dataset_config import DatasetConfig


class DatasetCatalog:
    def __init__(self, config_dir: str | Path):
        self.config_dir = Path(config_dir)
        self._datasets = self._load()

    def _load(self) -> dict[str, DatasetConfig]:
        if not self.config_dir.is_dir():
            raise FileNotFoundError(f"Dataset config directory does not exist: {self.config_dir}")
        datasets: dict[str, DatasetConfig] = {}
        paths = sorted((*self.config_dir.rglob("*.yaml"), *self.config_dir.rglob("*.yml")))
        for path in paths:
            config = DatasetConfig.from_yaml(path)
            if config.dataset_id in datasets:
                raise ValueError(f"Duplicate dataset_id {config.dataset_id!r} found at {path}")
            datasets[config.dataset_id] = config
        return datasets

    def get(self, dataset_id: str) -> DatasetConfig:
        try:
            return self._datasets[dataset_id]
        except KeyError as error:
            raise KeyError(f"Unknown dataset_id {dataset_id!r}") from error

    def list_dataset_ids(self) -> list[str]:
        return sorted(self._datasets)
