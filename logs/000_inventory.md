# Phase 1 仓库盘点报告

盘点日期：2026-07-10
盘点范围：工作区根目录 `/Users/dengerqiang/Documents/code/Trade/stock-research`；忽略 `.git`、`.venv`、缓存目录内容及 `shared_data` 数据内容进行文本搜索。

## 1. 当前根目录结构

```text
stock-research/
├── alpha_agent_system/
├── build-daily-cache/
├── market_pattern_labeler/
├── market-data-hub/
├── migration/
├── shared_data/
├── stock-pattern-search/
└── migration/
    ├── platform/           # Phase 1 暂存空骨架
    │   ├── data/
    │   └── ml/
    ├── research/
    │   ├── pattern/
    │   └── cycle/
    ├── automation/
    ├── storage/
    ├── ops/
    │   ├── jobs/
    │   └── scripts/
    └── docs/
```

所有原项目均仍在原路径；本阶段没有移动或删除业务目录。暂存空目录全部位于 `migration/` 下，并使用 `.gitkeep` 保留；仓库根目录没有创建这些目标骨架。

## 2. 根目录项目用途初判

| 目录 | 初步用途 |
|---|---|
| `alpha_agent_system` | 调用独立选股项目的 LLM/Agent 编排、报告和调度上层；不负责交易执行。 |
| `build-daily-cache` | 用 Tushare 拉取、过滤、重试并合并 A 股日频数据；还包含增量数据处理工具和大量本地产物。 |
| `market_pattern_labeler` | 从日线 parquet 召回形态候选并导出供人工复核的 CSV。 |
| `market-data-hub` | 跨市场数据采集、清洗、标准化和本地导出，已包含 CN Tushare 日频流水线。 |
| `shared_data` | 多项目共享的本地数据仓库，主要是 parquet 原始/缓存数据、标签和美股数据。 |
| `stock-pattern-search` | 通用股票形态、策略搜索和机器学习训练/推理框架，目前以 Type-N 为主要生产链路。 |
| `migration` | 独立 Git 仓库形式的迁移文档、路径映射、脚本和日志。 |

## 3. Python 项目判断

明确或高度疑似 Python 项目：

- `alpha_agent_system`：有 `requirements.txt`、`src/`、Python 脚本。
- `build-daily-cache`：有 `pyproject.toml`、`main.py`、Python 工具。
- `market_pattern_labeler`：有 `pyproject.toml`、`src/`、`tests/`。
- `market-data-hub`：有 `pyproject.toml`、Python package、`tests/`。
- `stock-pattern-search`：有 `requirements.txt`、`src/`、`tests/`。

`migration`、`shared_data` 不是 Python 项目。

## 4. 项目元数据文件

下表只统计项目自身顶层文件，不把 `.pytest_cache/README.md` 当作项目文档。

| 目录 | pyproject.toml | setup.py | setup.cfg | requirements.txt | package.json | Makefile | README.md |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `alpha_agent_system` |  |  |  | ✓ |  |  | ✓ |
| `build-daily-cache` | ✓ |  |  |  |  |  | ✓ |
| `market_pattern_labeler` | ✓ |  |  |  |  |  | ✓ |
| `market-data-hub` | ✓ |  |  |  |  |  | ✓ |
| `stock-pattern-search` |  |  |  | ✓ |  |  | ✓ |
| `migration` |  |  |  |  |  |  | ✓ |
| `shared_data` |  |  |  |  |  |  |  |

未发现顶层 `setup.py`、`setup.cfg`、`package.json` 或 `Makefile`。

## 5. shared_data 大文件情况

`shared_data` 总大小约 **24 GiB**，其中 `raw/` 约 24 GiB、`us/` 约 273 MiB、`labels/` 约 12 MiB。发现多个大于 10 MiB 的 parquet 文件，包括数个年度增量文件、备份文件和完整 daily cache。因此它明确属于大型本地数据目录，迁移和 Git 操作必须特别谨慎。

## 6. shared_data Git 跟踪情况

工作区根目录本身**不是 Git 仓库**，`shared_data` 也没有自己的 `.git`，所以不存在可用 `git ls-files shared_data` 直接验证的根仓库索引。逐一检查六个独立 Git 仓库的 tracked paths，没有发现路径中含 `shared_data` 的已跟踪文件。

结论：当前证据表明 `shared_data` 没有被这些仓库跟踪，但由于缺少统管根仓库，不能把它表述为“已由根仓库 ignore”。后续若建立 monorepo，必须先配置根 `.gitignore` 并再次验证。

## 7. build-daily-cache 是否还有独立代码

有。除 `main.py` 外，仍有：

- `custom_pipeline/tools/ingest_daily_data.py`
- `custom_pipeline/tools/merge_daily_increment.py`
- `custom_pipeline/tools/convert_xlsx_labels.py`
- 独立 `pyproject.toml`、README 和 lockfile
- 大量 parquet 增量、失败日期 JSON、`tk.csv` 等本地产物

因此不能只因主要下载能力已出现于新项目就直接删除整个目录；需先判断三个工具和本地资产是否仍有唯一用途。

## 8. 功能是否已在 market-data-hub 中存在

主要能力看起来已经存在：`market-data-hub` 有 CN 配置、Tushare adapter、交易日历、`daily`/`daily_basic` 等端点抓取、失败日期保存与重试、增量 parquet 下载和按股票导出流水线，并有 `tests/test_cn_tushare_pipeline.py` 覆盖。

但本次只做静态初判，尚未证明功能完全等价。尤其要对照 `build-daily-cache` 的筛选规则、增量合并、xlsx 标签转换以及历史本地产物处理。结论是“具备合并基础，Phase 4 前仍需功能矩阵和运行验证”，不是现在可删除。

## 9. 旧路径/名称引用盘点

使用 `migration/scripts/check_old_paths.sh` 所列 11 个关键词搜索；排除了 `.git`、`.venv`、`__pycache__`、`shared_data` 数据内容和本报告自身。首次盘点匹配数如下（数量是匹配 token 数，不是唯一文件数）：

| 关键词 | 匹配数 |
|---|---:|
| `build-daily-cache` | 27 |
| `build_daily_cache` | 8 |
| `daily-cache` | 25 |
| `daily_cache` | 203 |
| `market-data-hub` | 46 |
| `market_data_hub` | 84 |
| `stock-pattern-search` | 20 |
| `stock_pattern_search` | 1 |
| `market_pattern_labeler` | 165 |
| `alpha_agent_system` | 71 |
| `shared_data` | 127 |

Phase 1 中这些引用和原目录仍存在是预期行为。命中既包含真实相对路径（例如 `../shared_data`、`../build-daily-cache`），也包含必须保持不变的 Python import/package 名。后续阶段不得机械替换下划线 package 名。

## 10. 风险与后续建议

1. **不是单一根 Git 仓库**：六个项目各有 `.git`，而 `shared_data` 和新骨架在其外。实施物理迁移前须先决定保留多仓库、Git submodule，还是创建 monorepo；该选择会影响历史保留和提交方式。
2. **已有未提交改动**：`alpha_agent_system` 有 3 个已修改源码文件，`stock-pattern-search` 有 1 个已修改脚本，`build-daily-cache/tk.csv` 未跟踪；后续移动必须保护这些用户改动。
3. **敏感/本地文件**：可见多个 `.env`、`.DS_Store`、虚拟环境、缓存和数据产物。迁移前复核 ignore 规则，禁止提交 token 与本地数据。
4. **数据体积大**：24 GiB 的 `shared_data` 不适合复制式迁移；应做同文件系统原子移动、容量检查和消费者路径切换，并准备回滚方案。
5. **build-daily-cache 尚有独立资产**：必须先建立逐项功能矩阵和资产处置清单，再决定删除。
6. **旧路径与 import 混合**：后续更新应区分文件系统路径和 Python package 名，避免大规模字符串替换破坏 import。
7. **运行验证边界**：Phase 1 未改 Python 业务代码，且全根目录 `compileall` 会遍历多个独立项目、虚拟环境和大量工作区内容，因此本阶段未运行全局 `python -m compileall .`；项目级编译与测试应在各自移动阶段执行并记录。

## Phase 1 验证记录

- 根目录 `git status --short`：失败，原因是根目录不是 Git 仓库；已改为逐仓库检查并记录上述未提交改动。
- `find . -maxdepth 3 -type d | sort`：完成，用于生成结构盘点。
- `bash migration/scripts/check_layout.sh`：通过，15 个 Phase 1 必需目录全部存在。
- `bash migration/scripts/check_old_paths.sh`：退出码 0，共输出 644 行（含标题和完成提示）；命中结果按设计只做盘点，没有导致失败。
- `python -m compileall .`：基于上述安全和范围判断未执行；不是代码验证失败。
