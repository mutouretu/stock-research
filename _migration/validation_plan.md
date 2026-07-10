# stock-research 迁移验证计划

## 验证原则

1. 当前 Git 仓库根目录就是未来新 `stock-research` 的根目录。
2. 每阶段只实施一个明确范围，并将结果记录到 `_migration/logs/`。
3. 不隐瞒编译、测试或路径检查失败。
4. 保持 Python package/import 名称不变，不把目录迁移扩大为业务重构。
5. `storage/shared_data/` 及其他大型数据文件不得加入 Git。
6. 父目录旧项目的现有修改必须保留。

## Phase 1b：修正新仓库根目录定位

- 在当前仓库根目录创建 `platform/`、`research/`、`automation/`、`storage/`、`ops/` 和 `docs/` 骨架。
- 把迁移资料收纳到 `_migration/`。
- 更新根目录 README、路径映射、检查脚本和 `.gitignore`。
- 不迁移、复制、删除或修改父目录中的旧项目。

验证：

```bash
git status --short
find . -maxdepth 3 -type d | sort
bash _migration/scripts/check_layout.sh
bash _migration/scripts/check_old_paths.sh
```

输出：`_migration/logs/001_fix_repo_root_layout.md`。

## Phase 2：迁移 market-data-hub

从 `../market-data-hub` 迁移到 `platform/data/market-data-hub`，保持 `market_data_hub` import 不变；随后运行项目编译、测试和旧路径检查。

输出：`_migration/logs/002_move_market_data_hub.md`。

## Phase 2.5 验收结论

`market-data-hub` 基础编译、16 项测试、US AAPL/MSFT 真实短窗口下载/验证/按股票导出，
以及 CN 合成增量合并/直接导出均已通过。详细证据见
`_migration/logs/002_5_validate_market_data_hub_functionality.md`。

- 允许进入 Phase 3，但迁移时必须完成 `../shared_data` 到 `storage/shared_data` 的路径切换、完整性校验和消费者回归。
- 暂不执行 Phase 4 归档/删除；真实 CN 单日下载已通过，但 XLSX 标签转换、labels/schema、pickle 兼容、凭据和历史资产仍待处理。

## Phase 3：迁移 shared_data

从 `../shared_data` 迁移到 `storage/shared_data`。迁移前后核对容量、文件数量、消费者路径和 Git ignore 状态，不复制大型数据进入 Git 历史。

迁移结论（2026-07-10）：已使用同文件系统 `mv` 完成，迁移前后均为 25,164,336 KiB、
159,262 个文件和 41 个目录。旧路径通过
`../shared_data -> migration/storage/shared_data` 软链接保持兼容；Git 跟踪的数据文件为 0，
5 个 parquet 抽样均可读取。可以进入 Phase 5，Phase 4 的归档/删除阻塞保持不变。

输出：`_migration/logs/003_move_shared_data.md`。

## Phase 4：处置 build-daily-cache

逐项确认 `../build-daily-cache` 的下载、筛选、重试、增量合并、格式转换和本地资产已由 `market-data-hub` 或其他明确位置承接后，才允许删除或归档。

输出：`_migration/logs/004_remove_or_archive_build_daily_cache.md`。

## Phase 5：迁移 pattern 项目

从 `../stock-pattern-search` 和 `../market_pattern_labeler` 迁移到 `research/pattern/`，只更新必要的文件系统路径，不改业务逻辑和 package 名。

Phase 5a 结论（2026-07-10）：`market_pattern_labeler` 已从 GitHub `main@3815e42` 导入
`research/pattern/market_pattern_labeler/`，编译、68 项测试、两个 CLI help、5 文件数据目录检查
和 AAPL 单股票 miner smoke 均通过。可以进入 Phase 5b 迁移 `stock-pattern-search`；默认
`../shared_data` 路径的统一收口仍留给独立任务。

输出：`_migration/logs/005_move_pattern_projects.md`。

## Phase 6：迁移 alpha_agent_system

从 `../alpha_agent_system` 迁移到 `automation/alpha_agent_system`，保持 agent 行为不变。

输出：`_migration/logs/006_move_alpha_agent_system.md`。

## Phase 7：创建三个新项目骨架

创建 `platform/data/research-data-core`、`platform/ml/research-ml-core` 和 `research/cycle/cycle-equity-research` 的最小可安装、可导入、可测试骨架。

输出：`_migration/logs/007_create_new_project_skeletons.md`。

## Phase 8：抽取通用 ML 框架

待目录迁移稳定并建立清晰测试边界后，再从 `stock-pattern-search` 逐步抽取通用 ML 能力。该工作不得与前述物理迁移捆绑。
