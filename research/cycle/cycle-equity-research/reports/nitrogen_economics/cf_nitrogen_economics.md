# CF Milestone 3 氮肥利润代理报告

- 模型：`cf_nitrogen_economics` v1.0.0
- 状态：PASS
- 日频：3403 行
- 季度：42 行
- 情景顺序违规：0
- 重复构建一致：True

## 公式层级

1. 相对状态：标准化产品价格 ÷ Henry Hub。
2. 理论现金价差：标准化产品价格 − Henry Hub × 情景气耗。
3. CF 实现气价差：CF 实现售价 − CF 实际气价 × 情景气耗 − 已识别变动成本。

第三层仍不是会计毛利；实现气价差与披露毛利/吨之间的差额作为其他成本、地区基差和时点残差保留。

## 分产品校准

| 产品 | 水平相关 | 变化相关 | 方向命中率 | 残差均值 | MAE |
|---|---:|---:|---:|---:|---:|
| ammonia | 0.955 | 0.900 | 0.821 | 201.678 | 201.678 |
| granular_urea | 0.983 | 0.925 | 0.897 | 140.863 | 140.863 |
| uan | 0.991 | 0.980 | 0.897 | 116.244 | 116.244 |
| ammonium_nitrate | 0.616 | 0.483 | 0.718 | 189.776 | 189.776 |

## 市场代理和公司结果

- `ams_urea_spread_vs_cf_urea_gross_margin`：水平相关 0.812，变化相关 0.735，方向命中率 0.643。
- `global_urea_spread_vs_cf_urea_realized_price`：水平相关 0.968，变化相关 0.758，方向命中率 0.780。
- `basket_spread_vs_gross_margin`：水平相关 0.882，变化相关 0.677，方向命中率 0.795。
- `basket_spread_vs_ebitda_proxy`：水平相关 0.937，变化相关 0.812，方向命中率 0.846。

## 已知失效场景

- Gas intensities are scenario assumptions calibrated to company-wide disclosed consumption, not plant engineering measurements.
- Identified variable cost is zero because no consistent product-level series is disclosed; resulting spreads are not accounting gross margins.
- AMS prices are Illinois distributor asks while CF prices are company realized prices across geographies and contract types.
- Inventory timing, hedging, freight, purchased product, turnarounds and product mix remain in the residual.

## 参数来源

- https://www.sec.gov/Archives/edgar/data/1324404/000110465924055837/tm2413105d1_ex99-1.htm
- https://www.sec.gov/Archives/edgar/data/1324404/000132440425000006/cf-20241231.htm
