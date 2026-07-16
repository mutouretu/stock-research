# CF M4.2 领先滞后稳定性分析

- 状态：**PASS**
- 分析截止日：`2026-06-30`
- 关系数量：14
- 滚动窗口记录：506
- 场景切片记录：89
- Point-in-time 违规：0
- 重复运行一致：True

## 固定规则

- 每个关系沿用 M4.1 已选择的领先期，不在滚动窗口或场景内重新挑选滞后。
- 月频使用 60 个观察、季度使用 20 个观察；财报事件关系使用 20 个事件。
- 核心门槛为：预期方向窗口占比不低于 75%，滚动中位绝对相关不低于 0.20。
- 高低气价和正常/大幅价差变化两类场景的预期方向占比均需不低于 75%，且各场景绝对相关不低于 0.10。
- 季节切片只用于描述，不作为硬门槛，因为季度样本分组后很小。

## 关系决策

| 关系 | 角色 | 固定领先期 | 全样本相关 | 滚动中位 | 滚动同向 | 气价场景 | 波动场景 | 决策 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `quarterly_global_spread_to_cf_realized_spread_change` | `cycle_core_validation` | 0 | 0.775 | 0.821 | 100% | 100% | 100% | `ACCEPT_CORE_VALIDATION` |
| `quarterly_global_spread_to_ebitda_change` | `cycle_core_validation` | 0 | 0.633 | 0.714 | 100% | 100% | 100% | `ACCEPT_CORE_VALIDATION` |
| `quarterly_global_spread_to_gross_margin_change` | `cycle_core_validation` | 0 | 0.366 | 0.575 | 100% | 100% | 100% | `ACCEPT_CORE_VALIDATION` |
| `quarterly_corn_to_cf_volume_yoy_change` | `demand_candidate` | 1 | -0.375 | -0.551 | 0% | 0% | 0% | `REJECT` |
| `monthly_henry_hub_change_to_global_spread_change` | `diagnostic_identity` | 0 | -0.416 | -0.412 | 100% | 100% | 100% | `DIAGNOSTIC` |
| `monthly_corn_change_to_cf_return` | `market_confirmation` | 12 | -0.118 | -0.176 | 0% | 0% | 0% | `REJECT` |
| `monthly_disclosed_margin_change_to_cf_return` | `market_confirmation` | 5 | 0.325 | 0.236 | 95% | 100% | 100% | `ACCEPT_CONFIRMATION` |
| `monthly_disclosed_realized_spread_change_to_cf_return` | `market_confirmation` | 5 | 0.360 | 0.341 | 94% | 100% | 100% | `REJECT` |
| `monthly_global_spread_change_to_cf_return` | `market_confirmation` | 8 | 0.141 | 0.169 | 100% | 100% | 100% | `REJECT` |
| `quarterly_henry_hub_to_cf_gas_cost_change` | `operating_bridge` | 1 | 0.640 | 0.642 | 100% | 100% | 100% | `ACCEPT_BRIDGE` |
| `quarterly_urea_to_ammonia_price_change` | `operating_bridge` | 1 | 0.544 | 0.567 | 100% | 100% | 100% | `ACCEPT_BRIDGE` |
| `quarterly_urea_to_ammonium_nitrate_price_change` | `operating_bridge` | 1 | 0.604 | 0.722 | 100% | 100% | 100% | `ACCEPT_BRIDGE` |
| `quarterly_urea_to_granular_urea_price_change` | `operating_bridge` | 0 | 0.770 | 0.837 | 100% | 100% | 100% | `ACCEPT_BRIDGE` |
| `quarterly_urea_to_uan_price_change` | `operating_bridge` | 1 | 0.663 | 0.675 | 100% | 100% | 100% | `ACCEPT_BRIDGE` |

## 决策含义

- `ACCEPT_BRIDGE`：可保留在实现售价或实际气价经营桥中。
- `ACCEPT_CORE_VALIDATION`：支持核心周期代理，但同一传导链只计一次分。
- `ACCEPT_CONFIRMATION`：只作为市场确认，不进入经营周期核心分数。
- `CONDITIONAL`：全样本较强，但滚动或场景稳定性未全部通过。
- `REJECT`：M4.1 已不稳定、方向矛盾或证据不足。
- `DIAGNOSTIC`：公式包含关系，只核对构造方向。

## 解释边界

滚动窗口高度重叠，窗口通过率不是独立试验的成功概率。高低气价使用样本中位数，大幅变化使用价差绝对变化的前 25%，二者用于历史稳健性检查，不是实时状态阈值。所谓大幅变化也不等于已经识别出地缘供给事件。实时状态机仍需使用当时可计算的扩展窗口阈值，并避免把尿素、Henry Hub、理论气价差和下游毛利重复加权。
