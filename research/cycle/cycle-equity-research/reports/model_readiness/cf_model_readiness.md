# CF M2.1 模型就绪数据报告

- 状态：**WARNING**
- ERROR：0
- WARNING：2

| 面板 | 行数 | 核心特征 | 完整样本 | 样本/特征 | 建议用途 |
|---|---:|---:|---:|---:|---|
| `core_monthly` | 163 | 6 | 115 | 19.2 | 探索性估计，需正则化和稳健性检验 |
| `core_quarterly` | 42 | 5 | 40 | 8.0 | 描述分析/关系校准，不宜独立训练复杂模型 |
| `tactical_context` | 3403 | 0 | — | — | 场景确认与微观诊断，不进基础模型 |

## 核心特征

### 月频

- `global_urea_gas_spread_month_mean`
- `henry_hub_month_mean`
- `corn_month_mean`
- `cf_momentum_6m`
- `latest_cf_realized_basket_gas_spread`
- `latest_cf_gross_margin_change`

### 季度

- `global_urea_gas_spread_quarter_mean`
- `cf_realized_basket_gas_spread`
- `cf_total_sales_volume`
- `cf_realized_natural_gas_cost`
- `cf_gross_margin_change`

## 质量结论

- WARNING：core_monthly feature missing rates exceed limit: {'latest_cf_realized_basket_gas_spread': 0.26380368098159507}
- WARNING：core_quarterly economically distinct features exceed correlation limit; do not use together without selection or regularization: [{'left': 'global_urea_gas_spread_quarter_mean', 'right': 'cf_realized_basket_gas_spread', 'absolute_correlation': 0.9656625232817586}]

季度完整样本有限，默认只用于描述分析、关系校准和低自由度估计；复杂时间序列模型仍需在 M7 单独证明增量价值。
战术面板中的 AMS、种植面积和产品成本残差不进入基础训练矩阵。
