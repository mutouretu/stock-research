"""Resolve paths within the stock-research workspace."""

from __future__ import annotations

import os
from pathlib import Path


def _is_workspace_root(path: Path) -> bool:
    return (
        (path / "README.md").is_file()
        and (path / "platform").is_dir()
        and (path / "research").is_dir()
        and (path / "storage").is_dir()
    )


def find_stock_research_root(start: Path | None = None) -> Path:
    configured = os.environ.get("STOCK_RESEARCH_ROOT")
    if configured:
        root = Path(configured).expanduser().resolve()
        if not _is_workspace_root(root):
            raise FileNotFoundError(
                f"STOCK_RESEARCH_ROOT does not identify a stock-research root: {root}"
            )
        return root

    candidate = (start or Path.cwd()).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for path in (candidate, *candidate.parents):
        if _is_workspace_root(path):
            return path
    raise FileNotFoundError(
        f"Could not find stock-research root from {candidate}; set STOCK_RESEARCH_ROOT"
    )


def get_shared_data_dir(root: Path | None = None) -> Path:
    configured = os.environ.get("STOCK_RESEARCH_SHARED_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    workspace = root.expanduser().resolve() if root is not None else find_stock_research_root()
    return workspace / "storage" / "shared_data"


def resolve_repo_path(path: str | Path, root: Path | None = None) -> Path:
    value = Path(path).expanduser()
    if value.is_absolute():
        return value.resolve()
    workspace = root.expanduser().resolve() if root is not None else find_stock_research_root()
    return (workspace / value).resolve()


def resolve_shared_data_path(path: str | Path, root: Path | None = None) -> Path:
    value = Path(path).expanduser()
    if value.is_absolute():
        return value.resolve()
    return (get_shared_data_dir(root) / value).resolve()
