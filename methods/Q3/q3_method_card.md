# Q3 Method Card

## Goal and success criteria

在Q2基础上引入明确标识为模拟的作物替代/互补与销量—价格—成本相关结构，生成七年方案，并使用相同测试情景与Q2比较种植结构、平均收益和下行风险。

## Human constraints

- Output form: 七年种植策略及与Q2的可比分析。
- Priority: 收益与风险平衡，不把模拟相关性表述为观测事实或因果结论。
- Unacceptable failure: 非正定相关矩阵、边际范围越界、结论由单一任意参数设定驱动。
- Experiment budget: 轻量；探针使用100个相关情景。

## Shortlist

| ID | Role | Mathematical idea | Why eligible | Main risk | Implementation cost |
|---|---|---|---|---|---|
| Q3-M1 | main_candidate | 在Q2情景随机 MILP 中加入类别层面的相关模拟与替代/互补响应参数，保持边际变化范围 | 直接对应题目要求，并能与Q2共享约束和指标 | 参数无法由单年附件识别，结论可能由假设主导 | 高 |
| Q3-B1 | usable_baseline | Q2的独立情景方案，使用相同边际分布和评价样本 | 完整解决同一任务，是隔离“相关结构”影响的可比基线 | 不反映题目要求的关联因素 | 中 |
| Q3-F1 | conditional_fallback | 不重优化，只对Q2方案做弱/中/强相关压力测试 | 当替代/互补参数证据不足时避免过度建模 | 只能给策略稳健性边界，不能声称得到充分相关优化 | 低 |

## Baseline validity

- Real task completed: 是；Q2独立情景模型给出相同格式的七年方案。
- Comparable output/metric: 是；仅改变联合依赖结构，边际变化与评价指标保持一致。

## Risk-probe summary

| ID | Executability | Data/assumptions | Degeneracy | Sensitivity | Scale | Verdict |
|---|---|---|---|---|---|---|
| Q3-M1 | 100个相关情景已生成并可复现；候选相关矩阵最小特征值0.5832，为合法正定矩阵 | 相关方向和强度仅为模拟设定；替代/互补组尚待选择 | 固定方案收益标准差约83.52万元，无常数输出 | 当前示例相关结构使下10%均值比独立情景高约4.34万元，效应很小且不足以定论 | 与Q2相同，需滚动窗口控制规模 | CONDITIONAL |
| Q3-B1 | 独立情景链已运行 | 边际分布与Q3一致 | 输出可比较 | 不包含相关性，作为基准而非结论 | 符合轻量预算 | PASS |

## Fallback trigger

- Trigger: 替代/互补参数无法获得人工认可，或相关强度±50%时策略方向反复变化、面积重合度低于70%。
- Evidence to evaluate: `methods/probe_metrics.json` 与后续相关强度敏感性摘要。

## Compact history

- 2026-09-02：相关情景引擎通过正定性与复现检查；因参数不可识别，主候选保持条件通过。
