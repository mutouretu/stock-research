# market_pattern_labeler

`market_pattern_labeler` 是一个独立的数据生产工具仓库，用于从股票日线数据中召回形态候选事件并导出 CSV，供人工复核。

> Monorepo migration note: this project now lives at
> `research/pattern/market_pattern_labeler/` in the unified `stock-research` workspace. Existing
> `../shared_data/...` command examples are retained for the legacy checkout, where the compatibility
> symlink still resolves them. When running from this migrated project directory, use the canonical
> monorepo path `../../../storage/shared_data/...` explicitly. A broad default-path rewrite is
> intentionally deferred to a separate task.

## 当前 V0 目标

当前只做一件事：

1. 读取按股票存储的 daily parquet 数据。
2. 运行硬编码规则 miner（当前包含 phase1 breakout、phase2 pullback 和几类负样本 miner）。
3. 导出结构化候选或样本 CSV。

不包含数据库、前端、标注导入、训练集构建与模型训练。

## 安装

```bash
cd market_pattern_labeler
python3 -m pip install -e .
```

如果只想快速运行，也可以不安装，直接使用：

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main --help
```

## 命令行示例

每个 miner 的默认参数写在对应 Python `Config` 类里，`--config` 是可选覆盖项。只有需要多套实验参数时才建议使用 YAML。

```bash
python3 -m market_pattern_labeler.cli.main run-miner \
  --miner bottom_rebound \
  --data-dir ../shared_data/raw/daily/parquet_daily_cache \
  --output outputs/type_v/bottom_rebound_candidates.csv
```

或安装后使用：

```bash
mplabeler run-miner \
  --miner steady_uptrend \
  --data-dir ../shared_data/raw/daily/parquet_daily_cache \
  --output outputs/type_v/steady_uptrend_candidates.csv
```

需要覆盖默认参数时再传 YAML，例如 `type_n` 的多套实验配置：

```bash
mplabeler run-miner \
  --miner type_n \
  --data-dir ../shared_data/raw/daily/parquet_daily_cache \
  --config configs/type_n/phase1_breakout/type_n_runup.yaml \
  --output outputs/type_n/phase1_breakout/type_n_candidates.csv
```

## 输入数据假设

- 输入是一个目录，目录下每个 parquet 文件代表一只股票。
- 文件名通常为 `ts_code.parquet`。
- 常见字段：
  - `trade_date`
  - `open`, `high`, `low`, `close`
  - `vol`, `amount`（可选）

读取器会：

- 优先使用 `trade_date` 做日期标准化和升序排序。
- 若数据内缺少 `ts_code` 但存在 `symbol`，则用 `symbol` 作为 `ts_code`。
- 若数据内缺少 `ts_code` 和 `symbol`，则从文件名推断。
- 若数据内缺少 `vol` 但存在 `volume`，则用 `volume` 生成 `vol`。
- 对重复 `trade_date` 做 warning，保留最后一条。
- 对单文件读错、字段缺失做 warning 并跳过，不中断全市场扫描。

## Using US Data From market-data-hub

`market-data-hub` can export US daily bars into per-symbol parquet files:

```text
../shared_data/us/raw/daily/parquet_by_symbol
```

Each file should contain:

```text
trade_date, open, high, low, close, vol
```

Additional compatible columns may include:

```text
symbol, ts_code, volume, adj_close, market
```

Check the exported directory:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main check-data-dir \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --max-files 20
```

Run an existing miner as a smoke test:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main run-miner \
  --miner type_n \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --config configs/type_n/type_n.yaml \
  --output outputs/type_n/phase1_breakout/us_type_n_candidates.csv
```

This repository only recalls candidate pattern events. It does not download raw market data and does
not train machine learning models.

## US W-Bottom Candidate Mining

After exporting US daily data from `market-data-hub`, check the parquet directory first:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main check-data-dir \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --max-files 20
```

Then mine W-bottom candidates:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main run-miner \
  --miner w_bottom \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --config configs/w_bottom/w_bottom.yaml \
  --output outputs/w_bottom/candidates/us_w_bottom_candidates.csv
```

`w_bottom` is a high-recall rule-based candidate generator. It searches recent windows for
`prior high -> left bottom -> neckline -> right bottom -> current close` structures and emits
`w_bottom_forming` or `w_bottom_breakout` candidates. It does not train a model and does not
produce trading advice.

## US Bottom Base Breakout Candidate Mining

`bottom_base_breakout` searches for stocks that went through a relatively long bottoming or
base-building phase and have recently broken above the middle peak / neckline of that base. It is
more general than a strict W-bottom pattern and can recall box bases, rounding bases, and complex
bottom consolidation patterns.

Run:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main run-miner \
  --miner bottom_base_breakout \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --config configs/w_bottom/bottom_base_breakout.yaml \
  --output outputs/w_bottom/candidates/us_bottom_base_breakout_candidates.csv
```

Visual review:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main plot-candidates \
  --candidates outputs/w_bottom/candidates/us_bottom_base_breakout_candidates.csv \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --output-dir outputs/w_bottom/charts/us_bottom_base_breakout \
  --top-n 200
```

Use `scan.mode: historical` to collect candidates from many historical periods instead of only the
latest market state. Historical mode scans multiple `asof_date` values per symbol and de-duplicates
nearby hits with `min_days_between_candidates`.

## US Long Base Breakout Candidate Mining

`long_base_breakout` focuses on longer base-building structures, with the default minimum base
duration set to roughly one trading year. It looks for a prior drawdown, repeated separated support
touches, a qualified neckline below the old high, enough right-side duration, and a fresh breakout.
The default config also enables a monthly trend filter, requiring a positive long-term monthly
trend before accepting the daily base breakout candidate.

Run the full US scan:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main run-miner \
  --miner long_base_breakout \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --config configs/w_bottom/long_base_breakout.yaml \
  --output outputs/w_bottom/candidates/us_long_base_breakout_candidates.csv
```

Debug selected symbols:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main run-miner \
  --miner long_base_breakout \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --config configs/w_bottom/long_base_breakout.yaml \
  --output outputs/w_bottom/debug/debug_oled_dell_long_base.csv \
  --symbols OLED,DELL
```

Generate charts:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main plot-candidates \
  --candidates outputs/w_bottom/candidates/us_long_base_breakout_candidates.csv \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --output-dir outputs/w_bottom/charts/us_long_base_breakout \
  --top-n 200
```

Generate a year-balanced review set to avoid over-sampling one market regime:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main plot-candidates \
  --candidates outputs/w_bottom/candidates/us_long_base_breakout_candidates.csv \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --output-dir outputs/w_bottom/charts/us_long_base_breakout_year_stratified200 \
  --top-n 200 \
  --sample year_stratified
```

Build training labels from long-base candidates:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main build-ml-labels \
  --positive-candidates outputs/w_bottom/candidates/us_long_base_breakout_candidates.csv \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --output outputs/w_bottom/labels/labels_long_base_breakout.csv \
  --negative-ratio 3 \
  --min-asof-date 2004-01-01 \
  --random-seed 42
```

This creates positive `rule_long_base_breakout` labels and three negative sources:
`random_non_event`, `downtrend_continuation`, and `weak_base_non_breakout`. Splits are assigned by
`asof_date` rather than randomly, with default cutoffs `train <= 2022-12-31`,
`valid <= 2024-12-31`, and later rows assigned to `test`. The command writes both
`outputs/w_bottom/labels/labels_long_base_breakout.csv` and `outputs/w_bottom/labels/labels_long_base_breakout_report.md`. Use
`--min-asof-date` to keep labels aligned with the usable historical range for downstream training;
the report includes daily parquet range, labels range, and per-symbol date-range validation.

The current shared US parquet directory is symbol-file based. If ETF symbols such as `SPY`, `QQQ`,
`IWM`, and `DIA` are absent from that directory, they need to be added during the upstream
`market-data-hub` download/export step before the labeler can mine ETF patterns.

## Visual Review for W-Bottom Candidates

After mining W-bottom candidates:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main run-miner \
  --miner w_bottom \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --config configs/w_bottom/w_bottom.yaml \
  --output outputs/w_bottom/candidates/us_w_bottom_candidates.csv
```

Generate charts for manual review:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main plot-candidates \
  --candidates outputs/w_bottom/candidates/us_w_bottom_candidates.csv \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --output-dir outputs/w_bottom/charts/us_w_bottom \
  --top-n 100
```

By default, charts use the first close above the neckline after the right bottom as the chart
anchor, then show about five years before that anchor and 90 trading days after it. This keeps the
view focused on the period just after the bottoming structure breaks out, instead of always slicing
back from the latest `asof_date`. To force the old as-of-date view, pass `--anchor asof`.

Filter breakout candidates:

```bash
PYTHONPATH=src python3 -m market_pattern_labeler.cli.main plot-candidates \
  --candidates outputs/w_bottom/candidates/us_w_bottom_candidates.csv \
  --data-dir ../shared_data/us/raw/daily/parquet_by_symbol \
  --output-dir outputs/w_bottom/charts/us_w_bottom_breakout \
  --stage w_bottom_breakout \
  --top-n 100
```

The tool writes chart PNG files, a simple `index.html`, and a `review.csv` file. The
`manual_review` and `review_note` columns can be filled manually during quality inspection.

## 输出 CSV 字段

当前输出字段如下：

- `sample_id`
- `ts_code`
- `asof_date`
- `label`
- `label_source`
- `confidence`
- `event_id`
- `miner_name`
- `candidate_score`
- `close`
- `ret_1d`
- `ret_3d`
- `vol_ratio_1d`
- `vol_ratio_3d`
- `base_window_days`
- `base_range_pct`
- `breakout_flag`
- `rule_flags`

`w_bottom` 会在上述基础字段之外额外输出：

- `window`
- `pattern_stage`
- `left_bottom_date`, `left_bottom_price`
- `middle_peak_date`, `neckline_price`
- `right_bottom_date`, `right_bottom_price`
- `current_close`
- `prior_high_date`, `prior_high_price`
- `bottom_similarity_pct`
- `middle_rebound_pct`
- `prior_drawdown_pct`
- `neckline_distance_pct`
- `volume_ratio_20`

前 6 列与 `labels_data_list` 对齐，方便人工审核后直接提取训练标签。

## 可用 miner

- `type_n`: 正样本候选召回
- `w_bottom`: 美股 W 底 forming / breakout 高召回候选召回
- `bottom_base_breakout`: 美股长期筑底 / 底部平台右侧刚突破候选召回
- `long_base_breakout`: 美股一年以上长周期筑底并刚突破的候选召回
- `bottom_rebound`: 150 个交易日窗口的阶段底部反弹候选召回
- `range_support_rebound`: Type-V positive，横盘支撑区触底后的温和反弹候选
- `steady_uptrend`: Type-V easy negative，持续上涨股
- `steady_downtrend`: Type-V easy negative，持续下跌股
- `downtrend_simple`: 明显下跌趋势负样本
- `weak_sideways`: 弱势横盘负样本
- `high_volatility_range`: 高波动震荡负样本
- `fake_breakout`: 看似突破但后续没有跟随
- `downtrend_rebound`: 下跌大趋势中的短期反抽
- `late_stage_acceleration`: 已经涨很多后的后段加速
- `volume_only_spike`: 只有量能脉冲、价格结构不成立

当前目录先按形态分组，再按形态内阶段组织：

- `miners/type_n/phase1_breakout/`
- `miners/type_n/phase2_pullback/`
- `miners/w_bottom/`
- `miners/type_v/positive/`
- `miners/type_v/negative_easy/`
- `miners/type_v/negative_hard/`（预留）

配置文件只保留有复用或实验价值的 YAML。当前保留：

- `configs/type_n/type_n.yaml`
- `configs/type_n/phase1_breakout/type_n_runup.yaml`
- `configs/type_n/phase1_breakout/type_n_runup_nocap.yaml`
- `configs/type_n/phase1_breakout/type_n_no_runup_nocap.yaml`
- `configs/type_n/phase2_pullback/pullback_fastdrop.yaml`
- `configs/w_bottom/w_bottom.yaml`
- `configs/w_bottom/bottom_base_breakout.yaml`
- `configs/w_bottom/long_base_breakout.yaml`

## type_n miner（V0）规则概述

`type_n` 用硬编码规则做“高召回候选生成”：

1. 前段整理：过去窗口振幅受限（`base_range_pct`）。
2. 近期启动：近 1 日/3 日收益达到阈值。
3. 放量：当日或近 3 日均量相对过去均量放大。
4. 突破：价格接近或突破过去窗口高点。
5. 规则命中越多，`candidate_score` 越高。

默认参数在 `TypeNConfig` 里；`configs/type_n/phase1_breakout/` 下只保留 runup / nocap 这类实验覆盖参数。

## 当前限制

- 当前只实现候选/样本召回 miner。
- 仅输出 candidates CSV，不做标注回收。
- 仅做离线批处理，不做服务化。
- 规则是可解释起点，不保证高精度。
