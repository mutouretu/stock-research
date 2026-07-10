"""Dataset configuration contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DatasetConfig:
    dataset_id: str
    storage: str
    path: str
    entity_col: str
    time_col: str
    available_time_col: str | None = None
    columns: dict[str, str] = field(default_factory=dict)
    required_columns: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "DatasetConfig":
        required = ("dataset_id", "storage", "path", "entity_col", "time_col")
        missing = [name for name in required if not values.get(name)]
        if missing:
            raise ValueError(f"Dataset config is missing required fields: {missing}")
        storage = str(values["storage"])
        supported = {"parquet", "csv", "parquet_by_entity"}
        if storage not in supported:
            raise ValueError(
                f"Unsupported dataset storage {storage!r}; expected one of {sorted(supported)}"
            )
        return cls(
            dataset_id=str(values["dataset_id"]),
            storage=storage,
            path=str(values["path"]),
            entity_col=str(values["entity_col"]),
            time_col=str(values["time_col"]),
            available_time_col=(
                str(values["available_time_col"])
                if values.get("available_time_col") is not None
                else None
            ),
            columns={str(key): str(value) for key, value in (values.get("columns") or {}).items()},
            required_columns=tuple(str(value) for value in (values.get("required_columns") or [])),
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "DatasetConfig":
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as handle:
            values = yaml.safe_load(handle)
        if not isinstance(values, dict):
            raise ValueError(f"Dataset config must contain a YAML mapping: {config_path}")
        return cls.from_dict(values)
