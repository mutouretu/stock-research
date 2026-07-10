# stock-pattern-search：三年前高接近度股票挖掘模块开发文档

## 1. 模块名称

```text
new_high_simple
```

中文名称：

```text
三年前高接近度股票挖掘模块
```

模块定位：

> 在全市场股票中，扫描当前收盘价接近近三年前高的股票，并按照“距离前高越近，分数越高”的原则生成观察列表。

---

## 2. 开发目标

本模块第一版只做一件事：

> 根据股票当前收盘价与近三年前高之间的距离，对全市场股票进行打分和排序。

第一版不做机器学习，不做复杂多因子，不做交易信号，只输出观察池。

核心输出：

```text
三年前高接近度排行榜
```

---

## 3. 设计原则

### 3.1 简单优先

第一版只使用价格位置因子：

```text
high_ratio = close / high_3y_prev
```

其中：

```text
high_3y_prev = 最近750个交易日内，不包含当日的最高价
```

### 3.2 不做买入建议

模块只负责挖掘和排序，不直接输出买入信号。

输出结果是：

```text
观察列表
```

而不是：

```text
交易列表
```

### 3.3 不引入机器学习

第一版暂不需要：

```text
labeler.py
trainer.py
model.py
ml_ranker.py
```

后续如果要验证“接近前高后未来是否继续上涨”，再增加 labeler。

### 3.4 可扩展

虽然第一版简单，但目录结构要为后续扩展预留空间：

```text
趋势因子
成交量因子
相对强度因子
行业共振因子
机器学习排序器
历史回测与标签系统
```

---

## 4. 目录结构

建议放在 stock-pattern-search 项目中：

```text
stock-pattern-search/
  strategies/
    new_high_simple/
      README.md
      config.yaml
      scanner.py
      scorer.py
      filters.py
      report.py
      run_daily.py
```

暂不创建：

```text
labeler.py
trainer.py
model.py
```

---

## 5. 文件职责

### 5.1 config.yaml

存放模块参数。

示例：

```yaml
strategy_name: new_high_simple

rolling_window: 750

watch_threshold: 0.90
break_high_threshold: 1.00
near_2_threshold: 0.98
near_5_threshold: 0.95
near_10_threshold: 0.90
watch_loose_threshold: 0.85

min_avg_amount_20d: 100000000
min_listed_days: 250

top_n: 200

output_dir: reports/new_high_simple
```

---

### 5.2 scanner.py

负责扫描全市场股票数据。

主要职责：

```text
1. 读取股票日线行情
2. 按股票代码分组
3. 调用 scorer 计算分数
4. 调用 filters 过滤不合格股票
5. 汇总候选列表
```

建议主函数：

```python
def scan_market(trade_date: str, config: dict) -> pd.DataFrame:
    """
    扫描全市场股票，返回三年前高接近度观察列表。
    """
```

---

### 5.3 scorer.py

负责计算核心指标和分数。

核心指标：

```text
high_3y_prev
high_ratio
distance_to_high
score
status
```

核心公式：

```python
high_ratio = close / high_3y_prev
score = min(high_ratio, 1.0) * 100
distance_to_high = 1 - high_ratio
```

状态划分：

```python
def assign_status(high_ratio: float) -> str:
    if high_ratio >= 1.0:
        return "BREAK_HIGH"
    elif high_ratio >= 0.98:
        return "NEAR_2"
    elif high_ratio >= 0.95:
        return "NEAR_5"
    elif high_ratio >= 0.90:
        return "NEAR_10"
    elif high_ratio >= 0.85:
        return "WATCH"
    else:
        return "IGNORE"
```

建议主函数：

```python
def calculate_new_high_score(df: pd.DataFrame, rolling_window: int = 750) -> pd.DataFrame:
    """
    对单只股票的历史行情计算三年前高接近度分数。
    """
```

输入字段要求：

```text
date
code
open
high
low
close
volume
amount
```

输出新增字段：

```text
high_3y_prev
high_ratio
distance_to_high
score
status
```

---

### 5.4 filters.py

负责基础过滤。

第一版只做简单过滤：

```text
非ST
非退市风险
上市时间足够
成交额足够
最近正常交易
```

建议过滤条件：

```text
min_listed_days >= 250
avg_amount_20d >= 100000000
status != ST
status != 退市风险
```

建议主函数：

```python
def apply_basic_filters(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    对扫描结果进行基础过滤。
    """
```

---

### 5.5 report.py

负责导出观察列表。

输出格式：

```text
CSV
Excel
Markdown
```

第一版优先 CSV 和 Excel。

建议输出路径：

```text
reports/new_high_simple/YYYY-MM-DD_new_high_watchlist.csv
reports/new_high_simple/YYYY-MM-DD_new_high_watchlist.xlsx
```

建议主函数：

```python
def export_watchlist(df: pd.DataFrame, trade_date: str, config: dict) -> None:
    """
    导出三年前高接近度观察列表。
    """
```

---

### 5.6 run_daily.py

每日运行入口。

职责：

```text
1. 读取配置
2. 获取交易日
3. 执行全市场扫描
4. 输出观察列表
5. 打印摘要信息
```

运行方式：

```bash
python strategies/new_high_simple/run_daily.py --date 2026-07-01
```

---

## 6. 核心计算逻辑

### 6.1 三年前高

使用过去约750个交易日作为三年窗口。

注意：

```text
三年前高不包含今天
```

避免今天的最高价影响“是否突破前高”的判断。

计算方式：

```python
df["high_3y_prev"] = (
    df["high"]
    .rolling(window=750, min_periods=250)
    .max()
    .shift(1)
)
```

---

### 6.2 接近度比例

```python
df["high_ratio"] = df["close"] / df["high_3y_prev"]
```

含义：

```text
high_ratio = 1.00 表示收盘价达到三年前高
high_ratio = 0.95 表示距离三年前高还有约5%
high_ratio = 0.90 表示距离三年前高还有约10%
```

---

### 6.3 距离前高百分比

```python
df["distance_to_high"] = 1 - df["high_ratio"]
```

例如：

```text
high_ratio = 0.96
distance_to_high = 0.04
```

表示距离三年前高还有约4%。

---

### 6.4 分数

第一版使用线性评分：

```python
df["score"] = df["high_ratio"].clip(upper=1.0) * 100
```

解释：

```text
突破前高：100分
距离前高2%以内：约98分以上
距离前高5%以内：约95分以上
距离前高10%以内：约90分以上
```

---

## 7. 状态规则

| 状态         |                        条件 | 含义              |
| ---------- | ------------------------: | --------------- |
| BREAK_HIGH |        high_ratio >= 1.00 | 收盘价突破三年前高       |
| NEAR_2     | 0.98 <= high_ratio < 1.00 | 距离三年前高2%以内      |
| NEAR_5     | 0.95 <= high_ratio < 0.98 | 距离三年前高5%以内      |
| NEAR_10    | 0.90 <= high_ratio < 0.95 | 距离三年前高10%以内     |
| WATCH      | 0.85 <= high_ratio < 0.90 | 距离三年前高15%以内，弱观察 |
| IGNORE     |         high_ratio < 0.85 | 暂不关注            |

第一版默认入池条件：

```text
high_ratio >= 0.90
```

也就是只保留：

```text
BREAK_HIGH
NEAR_2
NEAR_5
NEAR_10
```

---

## 8. 输出字段

最终观察列表建议包含以下字段：

| 字段               | 说明          |
| ---------------- | ----------- |
| trade_date       | 交易日期        |
| code             | 股票代码        |
| name             | 股票名称        |
| close            | 当前收盘价       |
| high_3y_prev     | 近三年前高       |
| high_ratio       | 收盘价 / 近三年前高 |
| distance_to_high | 距离前高百分比     |
| score            | 接近度分数       |
| status           | 状态          |
| avg_amount_20d   | 近20日平均成交额   |
| listed_days      | 上市交易天数      |
| industry         | 行业，可选       |
| rank             | 当日排名        |

---

## 9. 排序规则

第一版按以下优先级排序：

```text
1. score 从高到低
2. high_ratio 从高到低
3. avg_amount_20d 从高到低
```

最终输出前：

```text
top_n = 200
```

---

## 10. 最小运行流程

```text
1. 加载配置 config.yaml
2. 读取全市场股票日线数据
3. 对每只股票计算 high_3y_prev
4. 计算 high_ratio
5. 计算 score
6. 标记 status
7. 执行基础过滤
8. 保留 high_ratio >= watch_threshold 的股票
9. 按 score 排序
10. 导出观察列表
```

---

## 11. 示例伪代码

```python
def run_daily(trade_date: str):
    config = load_config("strategies/new_high_simple/config.yaml")

    market_data = load_market_data(end_date=trade_date)

    result_list = []

    for code, df_stock in market_data.groupby("code"):
        df_score = calculate_new_high_score(
            df_stock,
            rolling_window=config["rolling_window"]
        )

        latest = df_score[df_score["date"] == trade_date]

        if latest.empty:
            continue

        result_list.append(latest)

    result = pd.concat(result_list, ignore_index=True)

    result = apply_basic_filters(result, config)

    result = result[result["high_ratio"] >= config["watch_threshold"]]

    result = result.sort_values(
        by=["score", "high_ratio", "avg_amount_20d"],
        ascending=[False, False, False]
    )

    result["rank"] = range(1, len(result) + 1)

    result = result.head(config["top_n"])

    export_watchlist(result, trade_date, config)

    return result
```

---

## 12. 第一版不做的事情

第一版暂不做：

```text
机器学习
labeler
未来收益标签
买入卖出信号
止损止盈
行业共振
成交量放大判断
均线多头判断
相对大盘强弱
复杂回测
自动交易
```

这些放到后续版本。

---

## 13. 后续扩展计划

### v0.2：加入趋势过滤

新增：

```text
MA20
MA60
MA120
MA250
close > MA60
MA60 > MA120
```

### v0.3：加入成交量过滤

新增：

```text
近5日成交量 / 近60日成交量
近20日平均成交额
突破日是否放量
```

### v0.4：加入行业信息

新增：

```text
行业分类
行业内接近三年前高股票数量
行业内高分股票占比
```

### v0.5：加入历史统计

新增：

```text
接近三年前高后未来20日收益
接近三年前高后未来60日收益
突破前高后未来最大回撤
假突破统计
```

此阶段开始需要：

```text
labeler.py
```

### v0.6：加入机器学习排序

新增：

```text
features.py
labeler.py
trainer.py
ml_ranker.py
```

模型目标：

```text
预测未来20日是否跑赢指数
预测未来60日是否继续创新高
预测突破后是否假突破
```

---

## 14. 当前版本结论

第一版模块只关注一个核心问题：

> 当前收盘价距离近三年前高有多近？

核心公式：

```text
score = min(close / high_3y_prev, 1.0) * 100
```

只要能稳定输出每日排行榜，本模块第一版就算完成。

第一版完成标准：

```text
1. 可以扫描全市场股票
2. 可以计算三年前高接近度
3. 可以生成 score 和 status
4. 可以过滤低流动性股票
5. 可以输出每日观察列表
6. 可以按分数排序展示前100或前200只股票
```

本模块的定位是：

```text
强势股观察雷达
```

而不是：

```text
自动交易策略
```
