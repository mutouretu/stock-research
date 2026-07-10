# stock-research 迁移专案

## 仓库定位

当前 Git 仓库根目录就是未来新的 `stock-research` 根目录。它在本机暂时可能仍叫 `migration`，这个名字只表示迁移期间的临时文件夹名，不代表未来仓库中存在一个 `migration/` 子目录。

迁移完成后的目录切换计划：

1. 将旧工作区 `stock-research/` 暂时改名为 `stock-research-old/`。
2. 将当前临时名为 `migration/` 的 Git 仓库移出并改名为 `stock-research/`。
3. 按阶段把旧项目从父目录迁移到新仓库的目标分层中。

迁移过程资料统一保存在当前仓库的 `_migration/` 下。真正的目标骨架位于当前仓库根目录的 `platform/`、`research/`、`automation/`、`storage/`、`ops/` 和 `docs/`，不是 `_migration/platform` 或 `migration/platform`。

## 迁移目标

```text
stock-research/
├── platform/
│   ├── data/
│   │   ├── market-data-hub/
│   │   └── research-data-core/
│   └── ml/
│       └── research-ml-core/
├── research/
│   ├── pattern/
│   │   ├── stock-pattern-search/
│   │   └── market_pattern_labeler/
│   └── cycle/
│       └── cycle-equity-research/
├── automation/
│   └── alpha_agent_system/
├── storage/
│   └── shared_data/
├── ops/
│   ├── jobs/
│   └── scripts/
├── docs/
└── _migration/
    ├── README.md
    ├── move_map.yaml
    ├── validation_plan.md
    ├── codex_task_prompt.md
    ├── logs/
    └── scripts/
```

## 迁移原则

1. 分阶段迁移，每阶段独立验证并记录日志。
2. 不借目录迁移重写业务逻辑或大规模修改 import。
3. 保持既有 Python package 名称，例如 `alpha_agent_system`、`market_pattern_labeler` 和 `market_data_hub`。
4. `shared_data` 是约 24 GiB 的本地数据仓库，禁止将大型数据文件加入 Git。
5. `build-daily-cache` 只有在确认功能完整合并、必要资产已处理且消费者已切换后才能删除或归档。
6. 不覆盖父目录各旧仓库中的未提交修改。
7. 每阶段验证失败必须如实写入 `_migration/logs/`。

## 当前进度

Phase 1b 已完成新仓库根目录定位修正。Phase 2 将 `market-data-hub` 从其独立 GitHub
仓库导入到根目录的 `platform/data/market-data-hub/`，保持 package、CLI 和业务逻辑不变。

Phase 3 已将本地 `shared_data` 移入 `storage/shared_data/` 并建立旧路径兼容软链接；
Phase 5a/5b 已导入两个 pattern 项目，Phase 7b 已创建最小 `research-ml-core` 并保持既有
pattern 业务 import 不变。自动化项目、`build-daily-cache`、`research-data-core` 和
`cycle-equity-research` 仍未处理。

后续阶段和验证命令见 [`validation_plan.md`](validation_plan.md)。
