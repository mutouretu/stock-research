# Phase 2 补充：同步 market-data-hub 合并后的 main

同步日期：2026-07-10

## 背景

`cn-tushare-cache-merge` 已合并到 `https://github.com/mutouretu/market-data-hub` 的默认
`main` 分支。新仓库此前导入基准为 `e8ea24b`，本次同步到 merge commit：

```text
b2c19a0 Merge pull request #1 from mutouretu/cn-tushare-cache-merge
```

## 同步内容

上游在两个 commit 中修改 9 个文件，约新增 1,208 行，主要包括：

- CN Tushare 日频下载和失败日期重试能力。
- 日频增量合并流水线。
- CN 日线按股票导出流水线。
- 新增 CLI 命令和 CN 配置。
- 新增 `tests/test_cn_tushare_pipeline.py`。

使用临时克隆仓库 fetch/fast-forward 后，通过与 Phase 2 相同的 `rsync` 排除规则同步到
`platform/data/market-data-hub/`。未复制 `.git`、虚拟环境、缓存、`data/`、`reports/`
或 parquet/CSV/数据库文件；上游源树本次仍没有数据类文件。

## 本地保留修改

在最新上游 README 上重新应用了三处仅限文档的工作区说明：

- `upper-level stock-research workspace` 定位。
- `Relationship With stock-research` 说明。
- `../shared_data` 暂时兼容、未来切换到 `storage/shared_data` 的迁移说明。

除此之外，上游源码、配置、测试及 `pyproject.toml` 按 `b2c19a0` 同步，没有重构业务逻辑或 CLI。

## 验证结果

在 `platform/data/market-data-hub/` 使用 Phase 2 已建立的本地忽略虚拟环境运行：

```text
.venv/bin/python -m compileall -q .  -> exit 0
.venv/bin/python -m pytest -q       -> 16 passed in 0.49s
```

其他检查：

- `market-data-hub` project name、`market_data_hub` package discovery 和
  `market-data-hub = market_data_hub.cli:main` console script 保持不变。
- Git 候选文件中没有 `.git`、虚拟环境、缓存、`data/`、`reports/` 或任何
  parquet/feather/sqlite/duckdb/CSV 文件。
- 与上游 `b2c19a0` 进行排除式 rsync dry-run，对源码树只报告 README 这一项预期文档差异。
- `bash _migration/scripts/check_layout.sh`：退出码 0。
- `bash _migration/scripts/check_old_paths.sh`：退出码 0，共输出 216 行；旧名称/package
  命中按脚本设计不导致失败。
- `git diff --check`：通过。

## 结论

合并后的 `market-data-hub` `main` 已完整同步到新仓库，CN Tushare 流水线及其测试已纳入，
且没有引入数据产物或嵌套 Git 仓库。
