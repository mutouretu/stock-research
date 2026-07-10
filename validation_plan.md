# stock-research 迁移验证计划

## 验证原则

1. 每次只实施并验证一个迁移阶段，结果写入 `migration/logs/`。
2. 项目移动后运行 `python -m compileall .`；存在测试时运行 `pytest -q`。
3. 失败必须原样记录，不以 `|| true` 掩盖最终状态。
4. 每次路径变化后运行旧路径盘点，并说明每个保留引用的理由。
5. `shared_data` 是大型本地数据仓库，任何阶段都不得误加入 Git。
6. 保持既有 Python package/import 名称不变，不借迁移重构业务逻辑。

## 通用检查

从工作区根目录运行：

```bash
git status --short                         # 若根目录是 Git 仓库
find . -maxdepth 3 -type d | sort
bash migration/scripts/check_layout.sh
bash migration/scripts/check_old_paths.sh
```

当前工作区由多个独立 Git 仓库组成，根目录不是 Git 仓库时，应改用 `git -C <project> status --short` 分别检查。

## Phase 1：创建迁移骨架和仓库盘点

只在 `migration/` 下创建暂存空目录、迁移文档、盘点日志和检查脚本，不在仓库根目录创建目标骨架，不移动或删除项目，不创建新项目代码。

```bash
bash migration/scripts/check_layout.sh
bash migration/scripts/check_old_paths.sh
```

输出：`migration/logs/000_inventory.md`。本阶段的 layout 检查只要求 `migration/` 下的暂存分层目录存在，不要求根目录目标项目路径存在。

## Phase 2：迁移 market-data-hub

移动到 `platform/data/market-data-hub`，更新工作目录和数据路径引用，保持 `market_data_hub` import 不变。

```bash
cd platform/data/market-data-hub
python -m compileall .
pytest -q
cd ../../..
bash migration/scripts/check_old_paths.sh
```

输出：`migration/logs/002_move_market_data_hub.md`。

## Phase 3：迁移 shared_data

迁移前后记录大小、Git 跟踪状态与消费者路径；禁止把数据文件加入 Git。

```bash
du -sh shared_data
test -d storage/shared_data
du -sh storage/shared_data
bash migration/scripts/check_old_paths.sh
```

输出：`migration/logs/003_move_shared_data.md`。

## Phase 4：确认功能合并后删除 build-daily-cache

先逐项核对 Tushare 下载、失败日期重试、增量合并、格式转换及仍需保留的数据/工具。只有功能完整合并、消费者已切换且必要资产已处理后才允许删除。

```bash
bash migration/scripts/check_old_paths.sh
test ! -d build-daily-cache
```

输出：`migration/logs/004_remove_build_daily_cache.md`，必须附功能对照结论。

## Phase 5：迁移 pattern 项目

将 `stock-pattern-search` 和 `market_pattern_labeler` 移入 `research/pattern/`，不改 package 名或业务逻辑。

```bash
(cd research/pattern/stock-pattern-search && python -m compileall . && pytest -q)
(cd research/pattern/market_pattern_labeler && python -m compileall . && pytest -q)
bash migration/scripts/check_old_paths.sh
```

输出：`migration/logs/005_move_pattern_projects.md`。

## Phase 6：迁移 alpha_agent_system

移动到 `automation/alpha_agent_system`，更新项目根目录配置，保持 agent 行为不变。

```bash
(cd automation/alpha_agent_system && python -m compileall . && pytest -q)
bash migration/scripts/check_old_paths.sh
```

输出：`migration/logs/006_move_alpha_agent_system.md`。

## Phase 7：创建三个新项目骨架

创建 `platform/data/research-data-core`、`platform/ml/research-ml-core`、`research/cycle/cycle-equity-research`，只建立可安装、可导入、可测试的最小骨架。

```bash
(cd platform/data/research-data-core && python -m compileall . && pytest -q)
(cd platform/ml/research-ml-core && python -m compileall . && pytest -q)
(cd research/cycle/cycle-equity-research && python -m compileall . && pytest -q)
```

输出：`migration/logs/007_create_new_project_skeletons.md`。

## Phase 8：后续抽取通用 ML 框架

在迁移稳定、边界与测试明确后，再逐步从 `stock-pattern-search` 抽取通用特征、标签、切分、训练、评估与回测能力。此工作不属于 Phase 1，也不得与目录迁移捆绑。

输出：后续单独设计文档和验证日志。

## 最终验收

最终阶段才检查根目录不再平铺业务项目、`build-daily-cache` 已按条件删除、新 core 项目可导入，以及旧路径引用均已更新或有明确保留理由。Phase 1 不应用这些最终条件判定失败。
