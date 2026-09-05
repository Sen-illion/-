# Q1 论文图组

这些图均由 `figure_sources/q1_figures.py` 从 `redo_v2/workspace/data_clean/` 和 `redo_v2/results/Q1/experiments/round2/tables/` 自动生成。

## 图组说明

- `Fig1_land_inventory`：54 个地块的土地类型、面积和地块数量；面积来自 `land.csv`。
- `Fig2_crop_economic_profile`：107 条经济参数记录按作物聚合后的典型亩产、成本、价格中点和亩均毛利。亩均毛利为 `典型亩产 × 价格中点 − 典型成本`，仅作规划参数描述，不作因果或显著性推断。
- `Fig3_baseline_2023_composition`：2023 年实际记录按地块类型和作物类型汇总。未记录面积没有被擅自补为 0。
- `Fig4_q1_policy_tradeoff`：Q1 round2 的 6 个已运行方案，横轴为浪费率，纵轴为总利润；圆点为主模型，方点为基准模型。半价销售情景的超产按结果文件口径不计为浪费。
- `Fig5_selected_policy_dynamics`：`m1_eta_01` 方案 2024—2030 年按土地类型和作物类型的年度种植面积。由于部分地块可种两季，单位明确写为“亩·季”。

## 重要口径

图中只展示源数据和已记录的 Q1 round2 结果，不插值、不补造观测、不添加显著性标记。图中涉及的“典型”数值采用经济参数记录的中位数，不能解释为统计样本均值或未来预测值。

## 文件格式

每张图同时提供 PNG（400 dpi）、PDF 和可编辑 SVG；对应的中间汇总数据保存在 `figure_sources/source_data/`。

## 画布类别

- `Fig1`、`Fig3`、`Fig4`：193.04 × 121.92 mm；
- `Fig2`：228.60 × 114.30 mm；
- `Fig5`：203.20 × 154.94 mm。

同一画布类别内部尺寸一致，插入论文时应按声明尺寸 100% 放置，不要在排版软件中单独拉伸。
