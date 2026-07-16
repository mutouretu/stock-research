# CF Industries 周期股研究路线图

## 1. 文档目标

本文档定义 CF Industries（`CF`）周期股研究的分阶段实施方案。研究从真实数据和可解释的氮肥经济性出发，逐步形成周期状态判断、中周期估值、规则型评分，最后再引入时间序列模型和回测。

计划按以下顺序推进：

1. Milestone 1：真实数据接入与质量报告
2. Milestone 2：CF 日频、季度研究面板
3. Milestone 3：氮肥利润代理
4. Milestone 4：领先滞后和周期状态分析
5. Milestone 5：中周期估值模型
6. Milestone 6：规则型观察/买入评分
7. Milestone 7：时间序列模型与回测

前 3 个 Milestone 解决数据、口径和经济含义；Milestone 4 至 6 将研究结论转化为可重复执行的判断；Milestone 7 负责检验增量预测价值，不反过来替代基本面逻辑。

---

## 2. 总体研究框架

CF 的核心传导链定义为：

```text
农产品价格、种植利润与种植面积
                ↓
北美氮肥需求、采购节奏与季节性
                ↓
尿素、UAN、氨价格及全球氮肥边际成本
                ↓
CF 产品售价 × 销量 - 天然气及其他成本
                ↓
毛利、EBITDA、自由现金流和资本回报
                ↓
中周期盈利、估值位置和市场预期差
                ↓
观察/买入评分、时间序列验证和回测
```

研究最终需要回答四个问题：

1. CF 当前处于氮肥周期的哪个阶段？
2. 未来两个至六个季度的盈利方向和主要风险是什么？
3. 当前股价隐含的中周期盈利假设是否合理？
4. 当前是否满足可执行的观察或买入条件？

---

## 3. 全程适用的工程原则

### 3.1 模块边界

- `market-data-hub`：外部数据下载、原始快照、清洗和标准化。
- `research-data-core`：通用数据 contract、加载、校验和 as-of 对齐。
- `cycle-equity-research`：CF 业务口径、特征、面板、分析、评分和报告。
- `storage/shared_data`：长期共享数据和标准化数据产物。

研究应用不得绕过 `market-data-hub` 长期维护独立下载逻辑；通用数据层不得包含 CF 特有的产品换算或投资规则。

### 3.2 Point-in-time 规则

每条非行情记录至少保留：

```text
observation_date   数据所描述的经济日期
period_end         财务或统计期间截止日（如适用）
available_time     当时市场能够获得数据的时间
retrieved_at       本地实际抓取时间
source             来源
series_id          来源序列标识
vintage            数据版本或修订批次（如适用）
```

约束如下：

- 财务数据只能从 filing/announcement date 之后使用。
- USDA 面积、成本和供需数据按发布日期进入研究面板，不能按统计期末提前使用。
- 修订数据保留 vintage；历史分析默认使用当时已知版本。
- 日终行情产生的信号默认最早在下一交易日执行。
- 所有前向收益目标与特征窗口严格错开。

### 3.3 原始值与派生值分离

- 原始单位和原始字段必须保留。
- 单位换算、指数、利润代理和评分写入派生层。
- 任何估算字段必须带 `method` 或版本标识。
- 报告不得把代理指标表述成 CF 的真实经营数据。

### 3.4 阶段闸门

每个 Milestone 只有在验收标准满足后才进入下一个阶段。允许后续阶段发现问题后回补数据，但不得跳过质量报告直接建模。

---

## 4. Milestone 1：真实数据接入与质量报告

### 4.1 目标

建立最小但真实、可更新、可追溯的数据底座，并自动回答：数据是否存在、覆盖多久、何时更新、缺失多少、单位是否一致、能否进行 point-in-time 分析。

本阶段只做数据接入、标准化和质量审计，不构建利润代理、投资评分或预测模型。

### 4.2 数据范围和优先级

#### P0：必须接入

| 数据组 | 主要数据 | 频率 | 首选来源 | 用途 |
|---|---|---:|---|---|
| CF 行情 | OHLCV、复权价格、公司行动 | 日 | 现有 Yahoo Chart 管线 | 股票收益和市值 |
| 天然气 | Henry Hub 现货 | 日 | EIA | CF 原料成本代理 |
| 全球尿素 | 尿素价格 | 月 | World Bank Pink Sheet | 长周期全球基准 |
| 美国肥料 | 无水氨、尿素、28%/32%液氮 | 周/双周 | USDA AMS | 北美终端价格代理 |
| 农产品 | 玉米、大豆价格 | 日或月 | 既有市场数据源/USDA | 农户收入和相对利润 |
| 种植面积 | 玉米、大豆 planted acres | 年内多次发布 | USDA NASS | 氮肥需求基础 |
| 农业利润 | 玉米、大豆成本与回报 | 年/预测更新 | USDA ERS | 农户支付能力 |
| CF 财务 | 三大报表、股份、现金和债务 | 季 | SEC XBRL | 盈利、现金流与 EV |
| CF 运营 | 产品售价、销量、产量、实际气价 | 季 | CF IR、10-Q、10-K | 季度经营桥 |

#### P1：M1 可选，最迟 M3 前接入

| 数据组 | 数据 | 作用 |
|---|---|---|
| 海外天然气 | TTF 或欧洲天然气代理 | 全球边际氮肥成本 |
| LNG | 美国 LNG 出口、设施投产/停运 | Henry Hub 与全球气价连接 |
| 农业供需 | WASDE 库存、消费和农场价格 | 农产品供需状态 |
| 种植进度 | Crop Progress | 春耕节奏和天气冲击 |
| 行业基准 | NOLA 尿素、UAN、坦帕氨 | 更贴近 CF 实现价格 |

商业数据源（如 Green Markets、Argus、CRU、ICIS）不作为 M1 阻塞项。免费数据验证研究价值后，再决定是否采购。

### 4.3 标准化字段

商品和农业价格表至少包含：

```text
series_id
product
geography
market_level       global / wholesale / distributor / retail / company_realized
price_basis        spot / ask / average / realized
value
unit
currency
observation_date
available_time
retrieved_at
source
vintage
```

CF 运营表至少包含：

```text
fiscal_period
period_start
period_end
filing_date
product
metric
value
unit
source_document
source_table
retrieved_at
extraction_method
```

### 4.4 数据质量检查

统一质量报告至少覆盖：

- 文件和 schema 是否存在；
- 最早、最晚 observation/available time；
- 总行数、实体数和唯一键重复；
- 关键字段缺失率；
- 日期连续性和异常缺口；
- 更新时效和距最新数据的天数；
- 价格非正数、极端跳变和单位漂移；
- 同一 series 是否混入多个单位或价格口径；
- 财务期、发布日期和重复申报是否合理；
- vintage 是否可区分初值和修订值；
- CF 季度值与年度累计值是否能够勾稽；
- 产品销量、售价和销售额之间的数量级是否合理。

质量问题按以下等级输出：

```text
ERROR    无法安全用于研究
WARNING  可以使用，但必须在报告中披露限制
INFO     覆盖或更新提示
```

### 4.5 产物

```text
storage/shared_data/
├── commodities/
├── agriculture/
├── fundamentals/us/CF/
└── us/raw/daily/parquet_by_symbol/

research/cycle/cycle-equity-research/
├── configs/datasets/
├── reports/data_quality/
│   ├── cf_data_quality.md
│   └── cf_data_quality.json
└── scripts/
    └── validate_cf_data.py
```

### 4.6 验收标准

- P0 数据均存在真实记录，不以 fixture 或手工示例代替。
- 每个数据集有 dataset contract、来源说明和更新命令。
- 质量报告可通过单一命令重复生成。
- 所有数据集明确 observation time、available time 和单位。
- CF 行情、Henry Hub 和尿素至少具备一个完整周期的历史覆盖，目标从 2013 年开始；来源本身不足时必须在报告中明确实际覆盖。
- CF 运营数据至少覆盖连续 20 个季度，关键表格经过抽样人工核对。
- ERROR 为零；WARNING 有明确处置说明。

### 4.7 暂不做

- 不构造“尿素价格减天然气价格”的伪利润。
- 不填补无法证实的历史价格。
- 不训练预测模型。
- 不生成买卖建议。

---

## 5. Milestone 2：CF 日频、季度研究面板

当前实现状态：已完成可运行的第一版。实际产物为
`storage/shared_data/research/cycle/CF/daily_panel.parquet` 和
`quarterly_panel.parquet`，并同时生成 lineage 与面板质量报告。

### 5.1 目标

把不同频率、不同发布日期的数据组织成两个可复用、无未来数据泄漏的研究面板。

### 5.2 日频面板

建议产物：

```text
storage/shared_data/research/cycle/CF/daily_panel.parquet
```

核心字段组：

- CF 价格、成交量和收益；
- Henry Hub、农产品及氮肥价格；
- 20/60/120 日动量和波动率；
- 春耕、追肥和秋肥季节标识；
- 最新已知的季度财务及运营指标；
- 最新已知的股份数、现金、债务和 TTM EBITDA；
- 数据新鲜度字段；
- 每个低频数据源的 `source_available_time`。

低频字段使用 backward as-of merge，只能从 `available_time` 向后传播。

### 5.3 季度面板

建议产物：

```text
storage/shared_data/research/cycle/CF/quarterly_panel.parquet
```

核心字段组：

- 产品净销售额、销售量和平均售价；
- 产品吨、营养吨和产量；
- 实际天然气成本；
- 毛利、毛利率、EBITDA、调整后 EBITDA；
- 经营现金流、资本开支和自由现金流；
- 库存和库存天数；
- 季度内外部商品价格均值、末值和波动；
- 季度内农产品及种植信号；
- filing-date 时点的 EV 和估值倍数。

### 5.4 面板测试

- 唯一键分别为交易日和财务季度。
- 任一低频值的 available time 不晚于面板日期。
- 季度流量字段不得把年初至今累计值误当成单季值。
- 股票拆分和分红处理前后一致。
- 财务重述有明确版本选择规则。
- 随机抽取至少 10 个日期，人工复核当时可见数据。

### 5.5 验收标准

- 两张面板由单一 pipeline 可重复构建。
- 面板 schema 固定并有测试。
- point-in-time 审计通过。
- 面板构建报告说明每个字段来源、覆盖率和填充方式。
- 后续特征代码不再直接读取原始网页或外部 API。

---

## 6. Milestone 3：氮肥利润代理

当前实现状态：已完成 v1.0.0。日频与季度代理分别输出到
`storage/shared_data/research/cycle/CF/nitrogen_economics/`，模型参数、验证结果和失效场景均版本化保存。

### 6.1 目标

构造具备明确经济含义、单位一致、可与 CF 实际季度经营数据校准的氮肥利润代理。

### 6.2 单位标准化

同时保留原始口径和标准口径：

- metric ton 与 short ton；
- product ton 与 nutrient ton；
- 氨、尿素、UAN 的含氮比例；
- FOB、CFR、经销商和 CF realized price；
- 美元/吨与美元/MMBtu。

换算系数集中配置、版本化并有单元测试，不散落在分析代码中。

### 6.3 三层利润代理

#### 第一层：价格/成本相对状态

```text
fertilizer_gas_ratio = standardized_fertilizer_price / henry_hub_price
```

优点是简单、历史长；缺点是没有真实美元利润含义。

#### 第二层：理论现金价差

```text
theoretical_cash_spread
    = product_price_per_standard_ton
    - henry_hub_price * configured_gas_intensity
```

天然气强度必须来自可解释的行业假设或公司数据，并输出高、中、低三种情景，不伪装成精确值。

#### 第三层：CF 实际利润代理

```text
cf_realized_spread
    = cf_realized_product_price
    - allocated_realized_gas_cost
    - identified_variable_costs
```

利用 CF 披露的实际售价、实际天然气成本、产品结构和销量进行季度校准。

### 6.4 氮肥指数

建立两个互不混淆的指数：

```text
global_fertilizer_index
    全球肥料或尿素长周期基准

cf_nitrogen_basket
    固定基期 CF 产品权重 × 氨、尿素、UAN 价格指数
```

`cf_nitrogen_basket` 使用固定基期的产品吨或营养吨权重，不使用当期销量动态加权，以免把销量变化混入价格指数。

### 6.5 验证方法

- 与 CF 产品实际售价做同期和领先滞后相关；
- 与分产品毛利、合计毛利和 EBITDA 做季度回归；
- 检查高低价周期中的残差方向；
- 分析运输、套保、产品结构和地区基差造成的偏差；
- 保留每版公式和参数，避免结果不可复现。

### 6.6 验收标准

- 所有利润代理有单位、公式、参数和版本。
- 外部市场价格与 CF 实际售价严格区分。
- 代理能够解释 CF 季度毛利变化的主要方向。
- 提供误差分解和已知失效场景。
- 报告同时呈现理论值、实际值和残差，而不是只报告相关系数。

---

## 7. Milestone 4：领先滞后和周期状态分析

### 7.1 目标

识别各类变量对 CF 售价、盈利和股价的领先关系，并形成可解释的周期状态定义。

### 7.2 分析对象

```text
外部氮肥价格 → CF 实际售价
Henry Hub / TTF → 氮肥价格和 CF 毛利
玉米利润 / 种植面积 → 北美氮肥需求和 CF 销量
氮肥利润代理 → CF EBITDA
盈利预期变化 → CF 股价和估值
```

### 7.3 方法

- 同频化后的 cross-correlation；
- 1 至 12 个月或 1 至 4 个季度的 distributed lags；
- rolling correlation 和稳定性检查；
- 春耕、秋肥及非施肥季分别估计；
- 按高低气价、供给冲击和库存状态分组；
- 事件窗口分析；
- 使用发布日期而非统计期末计算领先关系。

相关关系只作为线索，不直接解释为因果关系。

### 7.4 周期状态

先建立规则型状态机，不使用聚类结果直接命名经济周期：

```text
RECOVERY       氮肥价格改善，利润代理转正，盈利仍处低位
EXPANSION      价格、价差和盈利同步上升
PEAK_RISK      高利润、高估值，但价格动量或需求开始转弱
CONTRACTION    价格、价差和盈利下降
TROUGH         低利润、低估值，供给收缩或需求预期开始改善
MIXED          关键信号冲突，暂不归类
```

每个状态由明确阈值、持续期和退出条件定义，避免单日跳变。

### 7.5 验收标准

- 领先期在不同历史子样本中方向基本稳定。
- 对不稳定指标明确降权或剔除。
- 每个周期状态可以由原始指标复算。
- 状态切换有最小持续时间和滞回规则。
- 输出历史状态时间轴和典型季度复盘。

---

## 8. Milestone 5：中周期估值模型

### 8.1 目标

避免用周期顶部 EBITDA 机械计算低倍数，建立基于中周期盈利和情景假设的估值框架。

### 8.2 盈利口径

至少区分：

```text
reported_ttm_ebitda
adjusted_ttm_ebitda
mid_cycle_ebitda
downside_ebitda
upside_ebitda
```

中周期 EBITDA 从标准化产品售价、销量、天然气成本和固定成本推导，而不是简单使用历史平均净利润。

### 8.3 估值方法

主方法：

- EV / 中周期 EBITDA；
- 中周期自由现金流收益率；
- 情景化 DCF 或资本回报框架。

辅助方法：

- 历史估值百分位；
- 盈利周期状态条件下的估值分布；
- 市值对应的隐含氮肥价格或隐含 EBITDA。

### 8.4 关键一致性

- 合并 EBITDA 与 EV 中非控股权益口径一致。
- 净债务使用当时最新可见财务数据。
- 调整后 EBITDA 的公司自定义项目单独列示。
- 资本开支区分维持性、增长性和低碳项目支出。
- 回购导致的股份变化按当时已知股份数处理。

### 8.5 输出

```text
当前周期状态
当前 TTM 与中周期 EBITDA
下行 / 中性 / 上行情景
对应企业价值、股权价值和每股价值
当前价格隐含的 EBITDA / 氮肥价格假设
主要敏感性和失效条件
```

### 8.6 验收标准

- 能从产品价格和成本假设复算 EBITDA。
- 能从 EBITDA 复算企业价值和每股价值。
- 情景参数有历史范围约束。
- 历史回看时不使用未来财务数据。
- 估值输出包含区间，不输出伪精确单点目标价。

---

## 9. Milestone 6：规则型观察/买入评分

### 9.1 目标

把周期、盈利方向、估值和风险信息组合成透明、可审计的观察/买入评分。

### 9.2 建议评分结构

总分 100，初始权重建议为：

| 维度 | 权重 | 主要内容 |
|---|---:|---|
| 周期改善 | 25 | 氮肥价格、利润代理和状态切换 |
| 需求与季节 | 15 | 玉米利润、种植面积、采购窗口 |
| 盈利修正 | 20 | CF 实际售价、销量、EBITDA方向 |
| 中周期估值 | 25 | EV/中周期EBITDA、FCF收益率 |
| 风险与确认 | 15 | 气价、供给恢复、事件和趋势确认 |

### 9.3 输出等级

```text
0–39    回避/等待
40–59   观察
60–74   重点观察
75–89   满足分批买入条件
90–100  极端机会，但仍受风险闸门约束
```

区间只作为初始假设，必须通过历史案例和后续回测校准。

### 9.4 风险闸门

即使总分较高，以下条件可阻止买入信号：

- 数据过期或存在 ERROR；
- 周期信号相互冲突；
- 重大公司事件尚未纳入模型；
- 估值依赖明显超出历史区间的假设；
- 流动性、财务或治理风险触发；
- 信号仅由单一极端指标驱动。

### 9.5 验收标准

- 每一分都能追溯到输入指标和规则。
- 分数变化能解释为具体经济变化。
- 规则版本化，参数变更有记录。
- 在典型历史周期中符合基本面常识。
- 输出观察条件、触发条件和失效条件，不只输出总分。

---

## 10. Milestone 7：时间序列模型与回测

### 10.1 目标

检验统计模型是否在规则框架之外提供稳定的增量信息，并评估研究信号在真实可执行条件下的历史表现。

### 10.2 建模顺序

先预测经营指标，再预测股票收益：

1. 下一季度 CF 产品售价；
2. 下一季度销量和 EBITDA；
3. 未来 3/6/12 个月收益或超额收益；
4. 回撤风险和状态转移概率。

### 10.3 候选模型

- 季节性 naive 和历史均值基线；
- 线性/岭回归与 distributed lag；
- ARIMAX 或动态回归；
- 状态转换模型；
- 树模型仅在样本和特征稳定后使用。

季度样本较少，不以复杂度作为目标。任何复杂模型必须显著优于简单基线，并保持经济方向合理。

### 10.4 验证设计

- expanding 或 rolling walk-forward；
- 每个训练截面仅使用当时可见 vintage；
- 超参数只在训练窗口内选择；
- 保留模型训练、信号产生和交易执行三种时间；
- 纳入交易成本和下一交易日执行；
- 与买入持有、估值规则和周期规则分别比较；
- 按不同周期状态报告表现。

### 10.5 评估指标

经营预测：

- MAE、RMSE、方向准确率；
- 对简单基线的增量改进；
- 高低周期分组误差。

投资回测：

- CAGR、最大回撤、Sharpe/Sortino；
- 胜率、盈亏比、持有期和换手；
- 相对 CF 买入持有及行业基准的超额收益；
- 不同状态、年份和参数扰动下的稳定性。

### 10.6 验收标准

- 通过严格 walk-forward 和 point-in-time 审计。
- 简单基线、规则模型和统计模型可以并列比较。
- 结果不依赖单次极端周期或少数交易。
- 参数小幅变化不会导致结论完全反转。
- 若模型没有稳定增量价值，保留规则框架并明确否定结果。

---

## 11. Milestone 依赖关系

```text
M1 真实数据与质量
        ↓
M2 日频/季度面板
        ↓
M3 氮肥利润代理
        ↓
M4 领先滞后与周期状态
        ↓
M5 中周期估值
        ↓
M6 规则型评分
        ↓
M7 时间序列模型与回测
```

允许的并行工作仅限于不改变主依赖的任务，例如 M1 期间可以整理历史 CF 披露模板，但 M3 不得在 M2 point-in-time 面板验收前形成正式研究结论。

---

## 12. 版本和产物约定

每次正式分析运行记录：

```text
run_id
code_commit
config_version
data_asof
dataset_vintages
feature_version
model_or_rule_version
generated_at
```

建议研究产物结构：

```text
research/cycle/cycle-equity-research/
├── configs/
│   ├── datasets/
│   ├── instruments/
│   ├── features/
│   ├── valuation/
│   └── scoring/
├── docs/
├── reports/
│   ├── data_quality/
│   ├── cycle_state/
│   ├── valuation/
│   └── backtests/
├── scripts/
├── src/cycle_equity_research/
└── tests/
```

大型数据和生成报告是否提交 Git 按仓库约定执行；代码、配置、schema、数据字典和小型审计摘要应纳入版本控制。

---

## 13. 第一轮执行建议

正式实施从 M1 的以下顺序开始：

1. 固化数据字典、单位字典和 point-in-time 字段。
2. 盘点现有 CF 行情数据并生成基线质量报告。
3. 接入 EIA Henry Hub。
4. 接入 World Bank 尿素和 USDA AMS 肥料价格。
5. 接入 USDA NASS/ERS 农业数据。
6. 接入 SEC 标准财务。
7. 解析 CF 产品运营表格并进行人工抽样核对。
8. 生成 M1 总质量报告并处理全部 ERROR。

在 M1 验收前，不开始利润代理和投资结论开发。

### 13.1 当前实施状态

截至 2026-07-16，M1 第一批实现已经包括：

- CF 日行情下载与标准化输出；
- Henry Hub 日频现货下载与保守 available-time 处理；
- World Bank Pink Sheet 月度尿素解析；
- SEC Company Facts 下载与长表标准化；
- Markdown/JSON 统一数据质量报告。

尚未完成的 P0 接入包括 USDA AMS 肥料报价、玉米/大豆价格、NASS 种植面积、ERS
作物成本利润和 CF 分产品运营数据。SEC 真实下载还要求本地配置带联系人信息的
`SEC_USER_AGENT`。当前状态是 M1 开发中，不满足 M1 验收条件。
