# CF M4.1 领先滞后分析

- 状态：**PASS**
- 分析截止日：`2026-06-30`
- 关系数量：14
- 滞后网格记录：88
- 经济期关系：9
- 可用期关系：5
- Point-in-time 违规：0
- 重复运行一致：True

## 时间和统计口径

- 滞后 `k` 固定表示信号 `x(t)` 与目标 `y(t+k)` 配对；`k>0` 表示信号领先。
- `economic_period` 回答经营变量按统计期如何传导，不代表该时点可交易。
- `availability_time` 只使用信号日之前已经公开的数据，可用于研究后续市场反应。
- 相关系数对应标准化一元回归斜率；标准误使用 Newey--West HAC 修正。
- `q` 值使用 Benjamini--Hochberg 方法校正同一关系内搜索多个滞后造成的多重比较。
- 最佳滞后是预设网格中绝对相关系数最大者，只是探索性摘要，不是因果结论。

## 各关系的最佳滞后

| 关系 | 时钟 | 最佳领先期 | N | 相关系数 | HAC p | 关系内 q | 全局 q | 前半段 | 后半段 | 证据 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `monthly_corn_change_to_cf_return` | `availability_time` | 12 个月 | 149 | -0.118 | 0.093 | 0.838 | 0.264 | -0.064 | -0.177 | `UNSTABLE` |
| `monthly_disclosed_margin_change_to_cf_return` | `availability_time` | 5 个月 | 39 | 0.325 | 0.002 | 0.005 | 0.010 | 0.213 | 0.543 | `STRONG` |
| `monthly_disclosed_realized_spread_change_to_cf_return` | `availability_time` | 5 个月 | 37 | 0.360 | <0.001 | <0.001 | <0.001 | 0.088 | 0.535 | `UNSTABLE` |
| `monthly_global_spread_change_to_cf_return` | `availability_time` | 8 个月 | 153 | 0.141 | 0.006 | 0.076 | 0.024 | 0.033 | 0.182 | `UNSTABLE` |
| `monthly_henry_hub_change_to_global_spread_change` | `availability_time` | 0 个月 | 157 | -0.416 | <0.001 | <0.001 | <0.001 | -0.429 | -0.417 | `DIAGNOSTIC` |
| `quarterly_corn_to_cf_volume_yoy_change` | `economic_period` | 1 个季度 | 37 | -0.375 | 0.028 | 0.087 | 0.096 | -0.263 | -0.537 | `CONTRADICTORY` |
| `quarterly_global_spread_to_cf_realized_spread_change` | `economic_period` | 0 个季度 | 39 | 0.775 | <0.001 | <0.001 | <0.001 | 0.583 | 0.798 | `STRONG` |
| `quarterly_global_spread_to_ebitda_change` | `economic_period` | 0 个季度 | 41 | 0.633 | <0.001 | <0.001 | <0.001 | 0.345 | 0.677 | `STRONG` |
| `quarterly_global_spread_to_gross_margin_change` | `economic_period` | 0 个季度 | 41 | 0.366 | <0.001 | <0.001 | <0.001 | 0.366 | 0.599 | `STRONG` |
| `quarterly_henry_hub_to_cf_gas_cost_change` | `economic_period` | 1 个季度 | 39 | 0.640 | <0.001 | 0.001 | 0.003 | 0.749 | 0.630 | `STRONG` |
| `quarterly_urea_to_ammonia_price_change` | `economic_period` | 1 个季度 | 40 | 0.544 | <0.001 | <0.001 | <0.001 | 0.227 | 0.593 | `STRONG` |
| `quarterly_urea_to_ammonium_nitrate_price_change` | `economic_period` | 1 个季度 | 40 | 0.604 | <0.001 | <0.001 | <0.001 | 0.663 | 0.600 | `STRONG` |
| `quarterly_urea_to_granular_urea_price_change` | `economic_period` | 0 个季度 | 40 | 0.770 | <0.001 | <0.001 | <0.001 | 0.672 | 0.795 | `STRONG` |
| `quarterly_urea_to_uan_price_change` | `economic_period` | 1 个季度 | 40 | 0.663 | <0.001 | <0.001 | <0.001 | 0.593 | 0.666 | `STRONG` |

## 证据标签

- `STRONG`：前后子样本方向一致、符合经济预期，且关系内和全局多重检验校正后仍显著。
- `DIRECTIONAL`：方向和子样本稳定，但校正后统计证据不足。
- `CONTRADICTORY`：方向稳定但与事前经济预期相反。
- `UNSTABLE`：前后子样本方向不一致或其中一段关系过弱。
- `INSUFFICIENT`：有效观察数低于配置门槛。
- `DIAGNOSTIC`：变量之间存在公式包含关系，只用于核对计算方向，不作为独立证据。

## 使用边界

本报告用于筛选值得进入周期状态机的候选关系。季度样本只有约 40 个，HAC 的正态近似和子样本结果都应视为描述性证据。M4.2 还需要加入滚动窗口、季节和冲击场景检验；未通过稳定性检查的关系和公式诊断关系都不能直接成为周期状态规则。
