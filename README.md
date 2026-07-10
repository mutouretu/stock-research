# stock-research 迁移专案

## 目标

将当前 `stock-research` 根目录下平铺的多个项目，迁移为按功能分层的结构。

当前结构大致为：

```text
stock-research/
    alpha_agent_system/
    build-daily-cache/
    market_pattern_labeler/
    market-data-hub/
    shared_data/
    stock-pattern-search/
```

目标结构为：

```text
stock-research/
    platform/
        data/
            market-data-hub/
            research-data-core/
        ml/
            research-ml-core/

    research/
        pattern/
            stock-pattern-search/
            market_pattern_labeler/
        cycle/
            cycle-equity-research/

    automation/
        alpha_agent_system/

    storage/
        shared_data/

    migration/
        README.md
        move_map.yaml
        validation_plan.md
        codex_task_prompt.md
        logs/
        scripts/

    ops/
        jobs/
        scripts/

    docs/
```

## 迁移原则

1. 这次迁移只做目录分层、路径更新、废弃项目清理和新项目骨架创建。
2. 不重写业务逻辑。
3. 不在本次任务中抽取 `stock-pattern-search` 的机器学习代码。
4. 保持现有 Python package import 名称不变，例如 `alpha_agent_system`、`market_pattern_labeler`。
5. `shared_data` 视为本地数据仓库，移动时要避免把大型数据文件提交到 git。
6. `build-daily-cache` 已整合进 `market-data-hub`，确认无引用后删除。
7. 每完成一个阶段，都要运行验证命令，并把结果写入 `migration/logs/`。
8. 如果验证失败，不要掩盖，直接记录失败原因和后续修复建议。

## 分层职责

| 层级 | 目录 | 职责 |
|---|---|---|
| 数据平台 | `platform/data/market-data-hub` | 外部数据接入、清洗、标准化、落盘 |
| 数据接口 | `platform/data/research-data-core` | 统一读取、schema、交易日历、频率转换、as-of merge |
| ML 核心 | `platform/ml/research-ml-core` | 特征工程、标签、时间序列切分、训练、评估、回测 |
| 技术形态研究 | `research/pattern/stock-pattern-search` | 股价形态、趋势结构、pattern search |
| 形态标注 | `research/pattern/market_pattern_labeler` | 市场形态标注工具 |
| 周期股研究 | `research/cycle/cycle-equity-research` | CF、MOS、PPC、ZIM 等周期股研究 |
| 自动化 | `automation/alpha_agent_system` | Agent workflow、自动报告、提醒、调度辅助 |
| 数据仓库 | `storage/shared_data` | 本地共享数据、cache、parquet、feature store |
| 运维入口 | `ops` | 运行脚本、cron 入口、任务触发脚本 |
| 迁移记录 | `migration` | 迁移说明、路径映射、验证计划、日志 |

## 建议迁移阶段

### Phase 0：盘点现状

只盘点，不修改代码。

输出：

```text
migration/logs/000_inventory.md
```

需要盘点：

```text
目录结构
每个项目的 pyproject / requirements / setup 文件
import 路径
入口脚本
测试命令
shared_data 是否被 git 管理
build-daily-cache 是否还有引用
```

### Phase 1：创建目标骨架

创建：

```text
platform/
research/
automation/
storage/
ops/
docs/
migration/
```

但不移动现有项目。

### Phase 2：迁移数据层

```text
market-data-hub -> platform/data/market-data-hub
shared_data -> storage/shared_data
```

注意：`shared_data` 如果是大量本地数据，优先使用普通 `mv`，不要强行 `git mv`。

### Phase 3：删除 build-daily-cache

先确认：

```bash
rg "build-daily-cache|build_daily_cache|daily-cache|daily_cache"
```

再确认 `market-data-hub` 中已经有 Tushare A 股 daily sync / cache build 能力。

确认后删除。

### Phase 4：迁移研究应用层

```text
stock-pattern-search -> research/pattern/stock-pattern-search
market_pattern_labeler -> research/pattern/market_pattern_labeler
```

只改路径，不改业务逻辑。

### Phase 5：迁移自动化层

```text
alpha_agent_system -> automation/alpha_agent_system
```

只改路径，不改 agent 逻辑。

### Phase 6：新增 research-data-core

创建骨架：

```text
platform/data/research-data-core/
    pyproject.toml
    README.md
    src/research_data_core/
    tests/test_import.py
```

第一版只做空包骨架。

### Phase 7：新增 research-ml-core

创建骨架：

```text
platform/ml/research-ml-core/
    pyproject.toml
    README.md
    src/research_ml_core/
    tests/test_import.py
```

第一版只做空包骨架，不抽取 `stock-pattern-search` 代码。

### Phase 8：新增 cycle-equity-research

创建骨架：

```text
research/cycle/cycle-equity-research/
    pyproject.toml
    README.md
    configs/instruments/CF.yaml
    src/cycle_equity_research/
    tests/test_import.py
```

第一版只建立 CF 周期股研究配置和目录。

## 验收标准

最终根目录应主要保留：

```text
stock-research/
    platform/
    research/
    automation/
    storage/
    migration/
    ops/
    docs/
    README.md
    pyproject.toml
    .gitignore
```

根目录不应再保留：

```text
alpha_agent_system/
build-daily-cache/
market_pattern_labeler/
market-data-hub/
shared_data/
stock-pattern-search/
```

其中 `build-daily-cache` 应被删除，其他项目应移动到新分层目录。
