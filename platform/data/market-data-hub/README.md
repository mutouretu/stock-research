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

## CF cycle-research Milestone 1

The first public-source ingestion slice for CF Industries is configured in
`configs/recipes/cf_m1.yaml`. The recipe orchestrates reusable modules under commodity,
agriculture, fundamentals, and company-operations domains; it is not itself a data domain.
It currently supports:

- CF daily prices from Yahoo Chart;
- Henry Hub daily spot prices through the FRED-hosted EIA series;
- World Bank Pink Sheet monthly urea prices;
- CF Industries SEC Company Facts.
- corn and soybean continuous futures from Yahoo Chart;
- USDA ERS corn and soybean cost-and-return files;
- USDA NASS national planted acreage when `NASS_API_KEY` is configured.

Run all configured sources:

```bash
export SEC_USER_AGENT="Your Name your.email@example.com"
export NASS_API_KEY="your-free-quick-stats-key"
python -m market_data_hub.cli download-cf-m1-data --config configs/recipes/cf_m1.yaml
```

The CF Milestone 1 pipeline also archives SEC 8-K earnings-release HTML exhibits and
normalizes quarterly product selling prices, sales volumes, production volumes, and
realized production natural-gas cost. SEC access requires `SEC_USER_AGENT` in the
environment; raw exhibits and their SHA-256 manifest are retained for auditability.

Run selected sources by repeating `--source`:

```bash
python -m market_data_hub.cli download-cf-m1-data \
  --config configs/recipes/cf_m1.yaml \
  --source cf_price \
  --source henry_hub \
  --source world_bank_urea
```

The SEC requires a descriptive user agent with contact information. The value is read from
`SEC_USER_AGENT` and must not be committed to the repository.

USDA NASS Quick Stats requires a free API key. Store it in `NASS_API_KEY`; do not put it directly
in `configs/recipes/cf_m1.yaml`. Historical AMS fertilizer prices are downloaded from the public
PDF archive and do not require a MyMarketNews API key.

### AMS 3195 public PDF archive

The Illinois Production Cost Report PDFs can be archived without a MyMarketNews account or API
key. The downloader checks the stable latest-report URL and discovers historical documents through
the public file repository:

```bash
python scripts/download_ams_3195_pdfs.py
```

Useful options:

```bash
python scripts/download_ams_3195_pdfs.py --latest-only
python scripts/download_ams_3195_pdfs.py --max-pages 5
python scripts/download_ams_3195_pdfs.py --output /custom/archive/path
```

Files are stored under `storage/shared_data/commodities/ams_3195/raw/`. `manifest.json` records
the final source URL, report date, SHA-256 digest, size, and retrieval time. Repeated runs skip
documents already present. Archive discovery failures are reported as warnings while preserving
the stable latest-report download.

Parse the archived PDFs into normalized ammonia, urea, UAN 28%, and UAN 32% prices:

```bash
python scripts/parse_ams_3195_fertilizer.py
```

The normalized dataset is written to
`storage/shared_data/commodities/ams_3195/fertilizer_prices.parquet`. It retains the reported low,
high, and average distributor prices, report and availability dates, source document, extraction
layout, and document digest.

Normalized outputs are written under the repository-level `storage/shared_data/` directory. A
failed or empty download does not overwrite an existing Parquet dataset.

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
