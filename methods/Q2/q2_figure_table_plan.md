# Q2 图表计划

| ID | 类型 | 核心结论 | 形式 | 数据源 | 目标位置 | 状态 |
|---|---|---|---|---|---|---|
| Q2-FIG-1 | Type 3 | 五个新种子下，主方案相对基线的平均利润和下行利润增量均为正 | 双指标点线图，零线为参照 | `results/Q2/reports/frozen_numbers.json`；`q2_stability_verdict_round1` | Q2 稳健性 | 已生成并通过目视核验：`paper/figures/q2_seed_robustness.svg`、`.png` |
| Q2-TAB-1 | 论文表 | 主方案与均值参数基线的均值、标准差、5%分位、最差10%均值和超产率 | 精确数值表 | `results/Q2/experiments/round1/run_summary.json` | Q2 结果 | 已有数据，待论文排版 |

不另画与表格重复的主/基线柱状图；收益差较小，零起点柱状图会压缩信息，而截断轴又易夸大差异。
