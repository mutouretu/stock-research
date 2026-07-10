# market-data-hub

`market-data-hub` is a cross-market raw data ingestion and normalization project for the
upper-level `stock-research` workspace.

It owns market data collection, instrument master data, trading calendars, corporate actions,
price cleaning, and standardized local exports. It does not own strategy logic, factor mining,
machine learning training, stock scoring, watchlist generation, or backtesting.

## Current Scope

Phase one focuses on US equities and now includes the CN A-share Tushare daily cache
pipeline:

- configuration-driven symbol universe
- Yahoo Chart daily OHLCV download
- Tushare CN daily increment download
- adjusted close preservation
- minimal instrument master data
- corporate action export for dividends and splits
- local Parquet storage
- daily update and full refresh jobs

The adapter layer is prepared for later Polygon, Tiingo, and other data sources.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configure

Edit `configs/us.yaml`:

```yaml
market: US
default_source: yahoo_chart

storage:
  backend: parquet
  root_dir: data

universe:
  symbols:
    - AAPL
    - MSFT

download:
  start_date: "2015-01-01"
  end_date: null
  interval: "1d"

downstream_requirements:
  consumers:
    - market_pattern_labeler
    - type_n_search
  preferred_start_date: "2015-01-01"
  min_history_days: 2520
  use_cases:
    - w_bottom_labeling
    - long_term_pattern_mining
    - trend_recovery_scan
  w_bottom_windows:
    short: 120
    medium: 252
    long: 504
```

API keys are not stored in code. The default US source is `yahoo_chart`, which does not require an
API key. Future paid adapters should read credentials from environment variables or external secret
managers.

## Commands

```bash
python -m market_data_hub.cli download-us-instruments --config configs/us.yaml
python -m market_data_hub.cli download-us-prices --config configs/us.yaml
python -m market_data_hub.cli download-us-corporate-actions --config configs/us.yaml
python -m market_data_hub.cli us-full-refresh --config configs/us.yaml
python -m market_data_hub.cli us-daily-update --config configs/us.yaml
python -m market_data_hub.cli validate-us-prices
python -m market_data_hub.cli export-us-daily-by-symbol
python -m market_data_hub.cli download-cn-prices --config configs/cn.yaml
python -m market_data_hub.cli merge-cn-daily-increment --help
python -m market_data_hub.cli cn-daily-update --help
```

Use `configs/us_russell1000.yaml` to download a Russell 1000-style universe:

```bash
python -m market_data_hub.cli download-us-prices --config configs/us_russell1000.yaml
python -m market_data_hub.cli validate-us-prices
python -m market_data_hub.cli export-us-daily-by-symbol
```

Expected outputs:

```text
data/processed/us/instruments/instruments.parquet
data/processed/us/prices_daily/prices.parquet
data/processed/us/corporate_actions/corporate_actions.parquet
```

## Data Validation and Downstream Export

After downloading US daily prices, validate the normalized big table:

```bash
python -m market_data_hub.cli validate-us-prices \
  --input data/processed/us/prices_daily/prices.parquet \
  --report reports/us_prices_validation_report.md
```

Then export the big table into one parquet file per symbol:

```bash
python -m market_data_hub.cli export-us-daily-by-symbol \
  --input data/processed/us/prices_daily/prices.parquet \
  --output ../shared_data/us/raw/daily/parquet_by_symbol \
  --min-rows 500
```

The `../shared_data` paths in this document are retained for compatibility during the staged
migration. In the new `stock-research` workspace, shared data will ultimately live at
`storage/shared_data`; the code and command-path switch is deferred to the shared-data migration
phase.

Default input:

```text
data/processed/us/prices_daily/prices.parquet
```

Default output:

```text
../shared_data/us/raw/daily/parquet_by_symbol
```

The exported files are designed for both downstream projects:

```text
market_pattern_labeler
type_n_search
```

Each per-symbol parquet file contains both US-style and A-share-style compatible fields:

```text
trade_date
open
high
low
close
vol
volume
adj_close
ts_code
symbol
market
```

`ts_code` is set to `symbol`, and `vol` is copied from `volume`. `market-data-hub` only
validates and exports data. It does not perform W-bottom detection, labeling, model training,
ranking, watchlist generation, or backtesting.

## Relationship With stock-research

`market-data-hub` is the data-ingestion module of the unified workspace. Upper-level research
projects consume its standardized datasets for feature engineering, model training, scoring,
watchlists, and backtesting.

## CN A-share Daily Cache

CN data uses Tushare. Tokens are not stored in the repository; set the environment variable
configured in `configs/cn.yaml`:

```bash
export TUSHARE_TOKEN=...
```

Download a flat daily increment:

```bash
python -m market_data_hub.cli download-cn-prices \
  --config configs/cn.yaml \
  --start-date 20260708 \
  --end-date 20260708 \
  --output data/processed/cn/increments/daily_increment_20260708.parquet \
  --failed-dates-output data/processed/cn/failed_dates/failed_trade_dates_20260708.json
```

Merge the increment into the shared per-symbol snapshot used by downstream projects:

```bash
python -m market_data_hub.cli merge-cn-daily-increment \
  --base-dir ../shared_data/raw/daily/parquet_daily_cache_20241001_20260707 \
  --increment data/processed/cn/increments/daily_increment_20260708.parquet \
  --output-dir ../shared_data/raw/daily/parquet_daily_cache_20241001_20260708
```

Or run download and merge as one daily update:

```bash
python -m market_data_hub.cli cn-daily-update \
  --config configs/cn.yaml \
  --start-date 20260708 \
  --end-date 20260708 \
  --base-dir ../shared_data/raw/daily/parquet_daily_cache_20241001_20260707 \
  --output-dir ../shared_data/raw/daily/parquet_daily_cache_20241001_20260708
```

Long-lived CN data assets belong under `../shared_data/raw/daily/`. The flat increment files under
`data/processed/cn/increments/` are temporary daily process data and can be removed after a
successful merge. Historical large flat caches can be archived under:

```text
../shared_data/raw/daily/flat_cache_archive/
```

## Roadmap

- complete full US ticker master data from an exchange or paid source
- add Polygon and Tiingo production adapters
- continue expanding CN and HK pipelines
- partition Parquet outputs by date for large datasets
- add data quality checks and repair reports
- add trading calendar providers
