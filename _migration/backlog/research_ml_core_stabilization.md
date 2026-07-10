# research-ml-core 后续稳定化问题汇总

## 当前结论

`research-ml-core` 当前作为最小抽象层可以先保留，不建议在整体迁移完成前立即修改。

原因：

- 当前 `research-ml-core` 状态是 `partially_extracted`。
- `stock-pattern-search` 已迁移，但尚未切换运行时 import。
- 现有 Type-N、reviewer、策略 pipeline、配置、CLI 和业务逻辑未改。
- 目前没有发现会阻塞迁移主线的明显泄露问题。
- 这些问题更适合作为整体迁移完成后的稳定化任务处理。

建议保存路径：

```text
_migration/backlog/research_ml_core_stabilization.md
```

或者：

```text
docs/technical_debt/research_ml_core_stabilization.md
```

---

## 一、抽象边界问题

### 1. `ts_code` 不应出现在 core 协议层

当前 `SampleMeta` 使用了：

```text
ts_code
asof_date
label
```

其中 `ts_code` 带有股票 / A 股语境，不适合放在跨项目通用 ML core 中。

后续建议改成：

```text
entity_id
asof_time / asof_date
target / label
```

映射关系由应用层负责：

```text
stock-pattern-search:
    entity_id = ts_code

cycle-equity-research:
    entity_id = CF / MOS / PPC

commodity / macro:
    entity_id = urea / henry_hub / corn
```

建议后续修改：

```text
SampleMeta.ts_code -> SampleMeta.entity_id

build_sample_id(ts_code, asof_date)
    -> build_sample_id(entity_id, asof_time)
```

---

## 二、多实体时间序列问题

### 2. 特征函数目前默认按单序列计算

当前以下函数是对整列直接计算：

```text
add_return_features
add_lag_features
add_rolling_features
rolling_volatility
```

单股票、单公司、单商品序列下没有明显问题。

但如果输入是 panel 数据：

```text
entity_id / date / value
```

就可能跨实体计算：

```text
收益率
lag
rolling mean
rolling std
volatility
```

这不是股票业务问题，而是多实体时间序列抽象层需要支持的问题。

后续建议增加通用参数：

```python
entity_col: str | None = None
time_col: str | None = None
```

示例：

```python
add_return_features(
    df,
    column="close",
    periods=(5, 20),
    entity_col="entity_id",
    time_col="asof_date",
)
```

股票应用层可以传：

```python
entity_col="ts_code"
time_col="trade_date"
```

CF / 周期股应用层可以传：

```python
entity_col="company"
time_col="quarter"
```

core 不应该知道 `ts_code`、`ticker`、`CF`、`尿素` 等业务字段，只应该知道 `entity_col` 和 `time_col`。

---

## 三、时间切分与未来函数风险

### 3. `walk_forward_split` 当前只是按 index 顺序切

当前 `walk_forward_split` 适合基础验证，但还不是严格防泄漏切分。

问题在于，如果目标是：

```text
forward_return_20d
forward_return_60d
```

训练集末尾样本的 label 可能使用到测试区间内的未来价格。

后续需要支持：

```text
gap
embargo
label_horizon
```

建议接口：

```python
walk_forward_split(
    n_samples,
    train_size,
    test_size,
    step=None,
    expanding=True,
    gap=0,
    label_horizon=0,
    embargo=0,
)
```

例如：

```text
train: [0, ..., 979]
gap:   [980, ..., 999]
test:  [1000, ..., 1099]
```

这样可以避免 forward label 跨进测试区间。

---

## 四、特征列选择问题

### 4. `select_feature_columns` 默认排除字段不够

当前默认排除字段偏少，可能把 label-side metadata 当成特征。

后续默认排除列表建议包括：

```text
sample_id
entity_id
ts_code
symbol
ticker
asof_date
trade_date
label
target
label_source
confidence
split
```

特别是：

```text
confidence
```

更像标注质量、样本权重或 label 元信息，不应该默认进入特征。

如果需要使用，应作为：

```text
sample_weight_col
```

而不是 feature。

---

## 五、指标计算鲁棒性问题

### 5. metrics 需要过滤缺失值和无穷值

后续以下函数应统一处理缺失和异常值：

```text
classification_metrics
regression_metrics
information_coefficient
```

需要处理：

```text
NaN
pd.NA
inf
-inf
```

否则 forward label 尾部缺失值可能导致 sklearn metrics 报错。

建议统一逻辑：

```python
valid_mask = (
    pd.notna(y_true)
    & pd.notna(y_score)
    & np.isfinite(y_score)
)
```

如果有效样本过少，应明确返回 `nan` 或抛出带说明的错误。

---

## 六、测试覆盖不足

### 6. 当前测试是 smoke 级别

当前 `research-ml-core` 测试可以证明：

```text
包能安装
函数能 import
基础示例能跑
```

但还不足以证明适合金融 / 周期股时间序列生产使用。

后续建议补充测试：

```text
1. 多实体 panel 下 return / lag / rolling 不跨实体
2. forward label 尾部 NaN 正确
3. walk-forward gap / horizon 防泄漏
4. metrics 过滤 NaN / pd.NA / inf
5. select_feature_columns 不选 metadata
6. 单类分类样本 AUC 返回 NaN 而不是崩溃
7. backtest metrics 对空序列、全 0、极端收益的处理
```

---

## 七、路径解析问题

### 7. `stock-pattern-search` 默认 shared_data 路径后续要统一

当前迁移阶段保留旧路径兼容是对的，不建议现在强改。

后续应增加统一 resolver，而不是在各处手写相对路径。

建议工具：

```python
resolve_shared_data_dir()
```

优先级：

```text
1. 环境变量 STOCK_RESEARCH_SHARED_DATA_DIR
2. 当前 monorepo 根目录 storage/shared_data
3. 旧兼容路径 ../shared_data
4. 找不到则明确报错，提示如何设置
```

这部分应该放在：

```text
research-data-core
```

或者应用层工具中。

不要放进：

```text
research-ml-core
```

因为 `research-ml-core` 不应该理解数据目录、shared_data、parquet cache 等工程路径。

---

## 八、Git ignore 补强

### 8. 根 `.gitignore` 后续可以补模型产物

当前数据文件基本已经防住了，但后续模型产物也应补充：

```gitignore
*.joblib
*.onnx
*.pt
*.pth
*.npy
*.npz
models/
**/outputs/
**/experiments/
```

尤其后续训练模型、跑 CF 项目、生成报告时，容易产生模型和中间产物，需要提前防止误提交。

---

## 九、当前不建议立即修改的原因

当前不建议立刻修这些问题，原因是：

```text
1. 整体迁移尚未完成。
2. stock-pattern-search 尚未切换到 research-ml-core。
3. 现在修改 core API 会影响后续迁移对齐。
4. 当前 core 只是 partially_extracted，不是正式生产依赖。
5. 先保持迁移主线稳定更重要。
```

这些问题应该归入 backlog，等以下工作完成后再统一处理：

```text
market-data-hub 迁移完成
shared_data 迁移完成
market_pattern_labeler 迁移完成
stock-pattern-search 迁移完成
research-data-core 创建完成
cycle-equity-research 创建完成
```

---

## 十、后续处理顺序建议

整体迁移完成后，建议按这个顺序处理：

```text
1. 创建 research-data-core
2. 创建 cycle-equity-research
3. 稳定 research-ml-core 边界
4. 增加 panel / time / gap 相关测试
5. 再逐步让 stock-pattern-search 切换到 research-ml-core
6. 最后让 cycle-equity-research 复用 research-ml-core
```

---

## 一句话结论

当前 `research-ml-core` 没有明显阻塞迁移的问题，但存在抽象层稳定化任务。

为了保证整体迁移对齐，先保留为 backlog，等所有项目迁移完成后再统一修。
