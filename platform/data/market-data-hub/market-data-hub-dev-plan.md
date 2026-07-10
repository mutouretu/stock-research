# market-data-hub 开发文档：基础框架与美股数据获取

## 1. 项目定位

`market-data-hub` 是一个跨市场原始数据获取与标准化工程，目标是为上层的 `type-n` 机器学习挖掘系统提供稳定、统一、可追溯的数据输入。

它本身不负责判断“什么股票值得买”，也不做策略训练、因子打分、回测和观察列表生成。这些逻辑由 `type-n` 负责。

```text
market-data-hub  --->  标准化行情 / 股票池 / 公司行为 / 财务数据  --->  type-n
```

### 1.1 职责边界

`market-data-hub` 负责：

- 原始数据下载
- 股票池维护
- 交易日历维护
- 公司行为数据维护
- 复权数据构建
- 数据清洗和字段标准化
- 数据落盘与导出
- 每日增量更新与历史全量刷新

`type-n` 负责：

- 因子计算
- labeler 构造
- 规则筛选
- 机器学习排序
- watchlist 生成
- 回测验证
- 交易研究报告

## 2. 总体目录结构

采用如下目录结构：

```text
market-data-hub/
  README.md
  pyproject.toml

  configs/
    cn.yaml
    us.yaml
    hk.yaml

  market_data_hub/
    core/
      instruments.py
      calendars.py
      schemas.py
      storage.py
      adjustments.py

    markets/
      cn/
        adapters/
          tushare.py
        pipelines/
          download_prices.py
          download_instruments.py

      us/
        adapters/
          polygon.py
          yfinance.py
          tiingo.py
        pipelines/
          download_prices.py
          download_instruments.py
          download_corporate_actions.py

      hk/
        adapters/
          yahoo.py
          akshare.py
        pipelines/
          download_prices.py
          download_instruments.py

    exports/
      parquet.py
      postgres.py
      sqlite.py

    jobs/
      daily_update.py
      full_refresh.py
```

## 3. 第一阶段开发目标

第一阶段只做基础框架和美股数据获取，不做 A 股、港股完整接入。

### 3.1 第一阶段范围

必须完成：

- 创建项目骨架
- 建立统一 schema
- 建立配置系统
- 建立日志系统
- 建立本地 Parquet 存储
- 实现美股 ticker universe 获取
- 实现美股日线 OHLCV 下载
- 实现 adjusted OHLCV 标准化
- 实现基础公司行为字段保留
- 实现每日增量更新入口
- 实现全量刷新入口
- 输出可被 `type-n` 读取的标准化数据

暂不完成：

- 实时行情
- 分钟线行情
- 期权数据
- 新闻数据
- 财务报表数据
- A 股完整数据迁移
- 港股完整数据接入
- 数据质量自动修复
- 严格 point-in-time 财务数据对齐
- 机器学习特征工程

## 4. 技术选型

### 4.1 Python 版本

建议使用：

```text
Python >= 3.11
```

原因：

- 类型注解体验较好
- pandas / polars / pyarrow 支持成熟
- 适合后续和 `type-n` 共用数据处理环境

### 4.2 依赖建议

第一阶段建议依赖：

```toml
[project]
name = "market-data-hub"
version = "0.1.0"
description = "Cross-market data ingestion and normalization hub for type-n."
requires-python = ">=3.11"
dependencies = [
  "pandas>=2.2",
  "pyarrow>=15.0",
  "pydantic>=2.0",
  "pydantic-settings>=2.0",
  "typer>=0.12",
  "rich>=13.0",
  "loguru>=0.7",
  "httpx>=0.27",
  "tenacity>=8.2",
  "yfinance>=0.2",
  "python-dotenv>=1.0",
]
```

后续可选：

```toml
optional-dependencies = {
  polars = ["polars>=1.0"],
  postgres = ["sqlalchemy>=2.0", "psycopg[binary]>=3.1"],
  duckdb = ["duckdb>=1.0"],
  dev = ["pytest>=8.0", "ruff>=0.5", "mypy>=1.10"]
}
```

## 5. 数据源策略

### 5.1 第一阶段默认数据源

第一阶段建议使用 `yfinance` 作为原型数据源。

原因：

- 接入简单
- 可快速批量下载日线行情
- 适合验证数据框架和标准化流程
- 不需要先购买付费数据

注意：

- `yfinance` 不适合作为长期生产级唯一数据源
- 数据授权、稳定性、接口变化需要注意
- 后续应保留 Polygon / Tiingo 等正式数据源适配器

### 5.2 第二阶段正式数据源候选

建议预留：

- Polygon / Massive：适合美股行情、公司行为、批量历史数据、Flat Files
- Tiingo：适合 EOD 行情、调整价格、dividend/split 字段、ticker 元数据
- FMP：适合行情 + 财务 + 指标一体化
- Sharadar：适合严肃回测、delisted stocks、基本面 point-in-time 数据

第一阶段代码不绑定具体供应商，要通过统一 adapter 接口抽象。

## 6. 核心数据模型

### 6.1 Instrument

用于表示一个交易标的。

```python
from datetime import date
from pydantic import BaseModel

class Instrument(BaseModel):
    instrument_id: str
    symbol: str
    market: str              # CN / US / HK
    exchange: str | None = None
    name: str | None = None
    asset_type: str = "stock" # stock / etf / reit / adr / index
    sector: str | None = None
    industry: str | None = None
    currency: str | None = None
    is_active: bool = True
    list_date: date | None = None
    delist_date: date | None = None
    source: str
```

### 6.2 DailyBar

用于表示日线行情。

```python
from datetime import date
from pydantic import BaseModel

class DailyBar(BaseModel):
    instrument_id: str
    symbol: str
    market: str
    trade_date: date

    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    amount: float | None = None

    adj_open: float | None = None
    adj_high: float | None = None
    adj_low: float | None = None
    adj_close: float | None = None
    adj_volume: float | None = None

    dividend: float | None = None
    split_factor: float | None = None

    source: str
```

### 6.3 CorporateAction

用于表示公司行为。

```python
from datetime import date
from pydantic import BaseModel

class CorporateAction(BaseModel):
    instrument_id: str
    symbol: str
    market: str
    action_date: date
    action_type: str     # split / dividend / ticker_change / merger / delisting
    value: float | str | None = None
    raw_payload: dict | None = None
    source: str
```

### 6.4 TradingCalendar

用于表示市场交易日历。

```python
from datetime import date
from pydantic import BaseModel

class TradingCalendar(BaseModel):
    market: str
    trade_date: date
    is_open: bool
    session: str | None = None
    source: str
```

## 7. 标准化文件输出约定

第一阶段优先使用 Parquet，不急着引入数据库。

建议输出结构：

```text
data/
  raw/
    us/
      yfinance/
        prices_daily/
        instruments/

  processed/
    us/
      instruments.parquet
      prices_daily/
        year=2024/
        year=2025/
        year=2026/
      corporate_actions.parquet

  exports/
    type_n/
      us_instruments.parquet
      us_prices_daily.parquet
```

### 7.1 标准 prices_daily 字段

```text
instrument_id
symbol
market
trade_date
open
high
low
close
volume
amount
adj_open
adj_high
adj_low
adj_close
adj_volume
dividend
split_factor
source
created_at
updated_at
```

### 7.2 标准 instruments 字段

```text
instrument_id
symbol
market
exchange
name
asset_type
sector
industry
currency
is_active
list_date
delist_date
source
created_at
updated_at
```

## 8. 基础模块设计

### 8.1 core/schemas.py

负责定义 Pydantic 模型和 pandas DataFrame 字段规范。

建议包含：

```python
class Instrument(BaseModel): ...
class DailyBar(BaseModel): ...
class CorporateAction(BaseModel): ...
class TradingCalendar(BaseModel): ...

PRICE_DAILY_COLUMNS = [...]
INSTRUMENT_COLUMNS = [...]
CORPORATE_ACTION_COLUMNS = [...]
```

### 8.2 core/storage.py

负责统一存储接口。

第一阶段只实现 ParquetStorage。

```python
class ParquetStorage:
    def __init__(self, root: Path): ...

    def write_instruments(self, market: str, df: pd.DataFrame) -> None: ...
    def read_instruments(self, market: str) -> pd.DataFrame: ...

    def write_daily_prices(self, market: str, df: pd.DataFrame) -> None: ...
    def read_daily_prices(self, market: str, start: str | None = None, end: str | None = None) -> pd.DataFrame: ...
```

### 8.3 core/adjustments.py

负责复权逻辑。

第一阶段要求：

- 如果数据源已提供 adj_open / adj_high / adj_low / adj_close，则优先使用数据源字段
- 如果只有 adj_close，则按 `adj_close / close` 推算 adj_open / adj_high / adj_low
- 保留 dividend 和 split_factor 字段
- 不在第一阶段自己实现复杂公司行为复权

示例：

```python
def infer_adjusted_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    ratio = df["adj_close"] / df["close"]
    df["adj_open"] = df["open"] * ratio
    df["adj_high"] = df["high"] * ratio
    df["adj_low"] = df["low"] * ratio
    return df
```

### 8.4 core/instruments.py

负责生成统一 instrument_id。

建议规则：

```text
US:AAPL
US:MSFT
CN:600519.SH
HK:00700.HK
```

示例：

```python
def make_instrument_id(market: str, symbol: str) -> str:
    return f"{market.upper()}:{symbol.upper()}"
```

### 8.5 core/calendars.py

第一阶段暂不强制接入交易所官方日历。

可以先用价格数据中实际出现的日期构建交易日序列。

后续再接入：

- NYSE/Nasdaq 日历
- A 股交易日历
- 港股交易日历

## 9. 美股模块设计

### 9.1 markets/us/adapters/base.py

建议定义统一接口：

```python
from abc import ABC, abstractmethod
import pandas as pd

class USMarketDataAdapter(ABC):
    @abstractmethod
    def get_instruments(self) -> pd.DataFrame:
        pass

    @abstractmethod
    def get_daily_prices(
        self,
        symbols: list[str],
        start: str,
        end: str | None = None,
    ) -> pd.DataFrame:
        pass

    def get_corporate_actions(
        self,
        symbols: list[str],
        start: str,
        end: str | None = None,
    ) -> pd.DataFrame:
        return pd.DataFrame()
```

### 9.2 markets/us/adapters/yfinance.py

第一阶段主实现。

职责：

- 使用 yfinance 下载历史日线
- 标准化字段
- 生成 instrument_id
- 输出符合 `DailyBar` schema 的 DataFrame

伪代码：

```python
import yfinance as yf
import pandas as pd

from market_data_hub.core.instruments import make_instrument_id
from market_data_hub.core.adjustments import infer_adjusted_ohlc

class YFinanceUSAdapter:
    source = "yfinance"

    def get_daily_prices(self, symbols: list[str], start: str, end: str | None = None) -> pd.DataFrame:
        raw = yf.download(
            tickers=symbols,
            start=start,
            end=end,
            auto_adjust=False,
            actions=True,
            group_by="ticker",
            progress=False,
            threads=True,
        )
        return self._normalize_prices(raw, symbols)

    def _normalize_prices(self, raw: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
        frames = []
        for symbol in symbols:
            df = raw[symbol].copy() if len(symbols) > 1 else raw.copy()
            df = df.reset_index()
            df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]

            df["symbol"] = symbol
            df["market"] = "US"
            df["instrument_id"] = make_instrument_id("US", symbol)
            df["trade_date"] = pd.to_datetime(df["date"]).dt.date
            df["source"] = self.source

            rename = {
                "adj_close": "adj_close",
                "stock_splits": "split_factor",
                "dividends": "dividend",
            }
            df = df.rename(columns=rename)

            if "adj_close" in df.columns and "close" in df.columns:
                df = infer_adjusted_ohlc(df)

            frames.append(df)

        return pd.concat(frames, ignore_index=True)
```

### 9.3 markets/us/adapters/polygon.py

第一阶段只保留空实现和 TODO。

职责预留：

- ticker details
- aggregates daily bars
- splits
- dividends
- ticker events
- flat files

```python
class PolygonUSAdapter:
    source = "polygon"

    def get_instruments(self) -> pd.DataFrame:
        raise NotImplementedError

    def get_daily_prices(self, symbols: list[str], start: str, end: str | None = None) -> pd.DataFrame:
        raise NotImplementedError

    def get_corporate_actions(self, symbols: list[str], start: str, end: str | None = None) -> pd.DataFrame:
        raise NotImplementedError
```

### 9.4 markets/us/adapters/tiingo.py

第一阶段只保留空实现和 TODO。

Tiingo 的 EOD 接口可以返回 raw OHLCV、adjusted OHLCV、dividend 和 splitFactor 字段，后续可作为正式 EOD 数据源。

## 10. 美股 pipeline 设计

### 10.1 download_instruments.py

第一阶段可以先用静态股票池文件。

路径：

```text
configs/us_universe.yaml
```

示例：

```yaml
symbols:
  - AAPL
  - MSFT
  - NVDA
  - AMZN
  - GOOGL
  - META
  - TSLA
  - JPM
  - JNJ
  - V
```

后续再从数据源获取完整股票池。

### 10.2 download_prices.py

功能：

- 读取 `configs/us.yaml`
- 加载 symbol universe
- 调用 adapter 下载价格
- 标准化字段
- 写入 processed parquet

CLI 示例：

```bash
python -m market_data_hub.markets.us.pipelines.download_prices \
  --source yfinance \
  --start 2015-01-01 \
  --end 2026-07-03
```

### 10.3 download_corporate_actions.py

第一阶段：

- 对 yfinance：从日线 actions 字段中保留 dividend / split_factor
- 对 Polygon / Tiingo：暂时预留接口

第二阶段：

- 单独下载 splits
- 单独下载 dividends
- 单独下载 ticker events
- 建立 corporate_actions.parquet

## 11. 配置文件设计

### 11.1 configs/us.yaml

```yaml
market: US
currency: USD
storage:
  backend: parquet
  root: ./data

data_source:
  default: yfinance
  yfinance:
    enabled: true
    batch_size: 50
    auto_adjust: false
    actions: true

  polygon:
    enabled: false
    api_key_env: POLYGON_API_KEY
    use_flat_files: false

  tiingo:
    enabled: false
    api_key_env: TIINGO_API_KEY

universe:
  file: ./configs/us_universe.yaml

update:
  default_start: "2015-01-01"
  timezone: America/New_York
```

### 11.2 configs/cn.yaml

第一阶段仅占位。

```yaml
market: CN
currency: CNY
storage:
  backend: parquet
  root: ./data

data_source:
  default: tushare
  tushare:
    enabled: false
    token_env: TUSHARE_TOKEN
```

### 11.3 configs/hk.yaml

第一阶段仅占位。

```yaml
market: HK
currency: HKD
storage:
  backend: parquet
  root: ./data

data_source:
  default: yahoo
  yahoo:
    enabled: false
```

## 12. jobs 设计

### 12.1 jobs/full_refresh.py

全量刷新。

```bash
python -m market_data_hub.jobs.full_refresh --market US --source yfinance --start 2015-01-01
```

功能：

- 删除或覆盖旧 processed 数据
- 重新下载完整历史日线
- 重建 instruments
- 重建 prices_daily
- 生成导出数据

### 12.2 jobs/daily_update.py

每日增量更新。

```bash
python -m market_data_hub.jobs.daily_update --market US --source yfinance
```

功能：

- 读取本地最后一个交易日
- 从最后交易日之后开始下载
- 合并去重
- 写回 Parquet
- 输出更新摘要

## 13. type-n 对接格式

第一阶段导出给 `type-n` 的数据可以放在：

```text
data/exports/type_n/
  us_instruments.parquet
  us_prices_daily.parquet
```

`type-n` 只需要读取：

```text
instrument_id
symbol
market
trade_date
open
high
low
close
volume
adj_open
adj_high
adj_low
adj_close
adj_volume
source
```

后续 `type-n` 的三年新高挖掘可以直接使用：

```text
adj_close
adj_high
volume
trade_date
instrument_id
```

## 14. 第一阶段开发任务拆分

### Milestone 0：项目初始化

- [ ] 创建 Git 仓库：`market-data-hub`
- [ ] 创建目录结构
- [ ] 创建 `pyproject.toml`
- [ ] 配置 ruff / pytest
- [ ] 创建 README.md
- [ ] 创建 configs/cn.yaml、configs/us.yaml、configs/hk.yaml

### Milestone 1：核心 schema 与存储

- [ ] 实现 `core/schemas.py`
- [ ] 实现 `core/instruments.py`
- [ ] 实现 `core/adjustments.py`
- [ ] 实现 `core/storage.py`
- [ ] 实现 Parquet 读写
- [ ] 写基础单元测试

### Milestone 2：美股 yfinance 适配器

- [ ] 实现 `markets/us/adapters/base.py`
- [ ] 实现 `markets/us/adapters/yfinance.py`
- [ ] 支持批量 ticker 下载
- [ ] 支持 start / end 参数
- [ ] 标准化 OHLCV 字段
- [ ] 标准化 adjusted OHLCV 字段
- [ ] 保留 dividends / stock_splits 字段
- [ ] 处理空数据、异常 ticker、请求失败重试

### Milestone 3：美股 pipeline

- [ ] 实现 `markets/us/pipelines/download_instruments.py`
- [ ] 实现 `markets/us/pipelines/download_prices.py`
- [ ] 支持从 `configs/us_universe.yaml` 读取股票池
- [ ] 支持按 batch 下载
- [ ] 支持写入 processed parquet
- [ ] 输出下载统计：成功数量、失败数量、日期范围、行数

### Milestone 4：任务入口

- [ ] 实现 `jobs/full_refresh.py`
- [ ] 实现 `jobs/daily_update.py`
- [ ] 支持 `--market US`
- [ ] 支持 `--source yfinance`
- [ ] 支持自动读取本地最大 trade_date
- [ ] 支持合并去重

### Milestone 5：type-n 导出

- [ ] 实现 `exports/parquet.py`
- [ ] 导出 `us_instruments.parquet`
- [ ] 导出 `us_prices_daily.parquet`
- [ ] 写 README 说明 type-n 如何读取

## 15. 开发顺序建议

建议严格按这个顺序：

```text
1. 项目骨架
2. schema
3. ParquetStorage
4. yfinance adapter
5. download_prices pipeline
6. full_refresh job
7. daily_update job
8. type-n export
9. 再考虑 Polygon / Tiingo 正式数据源
```

不要一开始就做完整 CN / US / HK，也不要一开始就接三个美股数据源。先让美股日线从下载到标准化输出跑通。

## 16. 数据质量检查

第一阶段至少做以下检查：

- `trade_date` 不为空
- `instrument_id` 不为空
- `close` 大于 0
- `adj_close` 大于 0
- 同一 `instrument_id + trade_date` 不重复
- 按 `instrument_id + trade_date` 排序
- 缺失率统计
- 每个 ticker 的起止日期统计
- 下载失败 ticker 单独输出

示例质量报告：

```text
Market: US
Source: yfinance
Symbols requested: 10
Symbols success: 10
Symbols failed: 0
Date range: 2015-01-02 ~ 2026-07-02
Rows: 28,450
Duplicate rows: 0
Missing adj_close rows: 0
```

## 17. 异常处理原则

- 单个 ticker 失败不应中断全任务
- 失败 ticker 写入日志和 error report
- 网络错误使用重试
- 空数据直接跳过，但记录原因
- 字段缺失时抛出明确错误
- 不静默吞掉 schema 不一致问题

## 18. 后续扩展计划

### 18.1 美股正式数据源

第二阶段接入：

- Polygon / Massive
- Tiingo

优先级建议：

```text
1. Tiingo EOD：字段直接，适合作为 yfinance 替代
2. Polygon / Massive：适合公司行为、ticker events、批量历史数据
```

### 18.2 A 股接入

后续将已有 TuShare 工程迁移或接入到：

```text
market_data_hub/markets/cn/adapters/tushare.py
```

注意不要破坏已有可用工程，可以先做 wrapper。

### 18.3 港股接入

港股第一阶段可以考虑：

- Yahoo/yfinance
- AkShare

正式化时再评估更稳定数据源。

### 18.4 数据库支持

当 Parquet 不够用时，再引入：

- DuckDB：适合本地分析和 SQL 查询
- PostgreSQL：适合服务化
- ClickHouse：适合大规模行情查询

## 19. README 初稿结构

根目录 README.md 可以写：

```markdown
# market-data-hub

Cross-market data ingestion and normalization hub for type-n.

## Supported Markets

- US: first-stage support via yfinance
- CN: planned TuShare adapter
- HK: planned Yahoo/AkShare adapter

## Quick Start

```bash
pip install -e .
python -m market_data_hub.jobs.full_refresh --market US --source yfinance --start 2015-01-01
```

## Output

```text
data/exports/type_n/us_instruments.parquet
data/exports/type_n/us_prices_daily.parquet
```

## Project Boundary

market-data-hub handles data ingestion and normalization. Strategy mining and machine learning are handled by type-n.
```

## 20. 给 Codex 的开发提示词

可以把下面这段直接给 Codex：

```text
请根据以下要求创建一个 Python 项目 market-data-hub。

项目定位：跨市场原始数据获取与标准化工程，为上游 type-n 机器学习挖掘系统提供标准化行情数据。第一阶段只实现基础框架和美股日线数据获取。

请按以下目录结构创建项目：

market-data-hub/
  README.md
  pyproject.toml
  configs/
    cn.yaml
    us.yaml
    hk.yaml
    us_universe.yaml
  market_data_hub/
    core/
      instruments.py
      calendars.py
      schemas.py
      storage.py
      adjustments.py
    markets/
      cn/
        adapters/
          tushare.py
        pipelines/
          download_prices.py
          download_instruments.py
      us/
        adapters/
          base.py
          polygon.py
          yfinance.py
          tiingo.py
        pipelines/
          download_prices.py
          download_instruments.py
          download_corporate_actions.py
      hk/
        adapters/
          yahoo.py
          akshare.py
        pipelines/
          download_prices.py
          download_instruments.py
    exports/
      parquet.py
      postgres.py
      sqlite.py
    jobs/
      daily_update.py
      full_refresh.py

开发要求：

1. 使用 Python >= 3.11。
2. 使用 pandas、pyarrow、pydantic、typer、loguru、yfinance。
3. 在 core/schemas.py 中定义 Instrument、DailyBar、CorporateAction、TradingCalendar。
4. 在 core/instruments.py 中实现 make_instrument_id(market, symbol)，格式如 US:AAPL。
5. 在 core/adjustments.py 中实现 infer_adjusted_ohlc(df)，当存在 adj_close 和 close 时，用 adj_close / close 推算 adj_open、adj_high、adj_low。
6. 在 core/storage.py 中实现 ParquetStorage，支持 write_instruments、read_instruments、write_daily_prices、read_daily_prices。
7. 在 markets/us/adapters/base.py 中定义 USMarketDataAdapter 抽象类。
8. 在 markets/us/adapters/yfinance.py 中实现 YFinanceUSAdapter，使用 yfinance.download 下载美股日线，参数包括 symbols、start、end，使用 auto_adjust=False、actions=True，并标准化为统一字段。
9. polygon.py 和 tiingo.py 先保留 NotImplementedError，占位即可。
10. 在 markets/us/pipelines/download_prices.py 中实现 CLI，可读取 configs/us.yaml 和 configs/us_universe.yaml，批量下载美股日线并写入 processed parquet。
11. 在 jobs/full_refresh.py 中实现全量刷新入口，支持 --market US --source yfinance --start YYYY-MM-DD。
12. 在 jobs/daily_update.py 中实现每日增量更新入口，读取本地已有数据最大 trade_date，从下一日开始更新。
13. 在 exports/parquet.py 中实现导出给 type-n 的 parquet 文件：data/exports/type_n/us_instruments.parquet 和 data/exports/type_n/us_prices_daily.parquet。
14. 需要有基础错误处理：单个 ticker 下载失败不能中断整个任务，失败 ticker 写入日志。
15. 需要有基础数据质量检查：trade_date、instrument_id、close、adj_close 非空；instrument_id + trade_date 不重复。
16. 写 README.md，说明项目边界、快速开始、输出路径。
17. 写最少量 pytest 单元测试，覆盖 make_instrument_id、infer_adjusted_ohlc、ParquetStorage 基础读写。

请优先保证第一阶段美股日线数据可以从下载、标准化、存储到导出完整跑通。不要实现 type-n 的因子、labeler、机器学习和回测逻辑。
```

## 21. 参考资料

- yfinance GitHub README：说明 yfinance 是开源工具，提供 Yahoo Finance 数据访问，并提示其不隶属于 Yahoo，数据使用需参考 Yahoo 条款。
- yfinance API Reference：说明包含 `Ticker`、`Tickers`、`download` 等公开接口。
- Tiingo EOD 文档：说明 EOD 接口提供 raw prices、adjusted prices、dividend 和 splitFactor 等字段。
- Massive / Polygon Splits 文档：说明可获取历史 split events，并包含用于历史价格标准化的 adjustment factors。
