# Stock Pattern Search

通用选股挖掘与策略搜索工程。

当前工程已经从单一 `type-n` 实验演进为通用的机器学习选股搜索框架：底层保留统一的数据协议、特征构造、tabular 模型训练、推理和结果检查能力；上层按策略隔离 pipeline、reviewer、配置和输出目录。现阶段主要生产链路是 Type-N 的 `burst_hold_pullback`，同时保留 `new_high`、`type_v`、`w_bottom` 等策略空间。

## 当前定位

- 提供通用二分类选股样本协议：`sample_id + ts_code + asof_date + label`。
- 支持 `logistic_regression`、`lightgbm`、`xgboost` 的统一训练、保存、加载和对比。
- 支持策略级 pipeline 隔离，避免不同策略的规则、reviewer 和输出互相污染。
- 支持 Type-N 两阶段选股：
  - Phase 1：短窗口放量突破 / 爆量启动入池。
  - Phase 2：`burst_hold_pullback` 回踩过滤，重点看放量维持、回撤深度和振幅收缩。
- 支持 Phase 1 缓存，便于按日或按月做回测时复用入池结果。
- 支持 A 股实盘日线与美股共享日线目录的截面扫描实验。

## 策略隔离

代码按策略放在一级目录下，公共能力放在 `common` 或基础 pipeline 中：

```text
src/
├── pipelines/
│   ├── type_n/              # Type-N 两阶段任务和 phase tracking
│   ├── new_high/            # New-high 策略入口
│   ├── type_v/              # Type-V 策略入口
│   ├── w_bottom/            # W 底长底突破训练和最新截面推理
│   ├── build_dataset.py     # 通用样本构造
│   ├── train_model.py       # 通用模型训练
│   └── run_scan.py          # 通用模型扫描
├── reviewers/
│   ├── common/              # 通用 reviewer 组件
│   ├── type_n/              # Type-N reviewer
│   │   ├── phase1_breakout/
│   │   └── phase2_pullback/
│   ├── new_high/
│   ├── type_v/
│   ├── w_bottom/
│   └── _recycle/            # 历史兼容/回收代码
├── data/
├── features/
├── inference/
├── models/
└── training/
```

配置和产物也按策略分区：

```text
configs/
├── common/                  # 通用 baseline 配置
├── type_n/                  # Type-N 训练配置
│   ├── phase1_breakout/
│   └── phase2_pullback/
├── new_high/
├── local_runs/              # 临时和实盘运行配置，保留复现上下文
└── archive/

outputs/
├── models/
│   ├── common/
│   ├── type_n/
│   ├── new_high/
│   ├── type_v/
│   └── w_bottom/
├── predictions/
│   ├── common/
│   ├── type_n/
│   ├── new_high/
│   ├── type_v/
│   └── w_bottom/
└── analysis/
```

旧入口文件仍保留 wrapper，便于历史命令兼容；新增代码优先放入策略目录。

## 环境安装

### 新工作区中的数据路径

本项目现位于统一仓库的 `research/pattern/stock-pattern-search/`。共享数据的规范位置是仓库根目录下的 `storage/shared_data/`；从本项目目录访问时对应 `../../../storage/shared_data/`。

文档和代码中原有的 `../shared_data/...` 默认值暂时保留，以维持旧独立仓库及兼容软链接下的行为。本阶段没有机械替换路径；后续路径切换应作为独立任务完成。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

在统一 `stock-research` 仓库中开发时，安装本项目及其本地公共 ML core：

```bash
pip install -r requirements-monorepo.txt
```

当前通用 binary metrics 已切换到 `research-ml-core`；daily/labels validator 的必需字段存在性检查
已通过兼容 wrapper 使用 `research-data-core`；`add_basic_indicators` 的 returns 和 rolling mean
已通过列名兼容层使用 `research-ml-core`。历史窗口和共享数据默认路径已使用
`research-data-core`；logistic/LightGBM/XGBoost wrappers 和 Trainer 的 fit/score 已使用
`research-ml-core`。交易单位、OHLCV、单股票 loader、artifact orchestration 和策略特征仍保留
在本项目。

## Type-N 主链路

Type-N 当前推荐使用拆分任务执行，便于缓存 Phase 1，并在不同日期复用同一段入池结果。

### 1. 构建 Phase 1 缓存

```bash
python scripts/run_type_n_task.py phase1-cache \
  --start-date 2026-03-01 \
  --end-date 2026-03-31 \
  --phase1-top-n 20 \
  --raw-daily-dir ../shared_data/raw/daily/parquet_daily_cache_20241001_20260707 \
  --phase1-reviewer-config configs/local_runs/phase1_short_burst_strength_2026-03-02.yaml \
  --output-path outputs/cache/phase1_short_burst_strength_2026-03.csv \
  --status-path outputs/cache/status/phase1_short_burst_strength_2026-03.json
```

Phase 1 是按 anchor date 选出爆量突破候选。做回测时，目标日的 Phase 2 通常只看目标日前若干交易日的 Phase 1 命中。

### 2. 从缓存跑 Phase 2 区间

```bash
python scripts/run_type_n_cached_range.py \
  --start-date 2026-03-02 \
  --end-date 2026-03-31 \
  --phase1-cache-path outputs/cache/phase1_short_burst_strength_2026-03.csv \
  --raw-daily-dir ../shared_data/raw/daily/parquet_daily_cache_20241001_20260707 \
  --phase2-reviewer-config configs/local_runs/phase2_volume_hold_compact_strong_volume_2026-05-28.yaml \
  --anchor-lookback-days 5 \
  --output-dir outputs/predictions/type_n/type_n_short_burst_strength_2026-03
```

核心输出：

- `outputs/predictions/type_n/<run_name>/<date>/<date>_final_candidates.csv`
- `outputs/predictions/type_n/<run_name>/<date>/<date>_matrix_top20_tscode.csv`
- `outputs/predictions/type_n/<run_name>/<date>/<date>_matrix_top20_stock_code.csv`
- `outputs/predictions/type_n/<run_name>/watchlists/<date>_top30_for_ths.csv`
- `outputs/predictions/type_n/<run_name>/watchlists/<date>_top30_stock_codes_only.csv`

### 3. 单日拆分调试

需要定位某一天的各阶段结果时，可以拆开执行：

```bash
python scripts/run_type_n_task.py phase1-scan ...
python scripts/run_type_n_task.py build-pool ...
python scripts/run_type_n_task.py phase2-filter ...
python scripts/run_type_n_task.py merge-final ...
python scripts/run_type_n_task.py report ...
```

查看完整参数：

```bash
python scripts/run_type_n_task.py --help
python scripts/run_type_n_cached_range.py --help
```

## 通用 ML Baseline

通用 baseline 仍可用于新的策略样本快速训练和比较：

```bash
python scripts/generate_richer_mock_data.py
python scripts/check_data_contract.py
python src/pipelines/build_dataset.py --config configs/common/data.yaml

python src/pipelines/train_model.py --config configs/common/train.yaml
python src/pipelines/train_model.py --config configs/common/train_lgbm.yaml
python src/pipelines/train_model.py --config configs/common/train_xgb.yaml

python src/pipelines/run_scan.py --config configs/common/infer.yaml
python src/pipelines/run_scan.py --config configs/common/infer_lgbm.yaml
python src/pipelines/run_scan.py --config configs/common/infer_xgb.yaml
```

模型对比：

```bash
python scripts/compare_models.py \
  --pred-a-path outputs/models/common/baseline_lgbm/valid_predictions.csv \
  --pred-b-path outputs/models/common/baseline_xgb/valid_predictions.csv \
  --name-a lgbm \
  --name-b xgb \
  --top-n 10 \
  --output-json outputs/analysis/compare_valid_lgbm_vs_xgb.json
```

## W 底长底突破

W 底策略使用 `market_pattern_labeler` 生成的长底突破标签，并基于共享美股日线 parquet 训练 tabular baseline。

```bash
python src/pipelines/w_bottom/train_long_base_breakout_baseline.py \
  --labels-path ../market_pattern_labeler/outputs/w_bottom/labels/labels_long_base_breakout.csv \
  --daily-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --output-dir outputs/models/w_bottom/long_base_breakout_baseline \
  --models logistic_regression lightgbm xgboost
```

最新截面推理：

```bash
python src/pipelines/w_bottom/run_long_base_latest_ensemble.py \
  --daily-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --model-root outputs/models/w_bottom/long_base_breakout_baseline/models \
  --output-dir outputs/predictions/w_bottom/latest_ensemble
```

主要产物：

- `outputs/models/w_bottom/long_base_breakout_baseline/model_metrics.json`
- `outputs/models/w_bottom/long_base_breakout_baseline/evaluation_report.md`
- `outputs/predictions/w_bottom/latest_ensemble/latest_universe_predictions.csv`
- `outputs/predictions/w_bottom/latest_ensemble/latest_universe_candidates.csv`
- `outputs/predictions/w_bottom/latest_ensemble/latest_universe_report.md`

## 数据协议

### 日线数据

默认支持按股票拆分的 parquet 日线目录：

- A 股示例：`../shared_data/raw/daily/parquet_daily_cache_YYYYMMDD_YYYYMMDD`
- 美股示例：`../shared_data/us/raw/daily/parquet_by_symbol`

常用列：

- 必需：`trade_date, open, high, low, close, vol`
- 可选：`amount, turnover_rate, pct_chg`

### 标签数据

通用训练标签推荐字段：

- `sample_id`
- `ts_code`
- `asof_date`
- `label`
- `label_source`
- `confidence`

约定：

- `sample_id` 格式：`{ts_code}_{YYYY-MM-DD}`
- `label` 为二分类 `0/1`
- 训练特征只能使用 `asof_date` 当天及之前的数据
- future return 只能作为诊断字段，不能进入训练特征

## 产物说明

### build_dataset 输出

- `data/processed/sample_meta.parquet`
- `data/processed/X_tabular.parquet`
- `data/processed/y.npy`
- `data/processed/X_sequence.npy`（可选）

### train_model 输出

- `outputs/models/<strategy>/<model_name>/model.pkl`
- `outputs/models/<strategy>/<model_name>/model_meta.json`
- `outputs/models/<strategy>/<model_name>/normalizer.pkl`
- `outputs/models/<strategy>/<model_name>/metrics.json`
- `outputs/models/<strategy>/<model_name>/valid_predictions.csv`

### scan 输出

- `outputs/predictions/<strategy>/<run_name>/*.csv`
- `outputs/predictions/<strategy>/<run_name>/*.md`

## 测试

```bash
python -m pytest
```

Type-N 相关结构和任务测试：

```bash
python -m pytest tests/test_type_n_tasks.py tests/test_phase_tracking.py tests/test_reviewers_structure.py
```
