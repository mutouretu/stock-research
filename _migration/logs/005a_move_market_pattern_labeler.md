# Phase 5a：迁移 market_pattern_labeler

迁移日期：2026-07-10

## 1. 来源与目标

- 来源仓库：`https://github.com/mutouretu/market_pattern_labeler`
- 来源默认分支：`main`
- 来源 commit：`3815e42`（`Organize strategy output paths`）
- 目标路径：`research/pattern/market_pattern_labeler/`
- 导入方式：GitHub 临时 clone 后使用 `rsync -a` 导入
- 导入规模：75 个源码/配置/测试/文档文件，约 544 KiB

没有直接修改父目录旧 `../market_pattern_labeler` 工作树；只读检查显示其 `main` 保持 clean。

## 2. 排除内容

导入时排除：

- `.git/`
- `.venv/`、`venv/`
- `__pycache__/`
- `.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`
- `.DS_Store`
- 顶层 `outputs/`、顶层 `data/`
- `*.parquet`、`*.csv`、`*.sqlite`、`*.duckdb`、`*.pkl`、`*.pickle`

项目的 `src/market_pattern_labeler/data/` 是 Python package 源码，包含 daily loader，因此特意保留；排除规则只针对源仓库顶层 `/data/`。

导入后的首次禁入项扫描为空，没有复制嵌套 Git、环境、缓存、输出或数据文件。

## 3. Package、CLI 与业务逻辑

保持不变：

- project name：`market-pattern-labeler`
- Python package/import：`market_pattern_labeler`
- source layout：`src/market_pattern_labeler/`
- console script：`mplabeler = market_pattern_labeler.cli.main:main`
- CLI commands：`run-miner`、`check-data-dir`、`plot-candidates`、`build-ml-labels`

没有修改 Python 业务代码、miner、配置或 CLI 行为。与源 commit 做排除式 rsync dry-run，源码文件差异只有 README 这一项预期文档修改；其他显示仅为验证生成目录造成的时间戳变化。

## 4. README 路径说明

README 仅增加 monorepo 迁移说明：

- 父目录 `../shared_data -> migration/storage/shared_data` 软链接继续服务旧 checkout。
- 从迁移后的项目目录运行时，canonical 显式路径是
  `../../../storage/shared_data/...`。
- 现有代码和大量示例中的默认 `../shared_data` 没有机械替换，统一收口留给独立任务。

## 5. 编译、安装、测试与 CLI

在目标项目目录运行：

| 验证 | 结果 |
|---|---|
| `python3 -m compileall .` | 通过，退出码 0 |
| `python3 -m venv .venv` | 通过；本地目录被 Git ignore |
| `.venv/bin/python -m pip install -e ".[dev]"` | 首次受限网络失败；允许联网后成功 |
| `.venv/bin/python -m pytest -q` | 通过，`68 passed in 13.46s` |
| `.venv/bin/python -m market_pattern_labeler.cli.main --help` | 通过 |
| `.venv/bin/mplabeler --help` | 通过 |

首次安装失败是隔离环境无法访问 PyPI build dependency，不是项目构建或依赖声明失败。

## 6. shared_data 读取 smoke test

使用 canonical 数据目录：

```text
../../../storage/shared_data/us/raw/daily/parquet_by_symbol
```

该目录共有 972 个 parquet。

### `check-data-dir --max-files 5`

结果：

```text
checked_files=5
ok_files=5
failed_files=0
required_columns_status=ok
missing_column_warnings=0
rows_checked=31879
date_range=2000-01-03 to 2026-07-02
```

抽查文件为 A、AA、AAL、AAON、AAPL；全部成功读取。

### 单股票 miner smoke

运行 Type-N miner，限制 `--symbols AAPL`，输出写入：

```text
/private/tmp/stock-research-labeler-smoke/aapl_type_n_candidates.csv
```

结果：处理 1 个 symbol、失败 0、生成 10 条候选，CSV 约 2.9 KiB且字段完整。没有写入项目 `outputs/`。

## 7. Git 安全检查

- 没有嵌套 `.git/`。
- 验证生成的 `.venv`、`.pytest_cache`、`__pycache__` 和 egg-info 均受根/项目 `.gitignore` 保护，不属于 Git candidate。
- `git ls-files --others --exclude-standard` 中没有 outputs、data 文件或 parquet/CSV/数据库/pickle。
- smoke CSV 仅位于 `/private/tmp`。
- `storage/shared_data` 仍未被 Git 跟踪。
- 未修改 market-data-hub、stock-pattern-search、alpha_agent_system 或 build-daily-cache。

## 8. 遗留问题

1. 迁移项目的代码默认值和大量 README 示例仍使用 `../shared_data`；从新项目目录运行时必须显式传 canonical 路径，后续应单独设计统一配置而非机械替换。
2. 本地 `.venv` 与缓存保留用于验证但不会提交；若希望工作区更轻，可在提交后安全清理。
3. 依赖使用范围约束且没有 lockfile，可复现环境策略尚未统一。

## 9. Phase 5b 判断

**可以进入 Phase 5b：迁移 `stock-pattern-search`。**

依据：package/CLI/业务代码保持不变，完整测试通过，真实 shared_data parquet 读取和最小 miner 均成功，Git 安全检查通过。

Phase 4 仍保持阻塞，不得删除 `build-daily-cache`。
