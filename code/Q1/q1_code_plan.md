# Q1 Python Code Plan

- Target: Python, `round1`.
- Approved decision: `q1_method_choice`.
- Main: `Q1-M1`, three-year receding-horizon MILP.
- Baseline: `Q1-B1`, feasible cyclic profit-ranked policy.
- Dormant fallback: `Q1-F1`; activate only if a rolling window exceeds 5% MIP gap.

## Inputs and units

- `workspace/data_clean/land.csv`: plot ID, land type, area in 亩.
- `workspace/data_clean/crops.csv`: crop ID/name/type.
- `workspace/data_clean/planting_2023.csv`: 2023 plot-season history and area in 亩.
- `workspace/data_clean/economics_2023.csv`: yield 斤/亩, cost 元/亩, price bounds 元/斤.
- Price uses interval midpoint; 2023 production is expected-sales proxy. Smart-greenhouse first season temporarily reuses its supplied second-season economics.

## Main computation

1. Build legal plot-season-crop slots and 2023 state.
2. For each year, solve a window of the current year plus up to two future years; commit only the current-year decisions.
3. Enforce capacity, land suitability, water mode, minimum positive area, adjacent-season no-repeat planting, and every rolling three-year bean-area coverage.
4. Q1(1): normal-price sales capped by expected demand; excess has no revenue and receives an additional 0.5-price waste penalty.
5. Q1(2): excess receives 50% of normal price.
6. Add a small data-scaled activation penalty to discourage fragmentation.

## Baseline computation

Generate a full seven-year legal cyclic plan that chooses high per-acre margin crops by land/season, alternates consecutive crops, and schedules a full-area bean crop at least once per three years.

## Outputs and comparison

- `results/Q1/experiments/round1/tables/result1_1_main.csv`
- `results/Q1/experiments/round1/tables/result1_2_main.csv`
- corresponding baseline tables and yearly/case metrics.
- Compare profit, waste quantity/rate, crop count, top-5 area mass, assignment count, minimum area, hard-constraint errors, runtime, and maximum MIP gap.
- Fixed seed: `20240902`.

## Required monitors

- Each committed window is feasible; target MIP gap ≤5%.
- No capacity, suitability, rotation, water-mode, or bean-window violation.
- Price-perturbation sensitivity and concentration metrics are retained.
- Fallback trigger is observed when any production window exceeds 5% gap; fallback is not implemented in this round.

## Review checks

`syntax`, `input_contract`, `method_alignment`, `reproducibility`, `output_contract`, plus constraint feasibility and scale.
