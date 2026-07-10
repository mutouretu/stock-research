# Phase 2.4：确认 market-data-hub 已同步到最新 CN/Tushare 版本

验证日期：2026-07-10

## 结论

`platform/data/market-data-hub/` 已包含源仓库 `main` 最新的 CN/Tushare daily cache
pipeline。Phase 2.4 开始时重新 fetch 源仓库，远端最新 commit 仍为：

```text
b2c19a09367773a6e42b3344b7ffe8e762b0a2f7
b2c19a0 Merge pull request #1 from mutouretu/cn-tushare-cache-merge
```

当前模块在紧邻本阶段的补充同步中已更新到该 commit，因此 Phase 2.4 验收时无需再次复制源码。

## CN/Tushare 内容检查

### 依赖

`pyproject.toml` 包含：

```toml
"tushare>=1.4.29"
```

editable 安装最终确认实际安装 `tushare 1.4.29`。

### CLI 命令

源码和 `.venv/bin/market-data-hub --help` 均包含：

- `download-cn-prices`
- `export-cn-daily-by-symbol`
- `merge-cn-daily-increment`
- `cn-daily-update`

### 源码与符号

确认存在：

- package：`market_data_hub.markets.cn`
- adapter：`TushareCNAdapter`
- Tushare 接口封装：`daily`、`daily_basic`、`trade_cal`（经 `trade_calendar` 调用）
- 失败日期处理：`failed_dates`、保存/读取与重试逻辑
- 增量合并模块：`market_data_hub.markets.cn.pipelines.merge_daily_increment`
- 按股票导出模块：`market_data_hub.markets.cn.pipelines.export_daily_by_symbol`
- CN 流水线测试：`tests/test_cn_tushare_pipeline.py`

## 是否重新同步

Phase 2.4 重新 fetch 并对比了 `https://github.com/mutouretu/market-data-hub` 的
`origin/main`。远端仍是 `b2c19a0`，与当前导入基准一致，所以本次确认步骤没有再次
rsync。此前从 `e8ea24b` 同步到 `b2c19a0` 的过程记录在
`002a_sync_market_data_hub_main.md`。

同步排除规则继续覆盖 `.git/`、`.venv/`、`data/`、`reports/`、`__pycache__/`、
`.pytest_cache/`、parquet、CSV、SQLite 和 DuckDB 文件；未迁移 `shared_data` 或其他旧项目。

## 指定验证命令与结果

在 `platform/data/market-data-hub/` 执行：

| 命令 | 结果 |
|---|---|
| `python3 -m compileall .` | 通过，退出码 0 |
| `python3 -m venv .venv` | 通过，退出码 0；目录被 Git 忽略 |
| `.venv/bin/python -m pip install -e ".[dev]"` | 首次受限网络环境失败；允许联网后重跑成功，退出码 0 |
| `.venv/bin/python -m pytest -q` | 通过，`16 passed in 1.52s` |
| `.venv/bin/market-data-hub --help` | 通过，退出码 0；四个 CN 命令全部出现 |

首次 pip 失败是隔离环境无法解析 PyPI，报错为无法获取 build dependency
`setuptools>=68`；不是项目依赖或构建定义错误。联网重跑后 editable build 和全部依赖安装成功。

## 业务边界

- 未修改 market-data-hub 业务逻辑。
- 未修改 CLI 行为。
- 未迁移 `shared_data`。
- 未删除 `build-daily-cache`。
- 未迁移 `stock-pattern-search`、`market_pattern_labeler` 或其他项目。
- 未把数据文件、缓存、虚拟环境或嵌套 `.git` 加入 Git。

## 遗留问题

1. README 中的 `../shared_data` 仍作为分阶段迁移兼容路径保留，实际切换到
   `storage/shared_data` 留待 shared_data 迁移阶段。
2. `python3 -m compileall .` 会遍历本地 `.venv`，输出较多，但结果为成功且这些文件均被忽略。
3. 依赖通过范围约束解析，仓库尚无锁文件；可复现环境策略应在独立任务中确定。
