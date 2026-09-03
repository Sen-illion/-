# Q2 论文材料包（待签署）

## 写作边界

最终方法为独立情景滚动随机 MILP，基线为均值参数滚动 MILP并在同一情景上评价。选择、结果和稳定性分别追溯至 `q2_method_choice`、`q2_result_verdict_round1`、`q2_stability_verdict_round1`。收益改进应描述为“小幅且方向稳定”，不能描述为数量级优势。

## 方法材料

30个情景、种子20240902；共享种植决策、情景销售量；目标结合期望利润与90%置信水平的CVaR损失，风险权重0.15；超产按半价销售。约束继承Q1。权威说明：`methods/Q2/q2_final_method_explanation.md`。

## 拟冻结的顶层结论

| Claim ID | 数值与单位 | 来源和定位 | 稳健性 | 人工决策 | 置信/限制 |
|---|---|---|---|---|---|
| Q2-C1 | 主方案年均利润 68,206,112.47 元 | `run_summary.json` → `comparison.main_mean_profit_yuan` | 五个新种子均优于基线 | `q2_result_verdict_round1` | 30情景优化口径 |
| Q2-C2 | 基线年均利润 68,014,316.70 元 | 同上 → `comparison.baseline_mean_profit_yuan` | 同情景可比 | `q2_result_verdict_round1` | 可用基线 |
| Q2-C3 | 主方案最差10%平均利润 66,429,343.10 元 | 同上 → `comparison.main_lower_10pct_mean_profit_yuan` | 新种子增量均为正 | `q2_stability_verdict_round1` | Monte Carlo尾部估计 |
| Q2-C4 | 主方案平均超产率 58.034% | 同上 → `comparison.main_mean_excess_rate` | 五个新种子约58.0% | `q2_stability_verdict_round1` | 超产半价销售，不等于浪费率 |
| Q2-C5 | 最大 MIP gap 4.396% | 同上 → 主方法窗口 `mip_gap` 最大值 | 低于5%预设线 | `q2_result_verdict_round1` | 未触发Q2-F1 |

## 图表与文件

正文使用 Q2-FIG-1 表示五个新种子下平均利润和下行利润的正增量；精确比较使用 Q2-TAB-1。逐地块方案位于 `outputs/24c_modeling/result2.xlsx`。

## 必须保留的限制

未来分布为题面范围内模拟而非历史估计；优化仅用30个情景；新种子检验为固定方案复评；智慧大棚第一季经济参数由第二季代替。

