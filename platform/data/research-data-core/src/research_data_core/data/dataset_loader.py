"""Configuration-driven dataset loading."""

from pathlib import Path

import pandas as pd

from research_data_core.data.dataset_config import DatasetConfig
from research_data_core.io import read_csv, read_parquet, read_parquet_by_entity_dir
from research_data_core.paths import resolve_repo_path
from research_data_core.schema import normalize_columns, require_columns


class DatasetLoader:
    def __init__(self, config: DatasetConfig, root: Path | None = None):
        self.config = config
        self.root = root

    def load(
        self,
        *,
        max_files: int | None = None,
        max_rows: int | None = None,
        normalize_entity_time: bool = False,
        allow_full_scan: bool = False,
    ) -> pd.DataFrame:
        path = resolve_repo_path(self.config.path, self.root)
        if self.config.storage == "parquet":
            frame = read_parquet(path)
        elif self.config.storage == "csv":
            frame = read_csv(path)
        elif self.config.storage == "parquet_by_entity":
            frame = read_parquet_by_entity_dir(
                path,
                max_files=max_files,
                allow_full_scan=allow_full_scan,
            )
        else:
            raise ValueError(f"Unsupported dataset storage: {self.config.storage}")

        require_columns(frame, self.config.required_columns)
        source_to_canonical = {source: canonical for canonical, source in self.config.columns.items()}
        if source_to_canonical:
            frame = normalize_columns(frame, source_to_canonical)

        if normalize_entity_time:
            entity = source_to_canonical.get(self.config.entity_col, self.config.entity_col)
            time = source_to_canonical.get(self.config.time_col, self.config.time_col)
            normalized = {entity: "entity_id", time: "time"}
            if self.config.available_time_col is not None:
                available = source_to_canonical.get(
                    self.config.available_time_col,
                    self.config.available_time_col,
                )
                normalized[available] = "available_time"
            require_columns(frame, normalized)
            frame = normalize_columns(frame, normalized)

        if max_rows is not None:
            if max_rows < 0:
                raise ValueError("max_rows must be non-negative or None")
            frame = frame.head(max_rows)
        return frame
