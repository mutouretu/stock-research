from pathlib import Path

from src.common.paths import get_shared_daily_dir, get_shared_us_daily_dir


def test_shared_daily_dir_honors_data_core_environment(monkeypatch, tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    monkeypatch.setenv("STOCK_RESEARCH_SHARED_DATA_DIR", str(shared))
    assert get_shared_daily_dir() == shared.resolve() / "raw/daily/parquet_daily_cache"
    assert get_shared_daily_dir("alternate") == shared.resolve() / "raw/daily/alternate"
    assert get_shared_us_daily_dir() == shared.resolve() / "us/raw/daily/parquet_by_symbol"


def test_shared_daily_dir_defaults_to_monorepo_storage(monkeypatch) -> None:
    monkeypatch.delenv("STOCK_RESEARCH_SHARED_DATA_DIR", raising=False)
    path = get_shared_daily_dir()
    assert path.parts[-4:] == ("shared_data", "raw", "daily", "parquet_daily_cache")
    assert path.parent.parent.parent.name == "shared_data"
