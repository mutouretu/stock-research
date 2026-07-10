# Phase 2.5：验证 market-data-hub 功能可用性与 build-daily-cache 覆盖情况

验证日期：2026-07-10

## 1. 版本与范围

- 新仓库 commit（验证开始时）：`3089cf8`
- market-data-hub 上游来源：`https://github.com/mutouretu/market-data-hub`
- 上游 `main` 同步基准：`b2c19a09367773a6e42b3344b7ffe8e762b0a2f7`
- 模块路径：`platform/data/market-data-hub/`
- Python package：`market_data_hub`
- 项目版本：`0.1.0`

本阶段只运行验证并记录结论；没有修改 hub 业务逻辑，没有迁移 `shared_data`，也没有修改或删除父目录旧项目。

## 2. 基础状态复查

检查结果：

- `platform/data/market-data-hub/` 存在。
- 模块内没有嵌套 `.git/`。
- Git 管理范围内没有 `data/`、`reports/`、parquet、CSV、SQLite 或 DuckDB 产物。
- `pyproject.toml` package discovery 仍为 `include = ["market_data_hub*"]`。
- CLI script 仍为 `market-data-hub = market_data_hub.cli:main`。
- `.venv`、`__pycache__`、`.pytest_cache` 和 editable-install 元数据均被 ignore，不进入提交。

## 3. 基础验证

在 `platform/data/market-data-hub/` 运行：

| 验证 | 结果 |
|---|---|
| `python3 -m compileall -q .` | 通过，退出码 0 |
| `.venv/bin/python -m pytest -q` | 通过，`16 passed in 0.50s` |
| package import | 通过，`market_data_hub.__version__ == "0.1.0"` |
| `.venv/bin/market-data-hub --help` | 通过，退出码 0；US/CN 命令均出现 |

Phase 2.4 已完成 editable 安装；本阶段复用该本地、被忽略的 `.venv`。

## 4. US 最小流水线 smoke test

### 配置

所有输入和输出位于 `/private/tmp/stock-research-hub-smoke/`（对应用户要求的 `/tmp` 临时区域）：

- universe：`AAPL`、`MSFT`
- 日期：`2024-01-01` 至 `2024-01-31`
- source：`yahoo_chart`
- 临时配置：`/private/tmp/stock-research-hub-smoke/us_smoke.yaml`
- 输出根目录：`/private/tmp/stock-research-hub-smoke/us`

### 命令结果

| 命令 | 结果 |
|---|---|
| `download-us-instruments` | 通过；生成 2 个 instrument |
| `download-us-prices` | 通过；生成 42 行、2 个 symbol |
| `validate-us-prices` | 通过；0 缺失必需字段、0 重复、0 未排序 symbol、0 价格异常 |
| `export-us-daily-by-symbol --min-rows 1` | 通过；导出 AAPL、MSFT 两个 parquet，无跳过或失败 |

下载日期实际为 `2024-01-02` 至 `2024-01-31`，每个 symbol 21 行，符合该月交易日数量。主表包含 `symbol`、`market`、`trade_date`、OHLC、`volume`、`adj_close` 等字段；每股导出包含要求的：

```text
trade_date, open, high, low, close, volume, vol, symbol, ts_code, market
```

所有 parquet 均可读取。US smoke 输出总大小约 48 KiB，仅位于临时目录。

验证报告出现 1 类预期 warning：两个 symbol 的起始日期晚于 validator 默认期望的 `2015-01-01`。这是刻意使用 2024-01 短窗口造成，不是数据链路失败。

## 5. CN/Tushare smoke test

### 缺 token 行为

初次验证时进程环境中不存在 `TUSHARE_TOKEN`。单日命令正确以退出码 1 拒绝启动，核心错误文字为
`Missing Tushare token. Set TUSHARE_TOKEN or cn_daily.token.`，且未生成 increment parquet、
failed-trade-dates JSON 或其他半成品。

可用性缺口：缺 token 抛出的是 `ValueError`，而 CLI 只捕获 `MarketDataHubError`，所以用户会看到完整 traceback，而不是只有一行友好错误。该问题不影响“不产生半成品”的安全行为，本阶段按禁止事项不修改业务/CLI 逻辑。

### 真实单交易日下载

随后用户将本地 `.env` 放入父目录旧项目。该文件是单行裸 token，而非
`TUSHARE_TOKEN=...` 赋值；验证过程只在单个子进程中临时注入其值，未显示、复制、提交或写入新仓库。

运行日期：`20260708`。所有输出位于
`/private/tmp/stock-research-hub-smoke/cn_real_20260708/`。

结果：

```text
total_trade_dates: 1
rows: 4317
symbols: 4317
initial_failed_dates: 0
final_failed_dates: 0
```

- `daily_increment.parquet`：成功生成，约 9.4 MiB，可读取。
- `failed_trade_dates.json`：成功生成，内容为空对象，2 bytes。
- 日期只有 `20260708`。
- `(ts_code, trade_date)` 重复键为 0。
- 4,317 个 symbol 对应 4,317 行。
- `ts_code/trade_date/open/high/low/close/vol/amount` 字段全部存在且无空值。
- token 未写入日志或仓库。

## 6. CN 增量合并 smoke test

全部 fixture 和输出位于 `/private/tmp/stock-research-hub-smoke/cn_merge/`，总大小约 48 KiB。

fixture 覆盖：

- base 中已有 `000001.SZ` 的 `20240102`、`20240103`。
- increment 中含同一股票更新版 `20240103` 和新日期 `20240104`。
- increment 中含新股票 `600000.SH` 的 `20240104`。

### `merge-cn-daily-increment`

结果：

```text
base_symbols: 1
increment_symbols: 2
output_symbols: 2
output_rows: 4
failed_symbols: 0
```

- `000001.SZ.parquet`：3 行，日期按升序排列且唯一；重复的 `20240103` 保留 increment 新值。
- `600000.SH.parquet`：成功创建，1 行。
- 两个文件均可读取，并保留 `trade_date/open/high/low/close/vol/amount` 等下游字段。

### `export-cn-daily-by-symbol`

结果：2 个 symbol、3 行、0 失败；成功创建两个按股票 parquet，日期排序和去重均正确。

## 7. build-daily-cache 功能覆盖矩阵

父目录 `../build-daily-cache` 仅做只读检查。其工作树仍有一个既存的未跟踪本地资产 `tk.csv`；本阶段没有修改它。

| build-daily-cache 功能 | hub 是否覆盖 | hub 对应位置 | 是否验证 | 缺口 | 建议 |
|---|---|---|---|---|---|
| Tushare 拉取 A 股日线 | 覆盖 | `markets/cn/adapters/tushare.py`、`pipelines/download_prices.py` | 单元测试和真实单交易日下载均通过；4,317 行/股票 | 未发现核心缺口 | 可由 hub 接管；继续保护 token |
| 失败日期保存 | 覆盖 | `save_failed_trade_dates`、CN config/CLI output | 真实下载生成空对象 JSON；无 token 分支不产生半成品 | 尚未现场触发真实失败日期 | 保留 fake failure 测试；日常运行监控 JSON |
| 失败日期重试 | 覆盖 | `retry_failed_trade_dates`、`--retry-from-failed-dates` | 单元测试覆盖 fake endpoint failure | 未做真实网络失败重试 | 归档前可做受控失败/重试演练 |
| 增量 parquet 输出 | 覆盖 | `save_increment`、`download-cn-prices` | 真实单日 increment 成功生成并通过字段/重复键检查 | 未发现核心缺口 | 可由 hub 接管 |
| 增量合并到 per-symbol cache | 覆盖 | `merge_daily_increment.py`、CLI `merge-cn-daily-increment` | `/tmp` smoke 通过 | 无核心缺口 | 可由 hub 接管 |
| 字段标准化 | 核心覆盖 | `normalize_cn_daily_flat`、`CN_DAILY_COLUMNS` | 合成 smoke 通过；18 个日线字段清单与旧 `DEFAULT_DAILY_COLUMNS` 完全一致 | 旧 ingest 还会生成 labels/schema，这不属于纯字段标准化 | hub 数据输出可接管；labels/schema 另行处置 |
| `shared_data` 输出路径 | 部分覆盖 | CN/US export 默认值和 README | CLI 临时绝对路径验证通过 | 代码默认仍是 `../shared_data`，尚未切换 `storage/shared_data` | 在 Phase 3 做路径切换和消费者验证 |
| XLSX 标签转换 | 未覆盖 | 无 | 只读确认旧 `convert_xlsx_labels.py` 独有 | XLSX 读取、代码/日期/标签规范化、manifest 生成均缺失 | 归档前迁出并明确归属，不能随旧项目删除 |
| `tk.csv` 或本地资产处理 | 未覆盖 | 无 | 发现小型、未跟踪且疑似敏感的本地 token 资产；未复制 | 凭据/资产处置未定义 | 不提交；确认用途，若仍有效应安全迁入 secret 管理并考虑轮换 |
| `ingest_daily_data.py` | 部分覆盖 | hub CN export/merge 覆盖按股票 parquet | merge/export smoke 通过 | labels、schema、检查报告和 latest-label 生成未覆盖 | 拆分数据能力与研究标签能力后再归档 |
| `merge_daily_increment.py` | 覆盖 | hub `merge_daily_increment.py` | 合成 smoke 通过 | 无明显核心缺口 | 旧脚本可在资产迁出后归档 |
| pickle cache 兼容 | 未覆盖 | 无 | 静态对照 | hub 只以 parquet 为主，不支持旧 `.pkl` cache | 查明是否仍有消费者；无消费者后记录废弃决定 |
| custom input 历史资产 | 未覆盖（资产问题） | 无 | 只读盘点：26 parquet、32 JSON，约 299 MiB | 尚未决定保留、迁移或丢弃 | Phase 4 前建立资产清单、校验和与归档/删除决策 |

下载端点和过滤逻辑的静态对照显示 hub 已具备旧主程序的 `daily`、`daily_basic`、`cyq_perf`、`stk_factor_pro`、`stock_st`、`suspend_d`、`stock_basic`、`trade_cal`，以及北交所、新股、ST、停牌和总市值过滤能力。

## 8. 阶段决策

### Phase 3：允许进入

**可以进入 Phase 3：shared_data 路径迁移。**

依据：US 真实短窗口链路已跑通；CN per-symbol 增量合并/直接导出已用合成数据完整跑通；输出结构和核心字段满足下游要求。Phase 3 本身是路径与资产迁移，不要求先删除旧项目。

前置保护条件：迁移前记录约 24 GiB `shared_data` 的容量、文件数、Git ignore、消费者路径和回滚方案；在 Phase 3 中将 hub 默认/文档路径从 `../shared_data` 切换到 `storage/shared_data` 并复跑读取验证。

### Phase 4：暂不允许进入归档执行

**暂不进入 Phase 4 的实际归档/删除。** 可以开始制作归档准备清单，但不能删除 `build-daily-cache`。

阻塞原因：

1. XLSX 标签转换为旧项目独有能力，尚未迁出。
2. `ingest_daily_data.py` 的 labels/schema/latest-label 能力尚未明确归属。
3. pickle 兼容是否仍有消费者尚未确认。
4. 本地凭据文件和约 299 MiB 的历史 increment/failed-date 资产尚未安全处置。

## 9. 遗留问题

1. CN 缺 token 错误会打印 traceback，可在独立小任务中统一为 CLI 友好错误；本阶段未修改。
2. Phase 3 需要完成 `../shared_data` 到 `storage/shared_data` 的路径切换、数据完整性和消费者回归。
3. Phase 4 前必须迁出或明确废弃 XLSX/labels/schema/pickle 能力，并处置凭据与本地历史资产。

## 10. Git 与边界检查

- smoke test 所有产物均位于 `/private/tmp/stock-research-hub-smoke/`，没有复制回仓库。
- 新仓库 Git 范围没有新增 parquet、CSV、SQLite 或 DuckDB 文件。
- `../shared_data`、`../build-daily-cache`、`../stock-pattern-search`、`../market_pattern_labeler` 和 `../alpha_agent_system` 均仍存在且未被本阶段修改。
