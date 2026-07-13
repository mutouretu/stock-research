# stock-research

`stock-research` 是一个统一的股票研究工程，按职责组织市场数据、研究数据接口、机器学习基础能力、形态研究、周期股研究、自动化任务和本地共享数据。

仓库根目录就是正式的 `stock-research` 工作区，不再使用 `migration` 作为临时工程目录。历史迁移记录仍保存在 `_migration/`，仅用于追溯，不参与日常运行。

## 设计目标

- 将外部数据下载、清洗和标准化集中在数据平台层。
- 通过稳定的数据 contract 为不同研究项目提供统一、只读的数据接口。
- 将通用机器学习能力与具体选股策略解耦。
- 让形态研究、周期股研究和后续研究方向保持独立边界。
- 将大体量本地数据统一放在 `storage/shared_data/`，避免重复存储和提交到 Git。
- 让任务、脚本、配置、测试和研究文档具备清晰的归属。

## 目录结构

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
│   │   ├── market_pattern_labeler/
│   │   └── stock-pattern-search/
│   └── cycle/
│       └── cycle-equity-research/
├── automation/
├── storage/
│   └── shared_data/
├── ops/
│   ├── jobs/
│   └── scripts/
├── docs/
└── _migration/
```

## 数据平台

### market-data-hub

[`platform/data/market-data-hub/`](platform/data/market-data-hub/) 负责所有外部数据接入和标准化，包括：

- A 股与美股行情下载；
- 股票基础信息、公司行动和交易数据清洗；
- Tushare、Yahoo Chart 等数据源 adapter；
- CSV、Parquet 等标准化输出；
- 全量初始化、日常增量更新和数据校验；
- CF 周期股研究所需的能源、农业和 SEC 数据接入。

研究项目不应自行访问外部数据源。新的下载逻辑应优先放在此模块，并将标准化结果写入 `storage/shared_data/`。

详见 [`market-data-hub/README.md`](platform/data/market-data-hub/README.md)。

### research-data-core

[`platform/data/research-data-core/`](platform/data/research-data-core/) 是研究项目共享的数据访问层，负责：

- dataset YAML contract 与 catalog；
- 仓库根目录和共享数据路径解析；
- CSV、Parquet 和按实体分文件数据加载；
- 字段映射、schema 校验和主键检查；
- entity、time、available time 标准化；
- mixed-frequency 数据的 as-of 对齐和历史窗口构建。

该模块只负责稳定、通用、只读的数据接口，不下载外部数据，也不包含具体研究或策略逻辑。

详见 [`research-data-core/README.md`](platform/data/research-data-core/README.md)。

## 机器学习基础层

[`platform/ml/research-ml-core/`](platform/ml/research-ml-core/) 提供与策略无关的通用机器学习能力：

- rolling、lag、return、波动率和标准化特征；
- 分类与回归标签；
- walk-forward、rolling-window 和 expanding-window 切分；
- Logistic Regression、LightGBM 和 XGBoost adapter；
- 训练器、分类/回归指标、IC 和收益序列指标。

Type-N、突破、回踩、reviewer 和具体选股规则必须保留在研究应用层，不进入 ML core。

详见 [`research-ml-core/README.md`](platform/ml/research-ml-core/README.md)。

## 形态研究

### market_pattern_labeler

[`research/pattern/market_pattern_labeler/`](research/pattern/market_pattern_labeler/) 是规则型形态候选生成与标注数据生产工具。它读取日线数据，运行 W 底、长底突破、回踩、Type-N 等 miner，导出候选事件和样本供人工复核。

它不负责行情下载或模型训练。详见 [`market_pattern_labeler/README.md`](research/pattern/market_pattern_labeler/README.md)。

### stock-pattern-search

[`research/pattern/stock-pattern-search/`](research/pattern/stock-pattern-search/) 是通用机器学习选股与策略搜索工程，提供：

- 统一的样本、特征、训练和推理协议；
- Type-N 两阶段扫描和 Phase 1 缓存；
- new-high、Type-V、W-bottom 等策略空间；
- 策略级 pipeline、reviewer、配置和输出隔离；
- A 股和美股截面扫描、候选排序及结果检查。

通用数据与 ML 能力逐步由 `research-data-core` 和 `research-ml-core` 提供，策略语义继续保留在项目内。

详见 [`stock-pattern-search/README.md`](research/pattern/stock-pattern-search/README.md)。

## 周期股研究

[`research/cycle/cycle-equity-research/`](research/cycle/cycle-equity-research/) 用于研究周期敏感型公司。当前第一个研究标的是 CF Industries（`CF`），研究链路包括：

```text
农产品价格与种植利润
  → 北美氮肥需求
  → 尿素、UAN、氨价格
  → 售价减天然气成本
  → CF 利润、现金流与估值
```

项目负责声明数据依赖、通过 `research-data-core` 加载数据、构造日频与季度面板、生成周期特征并开展后续分析。外部数据下载仍统一由 `market-data-hub` 负责。

详见 [`cycle-equity-research/README.md`](research/cycle/cycle-equity-research/README.md)。

## 自动化、运维和文档

- [`automation/`](automation/)：跨模块自动化应用和后续 agent 工作流。
- [`ops/jobs/`](ops/jobs/)：全量初始化、日常增量、周度和季度任务说明。
- [`ops/scripts/`](ops/scripts/)：仓库级运维和批处理脚本。
- [`docs/`](docs/)：架构、研究计划、数据审计和跨模块说明。
- [`_migration/`](_migration/)：已完成迁移过程的历史记录，不是当前工程入口。

## 共享数据

所有模块共用仓库根目录下的：

```text
storage/shared_data/
```

典型数据流为：

```text
外部数据源
  → market-data-hub
  → storage/shared_data
  → research-data-core
  → research applications
```

`storage/shared_data/` 中的大型数据文件默认不提交到 Git。代码和配置应使用仓库相对路径或公共路径解析器，禁止写死开发者本机绝对路径。

## 开发约定

各子项目保持独立的 `pyproject.toml`、虚拟环境和测试套件。进入对应目录后安装和测试，例如：

```bash
cd platform/data/research-data-core
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

基本原则：

1. 下载逻辑属于 `market-data-hub`。
2. 通用数据访问属于 `research-data-core`。
3. 通用 ML 能力属于 `research-ml-core`。
4. 策略和业务语义属于对应的 `research/` 项目。
5. 本地数据属于 `storage/shared_data/`，研究产物应按项目隔离。
6. 新功能应包含配置校验、单元测试和必要文档。

## 当前状态

仓库已经完成统一根目录建设、市场数据模块导入、共享数据归位、两个形态研究项目接入，以及最小数据/ML core 和周期股研究工程建设。后续开发直接在 `stock-research` 根目录内进行，不再依赖临时 `migration` 目录。
