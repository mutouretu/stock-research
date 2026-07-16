# CF Milestone 1 数据质量报告

- 数据审计日期：2026-07-16
- ERROR：0
- WARNING：1
- 尚未接入的 P0 来源：无

| Dataset | 状态 | 行数 | 起始日期 | 最新日期 |
|---|---:|---:|---:|---:|
| `cycle.cf.price` | PASS | 3403 | 2013-01-02 | 2026-07-15 |
| `commodity.henry_hub` | PASS | 7410 | 1997-01-07 | 2026-07-13 |
| `commodity.urea` | WARNING | 792 | 1960-01-01 | 2025-12-01 |
| `commodity.fertilizer_ams_3195` | PASS | 321 | 2022-09-22 | 2026-07-10 |
| `cycle.cf.sec_companyfacts` | PASS | 27212 | 2006-12-31 | 2026-05-04 |
| `cycle.cf.product_operations` | PASS | 834 | 2015-06-30 | 2026-03-31 |
| `crop.corn_soybean_futures` | PASS | 6820 | 2013-01-02 | 2026-07-16 |
| `crop.corn_costs_returns` | PASS | 5665 | 1996-12-31 | 2025-12-31 |
| `crop.soybean_costs_returns` | PASS | 6026 | 1997-12-31 | 2025-12-31 |
| `crop.planted_acres` | PASS | 106 | 2013-01-01 | 2026-01-01 |

## cycle.cf.price

路径：`storage/shared_data/us/raw/daily/parquet_by_symbol/CF.parquet`

关键字段缺失率：

- `symbol`：0.00%
- `trade_date`：0.00%
- `close`：0.00%
- `adj_close`：0.00%
- `volume`：0.00%
- `source`：0.00%

- 未发现质量问题。

## commodity.henry_hub

路径：`storage/shared_data/commodities/henry_hub.parquet`

关键字段缺失率：

- `series_id`：0.00%
- `observation_date`：0.00%
- `available_time`：0.00%
- `value`：0.00%
- `unit`：0.00%
- `source`：0.00%
- `retrieved_at`：0.00%

- 未发现质量问题。

## commodity.urea

路径：`storage/shared_data/commodities/urea.parquet`

关键字段缺失率：

- `series_id`：0.00%
- `observation_date`：0.00%
- `available_time`：0.00%
- `value`：0.00%
- `unit`：0.00%
- `source`：0.00%
- `retrieved_at`：0.00%

- **WARNING** `staleness`：最新数据距审计日 227 天，阈值为 75 天

## commodity.fertilizer_ams_3195

路径：`storage/shared_data/commodities/ams_3195/fertilizer_prices.parquet`

关键字段缺失率：

- `product`：0.00%
- `report_date`：0.00%
- `available_time`：0.00%
- `price_low`：0.00%
- `price_high`：0.00%
- `price_average`：0.00%
- `unit`：0.00%
- `source_document`：0.00%
- `sha256`：0.00%

- 未发现质量问题。

## cycle.cf.sec_companyfacts

路径：`storage/shared_data/fundamentals/us/CF/companyfacts.parquet`

关键字段缺失率：

- `ticker`：0.00%
- `concept`：0.00%
- `unit`：0.00%
- `value`：0.00%
- `period_end`：0.00%
- `filing_date`：0.00%
- `form`：0.00%
- `accession`：0.00%

- 未发现质量问题。

## cycle.cf.product_operations

路径：`storage/shared_data/fundamentals/us/CF/product_operations.parquet`

关键字段缺失率：

- `ticker`：0.00%
- `period_end`：0.00%
- `fiscal_year`：0.00%
- `fiscal_quarter`：0.00%
- `scope`：0.00%
- `product`：0.00%
- `metric`：0.00%
- `value`：0.00%
- `unit`：0.00%
- `filing_date`：0.00%
- `accession`：0.00%
- `source_url`：0.00%

- 未发现质量问题。

## crop.corn_soybean_futures

路径：`storage/shared_data/agriculture/crop_futures.parquet`

关键字段缺失率：

- `symbol`：0.00%
- `commodity`：0.00%
- `trade_date`：0.00%
- `close`：0.23%
- `adj_close`：0.23%
- `volume`：0.23%
- `unit`：0.00%
- `source`：0.00%

- 未发现质量问题。

## crop.corn_costs_returns

路径：`storage/shared_data/agriculture/ers_corn_costs_returns.parquet`

关键字段缺失率：

- `commodity`：0.00%
- `category`：0.00%
- `item`：0.00%
- `unit`：0.00%
- `region`：0.00%
- `year`：0.00%
- `value`：0.00%
- `available_time`：0.00%
- `source`：0.00%

- 未发现质量问题。

## crop.soybean_costs_returns

路径：`storage/shared_data/agriculture/ers_soybean_costs_returns.parquet`

关键字段缺失率：

- `commodity`：0.00%
- `category`：0.00%
- `item`：0.00%
- `unit`：0.00%
- `region`：0.00%
- `year`：0.00%
- `value`：0.00%
- `available_time`：0.00%
- `source`：0.00%

- 未发现质量问题。

## crop.planted_acres

路径：`storage/shared_data/agriculture/nass_planted_acres.parquet`

关键字段缺失率：

- `commodity`：0.00%
- `statistic`：0.00%
- `reference_period`：0.00%
- `year`：0.00%
- `value`：0.00%
- `unit`：0.00%
- `available_time`：0.00%
- `source`：0.00%

- 未发现质量问题。
