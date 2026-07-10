# stock-pattern-search 公共 core 渐进重构方案

## 目标

在不重写策略、不改变 Type-N/reviewer/CLI 行为的前提下，让
`research/pattern/stock-pattern-search/` 逐步使用：

- `platform/ml/research-ml-core/`
- `platform/data/research-data-core/`

最终只在 stock-pattern-search 保留策略和研究应用职责，删除已经由公共 core 稳定承接的重复实现。

## 分支策略

本轮使用独立分支：

```text
refactor/stock-pattern-search-core-adoption
```

原因：该工作会跨越多个可独立验证的提交，且 main 当前是已验证的迁移基线。每一步都必须可单独
回滚；在完整测试和关键 smoke 通过前不合并 main。

## 当前基线

- stock-pattern-search 来自原仓库 `main@806078b`。
- 迁入新仓库时完整测试：`56 passed`。
- research-ml-core：已创建但 stock-pattern-search 尚未引用。
- research-data-core：已创建但 stock-pattern-search 尚未引用。
- Type-N、reviewer、策略 configs、watchlists 和输出组织全部留在应用层。
- 旧独立仓库仍有未提交的 `scripts/run_type_n_cached_range.py` 修改，不属于本轮重构输入。

## 边界原则

### 留在 stock-pattern-search

- Type-N、new-high、Type-V、W-bottom 等策略语义
- reviewer、筛选规则、penalty 和策略评分
- 策略 pipeline、watchlist、候选结果和策略配置
- 策略专属 features、labels 和数据集构造

### 迁入或改用 research-ml-core

- 通用 classification/regression/IC metrics
- 通用 rolling、lag、return、normalization primitives
- 通用 time split
- sklearn/LightGBM/XGBoost adapter
- 与策略无关的 trainer/evaluation/backtest primitives

### 迁入或改用 research-data-core

- 工作区与 shared-data 路径解析
- dataset config/catalog
- CSV/parquet 有界读取
- 通用 schema checks 和字段标准化
- entity/time 与 point-in-time/as-of 基础能力

## 推进顺序

### Phase R0：建立等价性基线

1. 记录完整测试、CLI help 和关键 Type-N tests 基线。
2. 为第一个迁移边界添加 old-vs-core characterization tests。
3. 明确 monorepo 本地 core 的安装方式。

完成门槛：不改生产路径，新增等价性测试通过，原 56 项测试保持通过。

### Phase R1：切换通用 metrics

1. 对比 `compute_binary_metrics` 与 `research_ml_core.evaluation.classification_metrics`。
2. 让旧函数成为薄兼容 wrapper，保留函数名、参数和返回 key。
3. 全量测试并检查训练/evaluator consumer。

完成门槛：正常、单类别、阈值边界和长度错误行为一致；consumer 无修改或仅修改 import。

### Phase R2：切换低风险 schema/normalization primitives

1. 盘点 validator、normalize 和 feature normalizer 的真实契约。
2. 先补等价测试，再扩展 core 或添加应用 wrapper。
3. 每次只切一个函数族。

完成门槛：列、dtype、排序、异常类型和错误消息的兼容要求明确；完整测试通过。

R2 边界决定：`normalize_daily` 的交易单位、OHLCV 和派生字段语义属于应用数据契约，暂不迁入
research-data-core。R2a 仅先切换通用 required-column presence check，并通过 compatibility wrapper
保留应用错误消息与 `raise_on_error` 行为。

### Phase R3：切换通用 features

按 returns → lag → rolling → normalization 的顺序迁移。策略特征继续留在应用层；不为了复用而把
Type-N 参数或命名放进 core。

完成门槛：固定 fixture 上逐列数值等价，包含 NaN warm-up、窗口边界和输入不变性测试。

### Phase R4：稳定并接入 research-data-core

先处理 `_migration/backlog/research_data_core_stabilization.md` 中会影响真实 consumer 的事项，重点是：

- required columns 的 raw/canonical 语义
- available time 标准化
- bounded reads
- column mapping 冲突
- as-of 排序和 left-order 保持

之后再依次切换路径解析、schema、单文件 loader，最后才考虑 panel/as-of 数据。

完成门槛：不发生隐式全量读取；样本数、字段、时间语义和排序与旧实现一致。

### Phase R5：切换 model adapters 和 trainer

先以 logistic regression 建立序列化、predict/predict_proba、metrics 等价性，再处理 LightGBM 和
XGBoost。历史模型的加载兼容必须单独验证。

完成门槛：固定种子下预测与指标满足约定容差，现有模型加载策略明确。

### Phase R6：Type-N 与关键策略回归

1. 运行完整测试。
2. 使用 `/tmp` 输出跑受控的 Type-N 小样本/单日 smoke。
3. 对比候选集合、排序、评分和关键中间表。
4. 对 new-high 和 W-bottom 做最小回归。

完成门槛：策略输出无未解释差异，仓库内无数据或 smoke 输出。

### Phase R7：删除重复实现

只有当所有 consumer 已切换、兼容 wrapper 无调用、回归证据完整后，才删除 stock-pattern-search 内
重复模块。删除应独立提交，便于回滚。

## 每一步的固定验证

```bash
cd research/pattern/stock-pattern-search
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_type_n_task.py --help

cd ../../..
bash _migration/scripts/check_layout.sh
git diff --check
git status --short
```

涉及 core 时还应分别运行 core 自身测试。真实 smoke 输出必须写入 `/tmp`。
各项目 pytest 必须在对应项目目录执行；不要从 monorepo 根目录直接收集所有项目测试。

## 提交策略

每个阶段至少一个独立提交，推荐格式：

```text
test: characterize stock pattern metrics against ml core
refactor: route stock pattern metrics through ml core
test: characterize stock pattern data contracts
refactor: adopt research data core in stock pattern search
```

禁止把等价性测试、多个模块切换和重复代码删除压成一个大提交。

## 回滚与停止条件

出现以下任一情况就停止当前模块切换，不继续扩大范围：

- 原测试失败且原因无法归因
- Type-N 候选集合、排序或评分出现未解释变化
- 数据时间语义或 point-in-time 行为变化
- 发生无界 shared-data 扫描
- 旧模型无法加载
- 需要把策略字段或规则硬编码进公共 core

回滚单位是当前阶段提交，而不是整轮重构。

## 当前进度

- [x] 创建独立重构分支
- [x] 记录渐进方案和边界
- [x] Phase R0：metrics 等价性测试（5 项 characterization tests）
- [x] Phase R1：metrics compatibility wrapper
- [ ] Phase R2：schema/normalization
- [x] Phase R3：features（以 R3a basic indicators 为安全边界完成）
- [x] Phase R4：data core（以路径解析和 point-in-time 窗口为安全接入边界）
- [x] Phase R5：models/trainer（保留应用 artifact orchestration）
- [x] Phase R6：策略回归
- [ ] Phase R7：删除重复实现

### R0 验证记录（2026-07-11）

- metrics old-vs-core characterization：`5 passed`
- stock-pattern-search 完整测试：`61 passed, 7 warnings`
- Type-N CLI help：通过
- research-ml-core 测试：`5 passed`

曾从 monorepo 根目录误运行一次 core venv 的 pytest，因跨项目未安装依赖和同名测试模块产生收集
错误；回到 `platform/ml/research-ml-core/` 后 core 自身 `5 passed`。该错误不属于产品回归，也未导致
代码修改。

### R1 验证记录（2026-07-11）

- `requirements-monorepo.txt` 可从 stock-pattern-search 目录安装本地 ml-core
- `compute_binary_metrics` 已成为保留旧函数名、参数和返回 key 的 thin wrapper
- metrics characterization：`5 passed`
- stock-pattern-search 完整测试：`61 passed, 7 warnings`
- Type-N CLI help：通过
- research-ml-core 测试：`5 passed`

### R2a 进度（2026-07-11）

- [x] 为 daily/labels required-column behavior 添加 3 项 compatibility tests
- [x] validator 通过 thin compatibility helper 调用 research-data-core `require_columns`
- [x] 保留原缺字段顺序、错误消息和 `raise_on_error=False` 返回行为
- [x] `requirements-monorepo.txt` 增加本地 research-data-core 安装
- [ ] normalization 和 quality checks 继续留在应用层，待后续逐项判断是否存在真正通用边界

验证：schema/validator targeted `7 passed`；stock-pattern-search 完整测试 `64 passed, 7 warnings`；
research-data-core `8 passed`；Type-N CLI help 通过。

### R3a 进度（2026-07-11）

- [x] ml-core returns 增加可配置 missing-value fill，兼容 pandas 2.x/3.x
- [x] ml-core rolling features 增加通用 `min_periods` 参数
- [x] 添加 3 项 basic-indicator old-vs-core characterization tests
- [x] `add_basic_indicators` 通过兼容映射生成原 `ret_1d/ma_5/ma_20` 列
- [x] 保留日期清洗、排序、输入不变性、缺列错误和 warm-up 行为
- [ ] `build_tabular_features` 仍包含应用特征组合，后续逐项判断，不整体搬入 core

验证：feature/dataset targeted `5 passed`；stock-pattern-search 完整测试 `67 passed, 7 warnings`；
research-ml-core `6 passed`；Type-N CLI help 通过。

R3 边界结论：

- `build_tabular_features` 输出 breakout distance、volume spike、above-MA ratio 等应用特征向量，
  继续保留在 stock-pattern-search。
- Type-N/reviewer 内的 returns、scoring 和 penalty 具有策略参数与业务语义，不迁入 ml-core。
- `build_window_by_asof_date` 属于 point-in-time 数据窗口能力，留到 R4 与 data-core 的时间语义一起评估。
- 因此 R3 不以“删除 features 目录”为目标；已接入的 returns/rolling primitives 是本阶段明确且
  可验证的通用边界。

### R4 结果（2026-07-11）

data-core stabilization：

- [x] 固定 `columns=canonical→source`、`required_columns=raw source` 语义
- [x] `available_time_col` 可标准化为 `available_time`
- [x] parquet-by-entity 默认禁止无界读取，必须给 `max_files` 或显式 `allow_full_scan=True`
- [x] column mapping 检测重复 target 和覆盖冲突
- [x] entity-aware as-of 默认保持 left 原始行顺序
- [x] 新增通用、无未来数据的 `build_history_window`
- [ ] 单个超大 parquet/CSV 的真正 pushdown/分批读取留给有真实 consumer 的后续优化
- [ ] shared-data-relative DatasetConfig path、列裁剪和 check_shared_data size UX 暂不影响本 consumer

stock-pattern-search adoption：

- [x] 6 项 window characterization/既有测试通过后，以 wrapper 接入 `build_history_window`
- [x] Type-N task、cached-range 和 scan wrapper 默认路径改用 data-core shared-data resolver
- [x] W-bottom 训练/推理默认 US daily 路径改用 data-core resolver
- [x] 支持 `STOCK_RESEARCH_SHARED_DATA_DIR` 环境变量覆盖
- [x] 保留 `DailyDataLoader` 和 `normalize_daily`，因为其文件命名和单位转换属于应用契约
- [x] 不接入 DatasetCatalog/Loader：现有 strategy configs 尚未转换为 DatasetConfig，强切会扩大范围

验证：research-data-core `11 passed`；window/路径及相关 pipeline targeted tests 通过；
stock-pattern-search 完整测试 `73 passed, 7 warnings`；Type-N、cached-range、scan CLI help 均通过。

R4 以已验证的路径和时间窗口边界完成。未完成的 data-core backlog 项继续作为后续按真实 consumer
需求处理的性能/API 工作，不阻塞进入 R5。

### R5 结果（2026-07-11）

ml-core stabilization：

- [x] `SklearnAdapter` 作为已有 estimator 的统一 fit/predict/proba 边界
- [x] LightGBM/XGBoost adapters 保持 optional dependency 延迟导入
- [x] 增加 raw estimator pickle save/load，格式与旧 `model.pkl` 兼容
- [x] core Trainer score 支持 `predict_proba` 和 predict-only fallback
- [x] research-ml-core 测试扩展到 `8 passed`

stock-pattern-search adoption：

- [x] logistic wrapper 继承 `SklearnAdapter`
- [x] LightGBM/XGBoost wrappers 分别继承对应 core adapter
- [x] 三类 wrapper 继续保留 `model_name`、factory、旧 save/load API
- [x] 三类模型均完成小样本 factory → fit → pickle → load → predict_proba 往返
- [x] application Trainer 的 fit/score 通过 core Trainer，metrics/artifact 文件仍由应用层组织
- [x] Predictor 继续读取原 `model.pkl/model_meta.json/normalizer.pkl` 契约

验证：model/predictor/W-bottom targeted `12 passed`；三类 registered-model roundtrip `6 passed`；
stock-pattern-search 完整测试 `79 passed, 10 warnings`；research-ml-core `8 passed`；Type-N CLI help
通过。warnings 为既有 LightGBM feature-name 提示和本机物理核心探测提示。

限制：迁移时按规则未复制旧 outputs/models，因此无法对真实历史模型文件做全量加载回归。本阶段已
证明 pickle 格式双向兼容和三类新建模型往返；真实历史 artifact smoke 留到 R6 在明确模型来源后执行。

R5 不迁移 W-bottom 的 joblib ensemble artifact 编排，也不把 metrics JSON、predictions CSV、
normalizer 或 model metadata 写入 core；这些是应用 pipeline 的复现契约。

### R6 结果（2026-07-11）

历史模型来源：

- 旧独立项目：`../stock-pattern-search`，HEAD `806078b`
- 旧项目当前仍有既有未提交修改：`scripts/run_type_n_cached_range.py`，本轮未改动
- Phase1 历史模型：
  - `outputs/models/type_n/phase1_breakout/lgbm_v5_no_runupscore7_w150`
  - `outputs/models/type_n/phase1_breakout/xgb_v5_no_runupscore7_w150`
- Phase2 历史模型：
  - `outputs/models/type_n/phase2_pullback/lgbm_fastdrop_15k_w150`
  - `outputs/models/type_n/phase2_pullback/xgb_fastdrop_15k_w150`

受控 smoke 设置：

- raw daily cache：`storage/shared_data/raw/daily/parquet_daily_cache_20241001_20260604`
- symbols：`4,949` 个 parquet 文件
- target date：`2026-06-01`
- anchor start date：`2026-05-29`
- `phase1_top_n=5`，`window_size=150`，`min_history=1`
- 所有输出写入 `/tmp/stock-pattern-r6-*`
- 曾尝试 `target_date=2026-06-01` 且无更早 anchor 的同日设置，旧/新均失败：
  `No anchor dates available before target_date=2026-06-01`。这是无效测试输入，不是回归。

旧工程 vs 新工程输出对比：

- Phase1 no-reviewer CSV hash 均为
  `25f32e77463938010792191311431b92c30e459edf91961bf47846185f16f6c1`
- Phase1 pool CSV hash 均为
  `68da520e2adcd33f5bceb143e862bfdb2fa2ed67cb358c415402771d1530aa4e`
- Phase2 CSV hash 均为
  `ecc877040c101f24ebb7eebe246c994cddc965fd6186fc92c83fd813d0c8beb6`
- final candidates CSV hash 均为
  `162ccec873d2115b6c40c52b4c12519be09e3636eaa73a83e1beaf0076f2e66f`
- Phase1 reviewer CSV hash 均为
  `e42bfb9df6820ec768127a529ca72f1b4084319b61f58f5204c677a723f411b8`
- candidate set、排序和主要评分列最大绝对差异均为 `0`

R6 发现并修复了一个迁移路径兼容问题：

- 旧 reviewer config `phase1_short_burst_strength_2026-03-02.yaml` 中仍使用
  `../shared_data/raw/daily/parquet_daily_cache_20250701_20260528`
- 旧工程 cwd 下该路径可通过 `../shared_data` 兼容软链命中；新 monorepo cwd 下会解析到
  `research/pattern/shared_data`，导致 overhang 数据未读到，因子退化为 `1.0`
- 修复：reviewer post-penalty 的私有路径解析保持已有 project-root 相对路径优先；当相对路径不存在且
  包含 `shared_data` 时，回退到 `research-data-core` 的 canonical shared-data resolver
- 新增测试：`tests/test_reviewer_shared_data_paths.py`

验证：

- reviewer shared-data path regression：`1 passed`
- reviewer/build-candidates targeted：`12 passed`
- new-high/W-bottom targeted：`11 passed, 7 warnings`
- stock-pattern-search 完整测试：`80 passed, 10 warnings`
- research-data-core：`11 passed`
- research-ml-core：`8 passed`
- Type-N CLI help：通过

残留风险：

- 新代码加载旧 XGBoost pickle 时会出现 XGBoost 官方版本兼容 warning；本次真实 Phase1/Phase2 smoke
  均已成功加载并字节级对齐，但后续应考虑用旧版本导出 `Booster.save_model` 格式再归档。
- Arrow CPU cache 探测和 joblib 物理核心探测 warning 来自本机沙箱/运行环境，不影响本次回归结论。
