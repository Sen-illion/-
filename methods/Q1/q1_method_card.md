# Q1 Method Card

## Goal and success criteria

在两种超产处置规则下生成 2024–2030 年逐地块、逐季、逐作物的可行种植方案；满足适种、面积、轮作、三年豆类覆盖和管理约束。Q1(1) 显式提高避免滞销浪费的优先级，同时保留收益证据。

## Human constraints

- Output form: 附件3模板中的 `result1_1.xlsx` 与 `result1_2.xlsx`（模板尚缺）。
- Priority: 收益与风险平衡；Q1(1) 提高控制滞销浪费优先级。
- Unacceptable failure: 违反硬约束、形成不可实施碎片化方案，或把未收敛解当成最优解。
- Experiment budget: 轻量，每轮情景不超过约 200；确定性求解也应采用受控时间窗口。

## Shortlist

| ID | Role | Mathematical idea | Why eligible | Main risk | Implementation cost |
|---|---|---|---|---|---|
| Q1-M1 | main_candidate | 三年重叠滚动窗口 MILP；面积为连续变量、种植启用与水浇地模式为0-1变量；Q1(1)加入显式超产惩罚/约束，Q1(2)线性化半价收入 | 能直接表达全部地块、轮作和豆类约束，并适配轻量预算 | 窗口间可能损失全局最优；目标和价格小扰动可能改变地块分配 | 中 |
| Q1-B1 | usable_baseline | 合法的利润排序循环贪心：按地类选高毛利作物，强制轮作与三年豆类覆盖 | 完整输出七年逐地块方案，运行极快，可作同口径下界比较 | 产量过度集中并忽略全局销量耦合 | 低 |
| Q1-F1 | conditional_fallback | 按地类聚合的线性规划，再做逐地块分配与约束修复 | 当窗口 MILP 的最优性缺口或耗时超预算时可快速给出可行近似 | 修复步骤可能损失目标值，必须重新验约束 | 中低 |

## Baseline validity

- Real task completed: 是；探针生成 574 个种植分配，覆盖七年并通过面积、适种结构、连续重茬和三年豆类覆盖检查。
- Comparable output/metric: 是；可计算同一销量、价格、成本口径下的利润、浪费量与集中度。
- Condition: 仅作基线，不作最终推荐；其前5作物面积占比 96.56%，Q1(1) 浪费率 92.12%，需明确标记为集中型下界。

## Risk-probe summary

| ID | Executability | Data/assumptions | Degeneracy | Sensitivity | Scale | Verdict |
|---|---|---|---|---|---|---|
| Q1-M1 | 三年窗口 6,573 变量、3,210 整数变量，14.88秒达到0.81%缺口 | 智慧大棚第一季经济参数暂复用第二季，条件通过 | 41种作物被使用，前5面积占60.86%，浪费率2.13% | ±5%价格探针在20秒内未收敛，分配重合度证据不稳定 | 完整七年单体模型45秒仍有19%–57%缺口；滚动窗口可行 | CONDITIONAL |
| Q1-B1 | 全七年即时生成且硬约束检查为0错误 | 使用同一数据口径 | 仅8种作物、前5占96.56%，明显集中 | 对销量规则高度敏感 | 运行成本低 | CONDITIONAL |

## Fallback trigger

- Trigger: 任一滚动窗口在限定时间内最优性缺口超过5%，或价格小扰动后仍无法在相同时间内把缺口压到5%以内。
- Evidence to evaluate: `methods/probe_reduced_metrics.json`、正式运行摘要与约束复核。

## Compact history

- 2026-09-02：根据 `global_framing_choice_1` 建立轻量、浪费优先的候选结构；完整七年单体 MILP 因规模风险改为三年重叠窗口。
