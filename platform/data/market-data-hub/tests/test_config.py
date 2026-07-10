from market_data_hub.config import load_config


def test_load_us_config() -> None:
    config = load_config("configs/us.yaml")

    assert config.market == "US"
    assert config.default_source == "yahoo_chart"
    assert "AAPL" in config.universe.symbols
    assert config.storage.backend == "parquet"
    assert config.download.start_date == "2015-01-01"
    assert config.download.end_date is None
    assert config.download.interval == "1d"
    assert config.downstream_requirements.preferred_start_date == "2015-01-01"
    assert config.downstream_requirements.min_history_days == 2520
    assert "market_pattern_labeler" in config.downstream_requirements.consumers
    assert "type_n_search" in config.downstream_requirements.consumers
    assert "w_bottom_labeling" in config.downstream_requirements.use_cases
    assert config.downstream_requirements.w_bottom_windows == {
        "short": 120,
        "medium": 252,
        "long": 504,
    }
