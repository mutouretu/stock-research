# Architecture (V0)

## 仓库边界

`market_pattern_labeler` 是一个独立仓库，定位为“通用 pattern 召回器 + 轻量标注闭环”的最小起点。

当前阶段只完成：

- 读取 daily parquet（按股票文件）
- 扫描候选 pattern
- 导出候选 CSV

## 模块职责

- `data/`: 日线数据读取与基础规范化。
- `miners/`: 规则召回器。当前提供 `type_n`。
- `schemas/`: 候选输出字段协议。
- `pipelines/`: 组织全市场扫描与输出。
- `cli/`: 命令行入口。

## 为什么是这个形态

- 先最小化实现“规则 -> 候选 CSV”，让人工复核链路跑通。
- 不引入数据库、前端、训练逻辑，避免过早复杂化。
- 通过统一 miner 接口，为后续新增 `pattern_v2` 或其他 miner 留扩展位。

## 下一步可自然扩展（不在 V0 内）

- review sheet 模板（人工复核字段）
- 标注结果回收为 label CSV
- 增加更多 miner（非 type_n）
