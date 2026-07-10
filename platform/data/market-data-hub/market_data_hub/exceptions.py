"""Project-specific exceptions."""


class MarketDataHubError(Exception):
    """Base exception for market-data-hub."""


class UnsupportedDataSourceError(MarketDataHubError):
    """Raised when a configured data source is not supported."""


class UnsupportedStorageBackendError(MarketDataHubError):
    """Raised when a configured storage backend is not supported."""


class DataDownloadError(MarketDataHubError):
    """Raised when a configured data download cannot produce usable rows."""
