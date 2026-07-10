"""Instrument-level research configuration."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class InstrumentConfig:
    instrument: str
    name: str
    domain: str
    entity: dict[str, Any]
    drivers: dict[str, list[str]]
    features: dict[str, Any]
    targets: tuple[str, ...]

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "InstrumentConfig":
        required = ("instrument", "name", "domain", "entity", "drivers", "features", "targets")
        missing = [field for field in required if not values.get(field)]
        if missing:
            raise ValueError(f"Instrument config is missing required fields: {missing}")
        return cls(
            instrument=str(values["instrument"]),
            name=str(values["name"]),
            domain=str(values["domain"]),
            entity=dict(values["entity"]),
            drivers={str(key): list(value) for key, value in values["drivers"].items()},
            features=dict(values["features"]),
            targets=tuple(str(value) for value in values["targets"]),
        )


def load_instrument_config(path: str | Path) -> InstrumentConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        values = yaml.safe_load(handle)
    if not isinstance(values, dict):
        raise ValueError(f"Instrument config must contain a YAML mapping: {config_path}")
    return InstrumentConfig.from_dict(values)
