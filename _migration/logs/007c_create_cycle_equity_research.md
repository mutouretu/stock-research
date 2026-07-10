# Phase 7c - 创建 cycle-equity-research 周期股研究项目骨架

## 基本信息

- 创建日期：2026-07-11
- 项目路径：`research/cycle/cycle-equity-research/`
- project 名称：`cycle-equity-research`
- package 名称：`cycle_equity_research`
- 版本：`0.1.0`
- 第一目标标的：CF Industries (`CF`)

## 工程结构

项目参考 stock-pattern-search 的工程组织，包含：

- `configs/instruments/`：研究对象及需求声明
- `configs/datasets/`：research-data-core 兼容的数据集接口契约
- `configs/local_runs/`：预留本地运行配置，当前为空
- `scripts/`：配置检查、dataset contract 检查和规划型入口
- `src/cycle_equity_research/`：data、features、pipelines 及预留 models/reports/training
- `tests/`：package、CF config 和 dataset contract 测试
- `README.md` 与 `pyproject.toml`

本阶段没有修改 stock-pattern-search、market_pattern_labeler、market-data-hub、research-ml-core
或 research-data-core。仓库里既有的未跟踪
`_migration/backlog/research_data_core_stabilization.md` 由用户保留，本任务未修改或纳入提交范围。

## CF 配置

`configs/instruments/CF.yaml` 声明：

- equity entity：CF / US
- 领域：nitrogen fertilizer
- commodity drivers：urea、ammonia、UAN
- cost driver：Henry Hub gas
- demand drivers：corn、soybean、planted acres
- financial drivers：revenue、EBITDA、gross margin、sales volume、inventory
- valuation directions：EV/EBITDA、FCF yield、dividend yield
- feature directions：nitrogen/gas spreads、20/60/120 momentum、seasonality
- target directions：3m/6m forward return、next-quarter EBITDA

YAML 只表达需求和研究方向，没有写入复杂业务公式。

## Dataset 示例

创建 5 个 research-data-core `DatasetConfig` 兼容契约：

1. `cycle.cf.price`
2. `cycle.cf.financials`
3. `commodity.urea`
4. `commodity.henry_hub`
5. `crop.corn`

配置声明 storage、仓库相对路径、entity/time、available time、字段映射和 required columns。
这些是接口契约，不保证对应物理文件已经存在；本阶段未尝试读取这些路径。

## 代码边界

features 下创建 nitrogen、agriculture 和 valuation 函数骨架。函数 docstring 描述后续职责，当前只
返回输入 frame 的副本，不计算复杂特征。dataset pipeline 只列出计划使用的 dataset id。

明确不包含：

- 数据下载、真实数据合并或数据写入
- 完整 nitrogen economics 或商品价差公式
- 模型实现、训练、回测、预测或报告
- outputs、模型文件、本地凭据
- 对现有业务项目的运行时接入
- alpha_agent_system 迁移或 build-daily-cache 删除

## 验证结果

在项目目录执行：

| 验证 | 结果 |
| --- | --- |
| `python3 -m compileall .` | 通过 |
| `.venv/bin/python -m pip install -e ".[dev]"` | 通过 |
| editable 安装 `../../../platform/data/research-data-core` | 通过 |
| `.venv/bin/python -m pytest -q` | `3 passed` |
| `check_cf_config.py --help` | 通过 |
| `inspect_cf_datasets.py --help` | 通过 |
| `build_cf_dataset.py --help` | 通过 |
| `run_cf_analysis.py --help` | 通过 |

四个 scripts 的默认只读命令也全部通过：CF config 摘要正确，5 个 dataset contract 全部列出，
build/analysis 入口明确报告未读取、合并、写入数据或执行分析。

## Git 安全检查

- `.venv/`、`__pycache__/`、`.pytest_cache/` 和 `*.egg-info/` 均被 ignore。
- 未创建或提交 outputs。
- 未提交 parquet、CSV、SQLite、DuckDB、pickle、模型、`.env` 或 token。
- 未硬编码用户本地绝对路径。
- 未读取 `storage/shared_data` 物理数据。
- 现有业务项目和两个 core 均无本阶段 diff。

## 遗留问题与结论

1. 物理 commodity、crop 和 financial datasets 尚未确认或接入。
2. CF price 路径虽已存在于共享数据布局中，本阶段也只把它作为契约，不读取数据。
3. feature 函数是有明确职责的占位实现，不应视为已完成业务特征。
4. 在接入真实 CF 数据前，应结合真实 consumer tests 处理
   `research_data_core_stabilization.md` 中的 required-column、available-time、bounded-read 和
   as-of ordering 等问题。
5. models、training 和 reports 仅为空 package 边界。

Phase 7c 骨架目标已完成。可以进入 CF 数据接入的设计/验证阶段，但不应直接开始大规模读取、模型
训练或业务接入；下一阶段应先确认物理数据来源、字段语义和 point-in-time 契约。
