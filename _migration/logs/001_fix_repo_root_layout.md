# Phase 1b：修正新仓库根目录定位

验证日期：2026-07-10

## 实施结果

- 确认当前 Git 仓库根目录就是未来新的 `stock-research` 根目录；本地文件夹名 `migration` 只是临时名称。
- 目标空骨架位于仓库根目录：`platform/`、`research/`、`automation/`、`storage/`、`ops/`、`docs/`。
- 原根目录迁移资料已收纳到 `_migration/`。
- 根 `README.md` 已改为新仓库说明，迁移专案说明位于 `_migration/README.md`。
- 新增根 `.gitignore`，排除环境文件、Python 缓存、数据库/列式数据文件及 `storage/shared_data/`。
- 未迁移、复制、删除或修改父目录中的旧项目。

## 指定验证命令

### `git status --short`

执行成功。整理尚未提交，因此 Git 将原根目录迁移资料显示为删除、将 `_migration/` 显示为新增；提交时 Git 会按内容识别相应重命名。`.DS_Store` 已被新 `.gitignore` 排除。

```text
 M README.md
 D codex_task_prompt.md
 D logs/.gitkeep
 D logs/000_inventory.md
 D move_map.yaml
 D scripts/.gitkeep
 D scripts/check_layout.sh
 D scripts/check_old_paths.sh
 D validation_plan.md
?? .gitignore
?? _migration/
```

### `find . -maxdepth 3 -type d | sort`

执行成功。除 `.git/` 内部目录外，业务相关目录为：

```text
.
./_migration
./_migration/logs
./_migration/scripts
./automation
./docs
./ops
./ops/jobs
./ops/scripts
./platform
./platform/data
./platform/ml
./research
./research/cycle
./research/pattern
./storage
```

未出现错误的 `migration/platform`、`migration/research`、`migration/automation` 或 `migration/storage` 子结构。

### `bash _migration/scripts/check_layout.sh`

退出码：`0`。15 个必需目录全部存在，最终输出：

```text
Phase 1b layout check passed.
```

### `bash _migration/scripts/check_old_paths.sh`

退出码：`0`，共输出 62 行。旧路径/名称命中来自迁移映射、计划、历史盘点和检查脚本，属于 Phase 1b 预期结果；脚本按设计不会因命中而失败。

## 旧项目保护检查

父目录中的六个旧项目/数据目录全部仍存在：

- `../market-data-hub`
- `../shared_data`
- `../stock-pattern-search`
- `../market_pattern_labeler`
- `../alpha_agent_system`
- `../build-daily-cache`

只读检查仍显示 Phase 1 盘点时已存在的未提交状态：`alpha_agent_system` 3 项、`build-daily-cache` 1 项、`stock-pattern-search` 1 项；本阶段没有修改这些旧仓库。

## 结论

Phase 1b 验证通过。新仓库根目录定位、目录骨架和迁移资料收纳均符合要求，可以进入提交评审；尚未实施任何旧项目迁移。
