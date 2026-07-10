# Phase 2：迁移 market-data-hub

验证日期：2026-07-10

## 迁移结果

- 源仓库：`https://github.com/mutouretu/market-data-hub`
- 源分支：远端默认分支 `main`
- 源 commit：`e8ea24b`（`Extend Russell 1000 history window`）
- 目标路径：`platform/data/market-data-hub/`
- 导入文件：60 个，导入后源码/配置/测试总大小约 296 KiB（不含后续本地验证环境）

源仓库先通过 `git clone` 克隆到 `/private/tmp/stock-research-phase2-market-data-hub`，再使用 `rsync -a` 导入目标路径。没有直接复制或修改父目录中的旧 `../market-data-hub` 工作树。

## 排除内容

导入时明确排除：

- `.git/`
- `.venv/`、`venv/`
- `__pycache__/`
- `.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`
- `.DS_Store`
- `data/`、`reports/`
- `*.parquet`、`*.feather`、`*.sqlite`、`*.duckdb`、`*.csv`

导入完成后的首次禁入项扫描没有发现上述文件或目录。编译和测试过程随后在目标项目内生成了被 Git 忽略的 `.venv`、`__pycache__`、`.pytest_cache` 和 editable-install egg-info；它们不是源仓库复制内容，也不属于 Git 候选文件。

## Package、CLI 与业务逻辑

保持不变：

- project name：`market-data-hub`
- Python package/import：`market_data_hub`
- console script：`market-data-hub = market_data_hub.cli:main`
- setuptools package discovery：`market_data_hub*`

未修改 Python 业务代码、数据抓取逻辑、配置格式或 CLI 行为。

## README 修改

只修改 `platform/data/market-data-hub/README.md`：

1. 将旧的 “upper-level type-n research system” 定位改为统一的 “upper-level stock-research workspace”。
2. 将关系说明标题改为 `Relationship With stock-research`。
3. 保留现有 `../shared_data` 命令示例以避免提前改变 CLI/路径行为，并注明未来统一路径是 `storage/shared_data`，实际切换推迟到 Phase 3。

`pyproject.toml` 未修改。

## 项目验证

在 `platform/data/market-data-hub/` 运行：

### 原始指定命令

- `python -m compileall .`：失败，退出码 127；当前 shell 没有 `python` 命令。
- `pytest -q`：失败，退出码 127；当前 shell 没有独立 `pytest` 命令。

以上是环境命令缺失，不是编译或测试用例失败。

### Python 3 回退验证

- `python3 -m compileall .`：通过，退出码 0。
- `python3 -m pytest -q`：未能启动测试，系统 Python 3.12 缺少 `pytest`。

随后创建项目内、被 Git 忽略的 `.venv`，运行：

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/python -c 'import market_data_hub; print(market_data_hub.__version__)'
```

结果：

```text
12 passed in 0.47s
0.1.0
```

最终 pytest 与 package import 验证均通过。

额外从新仓库根目录直接运行
`platform/data/market-data-hub/.venv/bin/python -m pytest -q` 时得到 `1 failed, 11 passed`：
`test_load_us_config` 使用相对路径 `configs/us.yaml`，因此依赖当前工作目录。该调用方式不符合本阶段指定的“先进入项目目录”验证步骤，但失败已保留记录；本阶段不修改既有测试或配置加载行为。

## 仓库根目录验证

- `git status --short`：执行成功；显示 README、迁移资料更新、删除 `platform/data/.gitkeep` 和新增模块目录。
- `find platform/data/market-data-hub -maxdepth 3 -type d | sort`：执行成功；列出模块源码、配置、测试和本地忽略的验证环境/缓存。
- `bash _migration/scripts/check_layout.sh`：通过，退出码 0。
- `bash _migration/scripts/check_old_paths.sh`：通过，退出码 0，共输出 171 行。命中包括保留的 package/import 名和迁移文档，按设计不导致失败。

父目录旧 `../market-data-hub` 仍位于 `cn-tushare-cache-merge` 分支且工作树干净，本阶段没有修改它。

## 遗留问题

1. 初次 Phase 2 按 GitHub 默认 `main` 的 `e8ea24b` 导入；随后 `cn-tushare-cache-merge` 已合并到上游 `main`，并在补充同步中更新到 merge commit `b2c19a0`。详见 `002a_sync_market_data_hub_main.md`。
2. README 和当前实现仍保留 `../shared_data` 路径兼容行为；在 Phase 3 迁移共享数据时统一切换到 `storage/shared_data`。
3. 当前本地验证使用 Python 3.12 和即时解析的最新兼容依赖；仓库尚无锁文件，后续可单独制定可复现环境策略。
4. 测试套件依赖从项目根目录启动；若未来需要从 monorepo 根目录统一运行测试，应在单独任务中明确测试工作目录或调整测试资源定位。

## 结论

Phase 2 迁移完成。`market-data-hub` 已作为源码模块导入数据平台层，package、CLI 和业务逻辑保持不变，完整测试通过，未导入大数据或旧仓库元数据。
