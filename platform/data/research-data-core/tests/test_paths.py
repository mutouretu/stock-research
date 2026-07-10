from pathlib import Path

from research_data_core.paths import find_stock_research_root, get_shared_data_dir


def test_find_current_workspace_root() -> None:
    root = find_stock_research_root(Path(__file__))
    assert (root / "platform").is_dir()
    assert (root / "research").is_dir()


def test_shared_data_environment_override(monkeypatch, tmp_path: Path) -> None:
    custom = tmp_path / "shared"
    monkeypatch.setenv("STOCK_RESEARCH_SHARED_DATA_DIR", str(custom))
    assert get_shared_data_dir() == custom.resolve()
