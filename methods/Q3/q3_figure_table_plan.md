# Q3 图表计划

| ID | 类型 | 核心结论 | 形式 | 数据源 | 目标位置 | 状态 |
|---|---|---|---|---|---|---|
| Q3-FIG-1 | Type 3 | 三档相关强度、三个新种子下，Q3-Q2 平均利润差始终为负 | 三种子点线图，零线为参照 | `results/Q3/reports/frozen_numbers.json`；`q3_stability_verdict_round1` | Q3 对照与限制 | 已生成并通过目视核验：`paper/figures/q3_relationship_robustness.svg`、`.png` |
| Q3-TAB-1 | 论文表 | Q3 与 Q2 对照方案的均值、下行利润、超产率和面积重合度 | 精确数值表 | `results/Q3/experiments/round1/run_summary.json` | Q3 结果 | 已有数据，待论文排版 |
| Q3-TAB-2 | 附录表 | 0.5、1.0、1.5 关系强度下的利润分布摘要 | 精确数值表 | `results/Q3/experiments/round1/tables/relationship_sensitivity_summary.csv` | 附录 | 已有数据，待论文排版 |

不绘制相关矩阵热图作为主结果，因为矩阵是模拟设定而非数据估计；正文用公式明确给出即可。
