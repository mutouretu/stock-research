# Type-N 全流程极简交接

## 需要拿到的东西

1. 代码仓库：

```bash
git clone git@gitee.com:type-n/build-daily-cache.git
git clone git@gitee.com:type-n/market_pattern_labeler.git
git clone git@gitee.com:type-n/type_n_search.git
```

2. 数据目录：

```text
shared_data/raw/daily/parquet_daily_cache
```

3. 模型包：

```text
type_n_models_20260512.tar.gz
```

解压到 `type_n_search` 根目录：

```bash
cd type_n_search
tar -xzf ../type_n_models_20260512.tar.gz
```

4. TuShare token：

在 `build-daily-cache/.env` 放：

```bash
TUSHARE_TOKEN=你的token
```

## 本地目录结构

建议放成这样：

```text
type_n/
  build-daily-cache/
  market_pattern_labeler/
  type_n_search/
  shared_data/
    raw/daily/parquet_daily_cache/
```

## 让 Codex 本地跑

进入 `type_n` 根目录，直接让 Codex 执行：

```text
检查三个仓库依赖是否可用，然后用 shared_data/raw/daily/parquet_daily_cache，
在 type_n_search 里跑 2026-05-12 的 phase1+phase2 选股。
phase1 从 2026-04-27 开始回看，使用 configs/local_runs/phase_tracking_2026-05-12_from_2026-04-27_top20.yaml。
然后使用 configs/local_runs/review_candidates_phase2_pool_ma120_trend_soft_2026-05-12.yaml 做 MA120 趋势加权 review。
最后把前 30 名结果列出来。
```

## 每日增量

每天收盘后让 Codex 执行：

```text
在 build-daily-cache 里读取 .env 的 TUSHARE_TOKEN，下载最新交易日的日线数据。
然后把新增 parquet 合并进 shared_data/raw/daily/parquet_daily_cache，
只维护这一组 daily cache。
最后在 type_n_search 里跑当天的 phase1+phase2 选股和 MA120 review。
```

## 当前主要输出

```text
type_n_search/outputs/predictions/phase_tracking/
type_n_search/outputs/predictions/review/
```

最常看的文件：

```text
type_n_search/outputs/predictions/review/phase2_pool_ma120_trend_soft_2026-05-12/review_candidates.csv
```

## 历史目录说明

`shared_data/raw/daily/parquet_daily_cache_5-12` 和 `shared_data/raw/daily/parquet_daily_cache_4-24` 是历史阶段目录名，不再作为默认运行目录。当前约定只维护：

```text
shared_data/raw/daily/parquet_daily_cache
```
