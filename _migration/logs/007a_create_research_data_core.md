# Phase 7a - 创建 research-data-core 数据接口层

## 基本信息

- 创建日期：2026-07-10
- 项目路径：`platform/data/research-data-core/`
- project 名称：`research-data-core`
- package 名称：`research_data_core`
- 版本：`0.1.0`

## 工程组织

项目参考 stock-pattern-search 的可操作工程风格，包含 `configs/`、`scripts/`、`src/`、
`tests/`、README 和 `pyproject.toml`。dataset YAML 示例与协议说明位于
`configs/datasets/`，三个只读脚本用于检查 shared-data、检查小样本和验证数据集。

本阶段只创建独立 package，没有修改或接入 stock-pattern-search、research-ml-core、
market_pattern_labeler、market-data-hub 或其他业务项目。

## 已实现功能

1. 解析 `STOCK_RESEARCH_ROOT`，或从当前路径向上识别包含 README、platform、research 和
   storage 的工作区根目录。
2. 解析 `STOCK_RESEARCH_SHARED_DATA_DIR`，默认返回 `storage/shared_data`。
3. `DatasetConfig` 从 YAML 加载 dataset id、storage、path、entity/time、available time、
   字段映射和 required columns。
4. `DatasetCatalog` 递归发现 YAML，通过 dataset id 获取配置并列出 id。
5. CSV、单 parquet 和有界 parquet-by-entity 目录读取。
6. required column、duplicate key 检查和 source-to-canonical 字段映射。
7. `DatasetLoader` 根据配置加载数据，并可选标准化为 `entity_id` / `time`。
8. 支持 `by=None` 或任意分组列的自动排序 as-of merge。
9. `check_shared_data.py`、`inspect_dataset.py`、`validate_dataset.py` 三个只读 CLI。

Python 源码和 scripts 中没有硬编码 `ts_code`、`ticker` 或具体业务品种字段。示例配置使用中性
字段名，所有实体、时间和物理字段均由配置提供。

## 明确不包含

- Tushare、Yahoo 或 market-data-hub 采集逻辑
- Type-N、周期股、商品价差、盈利预测等业务逻辑
- 模型训练、回测和报告生成
- trade calendar、resampling 等后续扩展
- 对现有业务项目的 import 或运行时切换

没有迁移 alpha_agent_system，没有删除 build-daily-cache，也没有创建
cycle-equity-research。

## 验证结果

在 `platform/data/research-data-core/` 执行：

| 验证 | 结果 |
| --- | --- |
| `python3 -m compileall .` | 通过 |
| `.venv/bin/python -m pip install -e ".[dev]"` | 通过 |
| `.venv/bin/python -m pytest -q` | `8 passed` |
| package import/version | 通过，输出 `0.1.0` |
| `scripts/check_shared_data.py --help` | 通过 |
| `scripts/inspect_dataset.py --help` | 通过 |
| `scripts/validate_dataset.py --help` | 通过 |
| 禁止业务字段源码扫描 | 无命中 |

8 项测试覆盖 package import、当前仓库根识别、shared-data 环境变量、YAML config、catalog
查找、缺字段、重复 key、字段映射、entity/time 标准化、CSV/parquet-by-entity 加载以及有/无
entity 的 as-of 对齐。

## Git 安全检查

- `.venv/`、`__pycache__/`、`.pytest_cache/` 和 `*.egg-info/` 由根 `.gitignore` 排除。
- 测试数据仅写入 pytest 临时目录。
- 未读取或扫描 shared_data 内容；只运行了脚本 `--help`。
- 未提交 parquet、CSV、SQLite、DuckDB、pickle、模型、`.env` 或凭据。
- 未硬编码本地绝对路径。

## 遗留问题与结论

1. 示例 YAML 是接口契约，不保证对应物理数据集已经存在。
2. `check_shared_data.py` 的实际大小统计会调用系统 `du`；本阶段为避免扫描约 24 GiB 数据，只
   验证其 help，没有执行实际扫描。
3. dataset config 目前支持 `parquet`、`csv` 和 `parquet_by_entity`；更多格式和 catalog 元数据
   应按实际消费者需求后续增加。
4. 尚未建立业务消费者兼容测试，因此本阶段不接入任何业务项目。

research-data-core 的最小数据接口层已完成并可独立使用。可以进入
`cycle-equity-research` 的独立创建阶段，但接入任何业务前仍应先定义具体数据集 YAML 和消费者
回归测试。
