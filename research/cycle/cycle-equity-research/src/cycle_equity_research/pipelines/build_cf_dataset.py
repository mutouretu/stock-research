"""Planning-only CF dataset pipeline."""

from pathlib import Path

from cycle_equity_research.data import load_dataset_catalog


def describe_cf_dataset_build(config_dir: str | Path) -> list[str]:
    """Return dataset ids that a later CF dataset build will consume."""
    return load_dataset_catalog(config_dir).list_dataset_ids()
