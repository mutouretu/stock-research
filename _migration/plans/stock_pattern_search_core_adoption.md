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
- [ ] Phase R3：features
- [ ] Phase R4：data core
- [ ] Phase R5：models/trainer
- [ ] Phase R6：策略回归
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
