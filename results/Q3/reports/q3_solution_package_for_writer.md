# Q3 论文材料包（待签署）

## 写作边界

最终方法是在Q2基础上加入类别层面相关冲击和弱替代/互补响应的滚动随机MILP。Q3独立方案由 `q3_result_verdict_round1` 保留，但 `q3_stability_verdict_round1` 明确冻结两项限制：参数是模拟设定；当前方案不优于Q2。

## 方法材料

30个相关情景、种子20240902；中等强度相关矩阵最小特征值0.5832；风险权重0.15、CVaR水平0.90、超产半价销售。基线为Q2方案在同一相关情景上的重新评价。权威说明：`methods/Q3/q3_final_method_explanation.md`。

## 拟冻结的顶层结论

| Claim ID | 数值与单位 | 来源和定位 | 稳健性 | 人工决策 | 置信/限制 |
|---|---|---|---|---|---|
| Q3-C1 | Q3年均利润 67,563,277.61 元 | `run_summary.json` → `comparison.q3_main_mean_profit_yuan` | 三强度三种子相对极差0.356% | `q3_result_verdict_round1` | 模拟相关结构 |
| Q3-C2 | Q2方案在相关情景下年均利润 68,196,801.59 元 | 同上 → `comparison.q2_plan_mean_profit_under_q3_scenarios_yuan` | 九组均高于Q3 | `q3_stability_verdict_round1` | 对照方案 |
| Q3-C3 | Q3-Q2平均利润差 -633,523.99 元 | 同上 → `comparison.mean_profit_change_yuan` | 九组差值均为负 | `q3_stability_verdict_round1` | 不得声称Q3优于Q2 |
| Q3-C4 | Q3最差10%平均利润 65,684,174.35 元 | 同上 → `comparison.q3_main_lower_10pct_mean_profit_yuan` | 九组方向一致 | `q3_result_verdict_round1` | 尾部Monte Carlo估计 |
| Q3-C5 | Q2/Q3面积重合度 42.645% | 同上 → `comparison.plan_area_overlap` | 触发Q3-F1 | `q3_stability_verdict_round1` | 人工决定仍保留Q3 |

## 图表与文件

正文使用 Q3-FIG-1 展示九组 Q3-Q2 平均利润差均为负；精确比较使用 Q3-TAB-1，强度摘要放入附录表 Q3-TAB-2。逐地块方案位于 `outputs/24c_modeling/result3.xlsx`。

## 必须保留的限制

相关矩阵和替代/互补响应不能解释为附件估计或因果关系；Q3方案未提高收益或下行表现；方案结构与Q2差异较大。
