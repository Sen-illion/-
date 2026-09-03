# Q1 论文材料包（待签署）

## 写作边界

最终方法为三年重叠滚动 MILP，基线为满足硬约束的利润排序贪心。方法选择来自 `q1_method_choice`，结果接受来自 `q1_result_verdict_round1`，稳定性与表述范围来自 `q1_stability_verdict_round1`。不得使用“全局最优”“稳健地低于10%”等超出证据的措辞。

## 方法材料

以 $x_{ijts}$ 表示种植面积、$y_{ijts}$ 表示启用状态、$u_{jts}$ 表示正常销售量。Q1(1) 最大化利润减去按超产货值计的 0.50 权重惩罚；Q1(2) 将超产按正常售价的 50% 计入收入。约束包括适种、面积、水浇地种植模式、相邻期禁重茬、连续三年豆类覆盖和最小种植面积。权威说明：`methods/Q1/q1_final_method_explanation.md`。

## 拟冻结的顶层结论

| Claim ID | 数值与单位 | 来源和定位 | 稳健性 | 人工决策 | 置信/限制 |
|---|---|---|---|---|---|
| Q1-C1 | Q1(1) 年均利润 33,728,552.33 元 | `run_summary.json` → `methods[0].metrics_summary.case1.mean_profit_yuan` | 销量±5%复评 | `q1_result_verdict_round1` | 可行近似解 |
| Q1-C2 | Q1(1) 基准超产率 6.833% | 同上 → `case1.mean_excess_rate` | -5%销量时为10.119% | `q1_stability_verdict_round1` | 条件性稳健 |
| Q1-C3 | Q1(2) 年均利润 61,412,145.76 元 | 同上 → `case2.mean_profit_yuan` | 未改变处置口径 | `q1_result_verdict_round1` | 超产半价销售 |
| Q1-C4 | 最大 MIP gap 48.858% | `run_summary.json` → `fallback_trigger.evidence.maximum_mip_gap` | 触发Q1-F1 | `q1_stability_verdict_round1` | 不得宣称全局最优 |

## 图表与文件

正文使用 Q1-FIG-1 展示销量扰动下主方案与基线超产率；精确结果用 Q1-TAB-1。逐地块方案位于 `outputs/24c_modeling/result1_1.xlsx` 与 `result1_2.xlsx`。

## 必须保留的限制

智慧大棚第一季复用第二季经济参数；销量以2023年产量代理；滚动窗口的高最优性缺口未消除；销量下降5%时超产率略高于10%。

