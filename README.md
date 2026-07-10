# stock-research

新的统一股票研究工作区，用于按职责组织数据平台、机器学习基础能力、研究应用、自动化和本地数据存储。

当前本地目录可能暂时名为 `migration`，但它本身就是未来新 `stock-research` 仓库的根目录。迁移完成后，旧工作区将暂时改名为 `stock-research-old`，当前目录再改名为 `stock-research`。

## 目标结构

```text
stock-research/
├── platform/
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
├── docs/
└── _migration/
```

当前已完成仓库骨架、`market-data-hub` 导入和 `shared_data` 本地迁移；两个 pattern 项目已
导入 `research/pattern/`，并已创建最小 `platform/ml/research-ml-core/`。其余旧项目仍保留在父目录中。

## 迁移资料

- [`_migration/README.md`](_migration/README.md)
- [`_migration/move_map.yaml`](_migration/move_map.yaml)
- [`_migration/validation_plan.md`](_migration/validation_plan.md)
