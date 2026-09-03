# Q2 Method Card

## Goal and success criteria

在题面给定的销量、亩产、成本和价格变化范围内，生成兼顾期望收益与下行情景的 2024–2030 年可行方案，并与确定性/均值方案使用同一评价口径。

## Human constraints

- Output form: 附件3中的 `result2.xlsx`（模板尚缺）。
- Priority: 收益与风险平衡。
- Unacceptable failure: 情景越界、随机结果不可复现、只报告均值而掩盖下行风险，或未说明Q2超产处置规则。
- Experiment budget: 轻量；探针使用100个情景，正式首轮不超过200个。

## Shortlist

| ID | Role | Mathematical idea | Why eligible | Main risk | Implementation cost |
|---|---|---|---|---|---|
| Q2-M1 | main_candidate | 三年滚动的情景平均近似随机 MILP，以期望利润和下尾利润/CVaR共同评价 | 延续Q1可行域并直接处理题面不确定范围，符合收益—风险平衡 | 概率分布为情景假设；情景变量规模随样本数增长 | 中高 |
| Q2-B1 | usable_baseline | 使用均值参数求滚动 MILP，再在同一100个情景上进行样本外评价 | 完成真实七年方案，能量化“忽略不确定性”的代价 | 可能对尾部情景脆弱 | 中 |
| Q2-F1 | conditional_fallback | 区间/预算稳健优化，不依赖精确概率分布 | 当情景结论对分布或随机种子不稳定时更可靠 | 可能过度保守并牺牲平均收益 | 中 |

## Baseline validity

- Real task completed: 是；沿用Q1滚动 MILP 的完整决策结构，仅用均值参数求解。
- Comparable output/metric: 是；主方法与基线都在同一固定种子、同一情景集上比较均值、5%分位数和下10%均值。

## Risk-probe summary

| ID | Executability | Data/assumptions | Degeneracy | Sensitivity | Scale | Verdict |
|---|---|---|---|---|---|---|
| Q2-M1 | 100个情景生成、固定种子复现和方案评价已运行；联合优化器尚未正式生成 | 变化范围符合题面；分布形式与Q2超产规则待确认 | 固定均值方案的收益标准差约84.76万元，未发现常数输出 | 100个情景下5%分位约4,606.55万元，下10%均值约4,597.78万元 | 200情景预计增加82,600个销售变量，需滚动窗口 | CONDITIONAL |
| Q2-B1 | 均值方案及100情景评价链可执行 | 不使用未来观测估计 | 必须在正式求解后检查作物和地块集中度 | 与分布设定和超产规则相关 | 符合轻量预算 | CONDITIONAL |

## Fallback trigger

- Trigger: 更换合理分布/随机种子后，方案面积重合度低于70%，或下10%利润显著恶化，或联合模型任一窗口在预算内缺口超过5%。
- Evidence to evaluate: `methods/probe_metrics.json`、正式Q2运行摘要。

## Compact history

- 2026-09-02：在100个独立情景上验证种子可复现与利润分布；Q2超产处置规则仍需人工选择。
- 2026-09-03：用户确定滞销浪费与半价销售两种口径都计算后再确定 `result2`；稳健方法链 B 仅为初步倾向，尚未改变候选角色。
