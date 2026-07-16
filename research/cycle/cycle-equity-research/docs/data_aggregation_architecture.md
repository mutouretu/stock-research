# 数据聚合分层

CF 研究的数据聚合遵循三层边界：

1. `market-data-hub` 下载、归档、解析并标准化单一来源数据。领域目录按商品、农业、财务和公司经营披露组织；`cf_m1` 只是下载配方。
2. `research-data-core` 提供不含业务语义的 point-in-time 对齐、期间聚合和数据契约能力。
3. `cycle-equity-research` 决定 CF 使用哪些数据、如何命名研究字段、如何构建宽面板与模型就绪面板。

标准数据保存在 `storage/shared_data/{commodities,agriculture,fundamentals}`，可重复生成的研究面板保存在 `storage/shared_data/research/cycle/CF`。新增标的时应优先增加 dataset contract、面板配置和少量公司专属映射，不复制下载器或时间对齐代码。

## 时间语义

- `observation_time` 表示数据描述的经济时期。
- `available_time` 表示研究者最早可见该值的时间。
- `panel_available_time` 表示整行面板可以完整使用的时间。
- 所有低频数据只能从 `available_time` 向后传播。
- 季度商品均值只使用属于该季度且在面板截止时间前已经发布的观测。
- SEC 季度流量优先使用单季值；没有单季值时，通过当前累计值减去上期累计值还原。

每次构建会输出配置哈希、输入数据集列表、列清单和质量报告，保证面板能够复算和审计。

## 宽面板与模型就绪层

M2 的 `daily_panel.parquet` 和 `quarterly_panel.parquet` 是可审计的宽面板：它们尽量完整地保留后续研究可能使用的标准字段，不等于训练矩阵。

M2.1 在宽面板之上增加三个消费端产物：

- `core_monthly_panel.parquet`：六个白名单核心特征，用于粗粒度月频关系研究；
- `core_quarterly_panel.parquet`：五个白名单核心特征，用于经营关系校准；
- `tactical_context_panel.parquet`：AMS、种植面积、季节性和成本残差，只用于场景确认与微观诊断。

特征角色由 `cf_feature_registry.yaml` 控制，数据源质量角色由 `cf_data_roles.yaml` 控制。调用者不能因为战术数据已经出现在宽面板里，就默认将它加入基础模型。低频数据按日展开不会增加有效样本数；质量报告使用完整独立期间数和样本/特征比，而不是展开后的日频行数判断可训练性。
