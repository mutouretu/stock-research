# research-data-core 后续稳定化问题

## 当前状态

Phase 7a 已完成，research-data-core 已创建为最小数据接口层。当前没有接入现有业务项目，可以继续后续迁移。以下问题暂不阻塞迁移，等 cycle-equity-research 创建并开始接入真实 CF 数据后再处理。

## 保留问题

1. DatasetLoader 的 required_columns 当前在字段映射前检查，需要明确 required_columns 是原始字段还是 canonical 字段。
2. available_time_col 已进入 DatasetConfig，但 DatasetLoader 暂未标准化为 available_time。
3. read_parquet_by_entity_dir 在 max_files=None 时可能全量读取目录，后续应增加 iterator 或 allow_full_scan。
4. merge_asof_by_entity 会改变 left 原始行顺序，后续可增加 preserve_left_order。
5. merge_asof_by_entity 的排序语义应基于真实 panel/as-of 数据补测试。
6. check_shared_data.py 默认 du -sh 可能扫描 24GiB shared_data，后续可增加 --no-size / --include-size。
7. validate_dataset.py 缺少 --max-rows，单大文件可能被全量读取。
8. normalize_columns 未检查目标列冲突或重复 target。
9. DatasetConfig.columns 的 canonical -> source 语义需要在文档中固定。
10. DatasetLoader 当前只支持 repo-relative path，后续可支持 shared_data-relative path。
11. DatasetLoader 尚未根据 config 做列裁剪，后续大文件读取可优化。

## 暂不处理原因

- 当前 research-data-core 尚未接入业务项目。
- stock-pattern-search、market_pattern_labeler 仍按原逻辑运行。
- cycle-equity-research 尚未创建。
- 真实 CF 数据集结构尚未确定。
- 现在过早修 API 可能影响迁移对齐。

## 后续处理时机

建议在 cycle-equity-research 创建完成，并开始接入 CF price / financials / commodity datasets 后，结合真实 dataset YAML 和消费者测试统一修复。