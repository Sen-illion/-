# Q2 Method Card

## Goal and success criteria

在题面给定的销量、亩产、成本和价格变化范围内，基于 Q1 的七年整体递归状态可行域，生成 2024--2030 年兼顾期望收益与下行情景风险的种植方案。主方法必须在所有情景共享同一套事前种植决策，并使用同一套约束和评价口径与基线比较。

## Human constraints

- Output form: 附件3中的 `result2.xlsx`（模板尚缺）。
- Priority: 收益与风险平衡，同时避免 Q1 已发现的滚动路径短视。
- Unacceptable failure: 情景越界、随机结果不可复现、情景间泄漏未来信息、只报告均值而掩盖下行风险、未分别说明 Q2 超产处置规则，或把有限时间 incumbent 宣称为全局最优。
- Experiment budget: 轻量探针 50--100 个情景；正式优化首轮 100--200 个情景；独立样本外测试不少于 2000 个新情景。

## Shortlist

| ID | Role | Mathematical idea | Why eligible | Main risk | Implementation cost |
|---|---|---|---|---|---|
| Q2-M1 | main_candidate | 七年整体情景随机 MILP，以递归状态转移继承 Q1 可行域，并以期望七年利润最大化、CVaR 风险预算控制下行风险 | 与 Q1 的 RS-FH-MILP 结构一致，避免三年滚动短视；可直接处理销量、亩产、成本和价格不确定性 | 情景数量导致销售与 CVaR 变量膨胀；概率分布和共同冲击属于建模假设 | 高 |
| Q2-B1 | usable_baseline | 七年整体均值参数 MILP，随后在与主方法相同的独立情景集上样本外评价 | 完成真实七年方案，可量化忽略参数不确定性的代价 | 可能对尾部情景脆弱 | 中 |
| Q2-B2 | structural_comparator | 原三年滚动情景 MILP，仅用于比较滚动短视损失、生成 warm start 或提供可行下界 | 保留原 Q2 方法作为直接结构对照，但不再作为主方案 | 窗口间路径短视，不能代表七年整体最优 | 中高 |
| Q2-F1 | conditional_fallback | 地块级七年合法路径生成 + 总体情景协调 MILP；必要时采用预算/区间稳健约束 | 整体模型超时或情景结论不稳定时仍能保留递归状态和硬约束 | 路径候选集可能限制全局最优，稳健模型可能过度保守 | 中高 |

## Baseline validity

- Real task completed: 是；Q2-B1 使用 Q1 同一七年整体决策结构，仅将未来参数替换为均值，并完成七年方案后再做样本外评价。
- Comparable output/metric: 是；Q2-M1、Q2-B1、Q2-B2 在相同测试情景、相同超产规则、相同硬约束验证器下比较七年累计利润、5% 分位数、下10%均值、CVaR、超产率和结构指标。
- Q2-B2 仅为结构对照，不承担正式 baseline 的角色。

## Model interface inherited from Q1

- 主规划范围：2024--2030 七年整体 MILP；三年滚动仅作对照、warm start 和回退。
- 共享决策：`x,z` 以及作物历史、豆类面积和地块模式状态在情景间共享。
- 情景变量：`Q,u,e,Pi` 随情景变化；不得为每个情景单独设置种植方案。
- 约束口径：严格相邻种植周期重茬、整块启用、连续三年豆类累计面积覆盖、相对最小面积 10%、水浇地模式互斥和正确的大棚参数映射全部沿用 Q1。
- 2023 年实际种植和豆类面积作为初始状态；2031--2032 年虚拟过渡期或等价终端状态检查必须纳入验证。

## Risk-probe summary

| ID | Executability | Data/assumptions | Degeneracy | Sensitivity | Scale | Verdict |
|---|---|---|---|---|---|---|
| Q2-M1 | 情景生成和评价链已可执行；七年整体联合优化器需在 Q1 接口冻结后实现 | 参数范围符合题面；三角分布为主，均匀分布和共同天气冲击作敏感性 | 检查作物集中度、地块碎片化及利润分布，避免只得到少数作物方案 | 测试随机种子、分布、CVaR 预算和情景数 50/100/200 | 情景变量随样本数线性增长；先做小情景探针，必要时路径分解 | CONDITIONAL |
| Q2-B1 | 七年整体均值模型可执行性需与 Q1 主模型共同确认 | 仅使用 2023 观测作为需求代理，不泄漏未来真实值 | 检查均值方案的集中度和尾部脆弱性 | 在同一测试情景集上评价 | 变量规模小于 Q2-M1 | CONDITIONAL |
| Q2-B2 | 原滚动情景链可执行 | 与 Q1 约束保持一致 | 检查窗口路径不一致和后期风险恶化 | 与七年整体方法比较短视损失 | 计算量较低，可作 warm start | CONDITIONAL |

## Objective and surplus rules

对每个情景计算七年累计利润 `Pi^omega`，CVaR 针对 `-Pi^omega` 定义。主模型优先采用风险预算形式：

$$
\max \frac1N\sum_\omega \Pi^\omega
\quad\text{s.t.}\quad
\operatorname{CVaR}_{\beta}(-\Pi)\le \kappa,
$$

其中 `beta=0.95`，`kappa` 以均值基线样本外 CVaR 为参照测试 90%、100%、110% 三个水平。`E[Pi]-lambda*CVaR` 仅作敏感性分析。

Q2-W 与 Q2-H 必须分别求解：W 为超产完全滞销，H 为超产按正常价格 50% 销售；两者不在模型内隐式择一，也不复用对方的种植面积方案。

## Cross-year stochastic evolution

对需要按年度变化率演化的参数，年度变化率独立抽样，但参数水平递推累计：

\[
X_t=X_{t-1}(1+r_t),\qquad X_{2023}\text{ 为基准},
\]

即 \(X_t=X_{2023}\prod_{k=2024}^{t}(1+r_k)\)。年度变化率之间不加入 AR(1) 或其他人为相关结构；参数水平因递推关系自然具有跨年依赖。禁止使用 \(X_t=X_{2023}(1+r_t)\) 的逐年重置写法。情景文件必须记录各类参数的变化率分布、上下界、独立抽样标记、递推标记、公式和 random seed。

## Fallback trigger

- Trigger: 七年整体模型在预算内无 incumbent 或选定窗口 gap 超过 5%；增加情景数或更换合理分布后主要面积重合度低于 70%；或主方法样本外下10%利润/CVaR 显著劣于均值基线且无法由风险预算解释。
- Evidence to evaluate: 正式 Q2 `run_summary.json`、solver window records、样本外指标、约束验证和稳定性报告。

## Compact history

- 2026-09-02：完成 100 个独立情景的生成、固定种子复现和均值方案样本外评价。
- 2026-09-03：确认滞销浪费与半价销售两种口径均需计算。
- 2026-09-05：根据 Q1 RS-FH-MILP 更新 Q2：七年整体情景随机 MILP 为主方法，三年滚动降为结构对照、warm start 和回退用途；增加非预见性、终端状态、风险预算和独立测试集要求。
