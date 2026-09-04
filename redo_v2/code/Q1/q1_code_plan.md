# Q1 Python 实现与实验契约

状态：`APPROVED METHOD / IMPLEMENTATION PLAN`  
轮次：`round1`  
目标语言：Python 3（SciPy/HiGHS、pandas、NumPy）  
批准决策：`q1_method_choice_1`

## 1. 本轮范围

只实现并比较：

- 主方法 `Q1-M1`：三年重叠滚动 MILP；
- 可用 baseline `Q1-B1`：带豆类期限预留和逐地块合法性检查的确定性利润排序贪心；
- 两者共用的数据加载、经济参数映射、指标计算和硬约束验证。

条件备用 `Q1-F1` 只记录触发条件，不实现。禁止读取隔离目录外的旧代码、旧方案或旧结果；`methods/Q1/probes` 仅提供方法与风险证据，不提供正式数值初值。

## 2. 输入契约

| 文件 | 主键/必要字段 | 单位 | 用途 |
|---|---|---|---|
| `workspace/data_clean/land.csv` | `plot_id, land_type, area_mu` | 亩 | 地块容量和地类 |
| `workspace/data_clean/crops.csv` | `crop_id, crop_name, crop_type` | — | 作物类别及豆类集合 |
| `workspace/data_clean/planting_2023.csv` | `plot_id, crop_id, area_mu, season` | 亩 | 销量代理、2023 重茬历史、豆类实际面积历史 |
| `workspace/data_clean/economics_2023.csv` | `crop_id, land_type, season, yield_jin_per_mu, cost_yuan_per_mu, price_low_yuan_per_jin, price_high_yuan_per_jin` | 斤/亩、元/亩、元/斤 | 产量、成本和价格中点 |

输入加载必须验证主键、非负/正值、地块与作物引用、2023 分季面积不超地块面积，以及每个合法作物—地类—季次组合均能取得经济参数。

智慧大棚第一季蔬菜必须映射到普通大棚第一季参数；智慧大棚第二季使用智慧大棚第二季参数。不得回退到旧的“第一季复用智慧大棚第二季”映射。

## 3. 共同数学对象

- 年份：2024–2030；滚动窗为 2024–2026、2025–2027、……、2028–2030、2029–2030、2030。
- 面积变量：$x_{ijts}\ge0$；启用变量：$y_{ijts}\in\{0,1\}$。
- 相对最小面积：$0.1A_i y_{ijts}\le x_{ijts}\le A_i y_{ijts}$。
- 正常销售量：$0\le u_{jts}\le Q_{jts}$ 且 $u_{jts}\le d_j$；$d_j$ 为按最新参数映射计算的 2023 实际产量代理。
- 报告经济利润不包含启用惩罚。极小启用项只作 tie-break，并记录其最大可能影响占利润的比例。
- 豆类面积：$X^B_{it}=\sum_{j\in B,s}x_{ijts}$；每个完整三年窗满足 $\sum_{\tau=t-2}^{t}X^B_{i\tau}\ge A_i$。
- 每次滚动提交当年决策，并向后续窗口传递逐地块、逐作物面积以及前两年豆类实际面积。

硬约束还包括地块季次容量、适种范围、水浇地单季水稻/两季蔬菜模式互斥，以及当前方法卡批准的保守重茬口径：同一地块某作物若在年份 $t$ 任一季启用，则年份 $t+1$ 不得启用；智慧大棚同一年两季也不得种同一作物。

面积覆盖模型依赖“地块内部土壤近似均匀”的已记录假设，不声称追踪物理子地块。

## 4. Q1-M1 计算流程

### 4.1 Q1(1) 零超产价格纯利润基准

对每个滚动窗最大化

$$
\Pi=\sum p_j u_{jts}-\sum c_{jL_is}x_{ijts},
$$

并只用一个量级经审计的极小 $-\varepsilon\sum y$ 打破近似并列。形成独立方案 `m1_zero_price_profit`，同时为对应历史路径上的 Pareto 二阶段提供 $\Pi^*$。

### 4.2 Q1(1) 正式 Pareto 主点与对照

分别独立滚动运行：

- `m1_eta_01`：$\eta=1\%$，正式主点；
- `m1_eta_03`：$\eta=3\%$，预注册稳健性对照。

每个窗口先在该策略自己的已提交历史下求 $\Pi^*$，再求

$$
\min W+\varepsilon_y\sum y,
\qquad \Pi\ge(1-\eta)\Pi^*.
$$

经济利润约束必须与启用 tie-break 分离。仅允许预先声明的数值可行容差，不允许根据结果移动 $\eta$。

### 4.3 Q1(2) 半价销售

独立滚动运行 `m1_half_price`，最大化

$$
\Pi_2=\sum p_j u_{jts}+0.5p_j(Q_{jts}-u_{jts})-\sum c_{jL_is}x_{ijts}.
$$

## 5. Q1-B1 修正版 baseline

baseline 必须从清洗附件重新生成，不读取旧分配。

1. 按地块计算 2023 年实际豆类面积。若 2023 豆类面积达到 $A_i$，预留整块豆类年份 2026、2029；否则预留 2025、2028。该确定性安排使所有三年窗口具备至少一次整块豆类覆盖。
2. 豆类年份在合法季次中选择不违反保守重茬、且基准亩利润最高的豆类；必要时在豆类集合中顺次替换。
3. 其余地块—年份按合法候选的边际收益排序贪心填充；水浇地比较单季水稻与两季蔬菜模式；每个启用组合使用整块面积，因而自动满足 $\alpha=10\%$。
4. 分别生成 `b1_zero_price` 与 `b1_half_price`。零价方案按剩余正常销量计算边际收益；半价方案对超过剩余正常销量的产量按 50% 价格计入边际收益。
5. 生成后必须调用与主方法相同的独立验证器。任何硬约束违规都使 baseline 状态为 `failed`，不得以“已修复”文字替代重新验证。

## 6. 求解预算与预注册处置

- 随机种子：2026（排序仍用稳定键确保确定性）。
- 每个 MILP 阶段初始上限 60 秒，目标 relative gap 5%。
- 若有 incumbent 但 gap 在 5%–10%，或没有 incumbent，则仅允许一次 180 秒定向重试；必须保留首轮状态、耗时和 gap。
- 若重试后任一正式主点窗口仍无 incumbent 或 gap 超过 5%，记录 `Q1-F1` 触发为真，但不在本轮自动实现 fallback。
- 不因求解结果修改 $\eta$、$\alpha$、豆类约束或智慧大棚映射。

## 7. 统一评价与验证

主方法和 baseline 按相同口径输出：

- 总经济利润、利润损失率；
- 总产量、总浪费量、浪费率；
- 启用组合数、平均单组合面积、最小正面积；
- 作物数、前5作物面积占比和 HHI；
- 地块/季次容量、适种、模式互斥、重茬、最小面积、三年豆类面积覆盖的违规数及最大违规量；
- 每个滚动窗口各阶段耗时、状态、节点数和 optimality gap。

Q1(1) 至少比较 `m1_zero_price_profit`、`m1_eta_01`、`m1_eta_03`、`b1_zero_price`；Q1(2) 比较 `m1_half_price` 与 `b1_half_price`。

## 8. 输出契约

```text
code/Q1/
├── q1_model.py
├── q1_baseline.py
├── q1_common.py
├── run_q1_round1.py
└── reviews/q1_python_review.json

results/Q1/experiments/round1/
├── tables/
│   ├── m1_zero_price_profit_plan.csv
│   ├── m1_eta_01_plan.csv
│   ├── m1_eta_03_plan.csv
│   ├── m1_half_price_plan.csv
│   ├── b1_zero_price_plan.csv
│   ├── b1_half_price_plan.csv
│   ├── method_comparison.csv
│   └── window_solver_records.csv
├── metrics/
│   ├── method_metrics.json
│   └── constraint_validation.json
├── logs/                  # 仅在失败、超时或警告存在时创建
└── run_summary.json
```

附件 3 缺失时不伪造最终 `result1_1.xlsx/result1_2.xlsx` 模板，只保存可审计的长表 CSV；获得模板后再做格式映射。

`run_summary.json` 必须记录 `q1_method_choice_1`、全部输入文件、环境版本、每种方法状态、输出文件、指标摘要、警告/错误、旧结果未复用声明，以及 fallback 是否触发。

## 9. 下游代码审查命名检查

- `syntax`
- `input_contract`
- `method_alignment`
- `reproducibility`
- `output_contract`
- `smart_greenhouse_mapping`
- `bean_area_coverage`
- `legacy_result_isolation`
- `solver_status_and_gap_reporting`

任一核心检查失败时不得把 manifest 提升到 G3。
