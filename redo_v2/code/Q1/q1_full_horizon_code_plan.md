# Q1 Full-Horizon Python Implementation Plan

## Approved method

Main method: recursive-state full-horizon MILP over 2024--2030. The model uses explicit area, activation, normal-sales, and surplus variables; whole-plot activation; strict adjacent planting-cycle rotation; and three-year cumulative bean-area coverage initialized from 2023.

Usable baseline: the existing legal rolling greedy allocator using the same cleaned inputs and independent validator.

## Objectives

- `full_pure_profit`: maximize normal-price economic profit.
- `full_eta_01`: minimize total surplus subject to profit >= 99% of the pure-profit incumbent.
- `full_eta_03`: the registered comparator at 97% of the pure-profit incumbent.
- `full_half_price`: maximize normal-price plus 50%-price surplus revenue minus cost.

## Evidence contract

Each run writes a complete seven-year plan as CSV and XLSX, an independent hard-constraint validation JSON, a solver summary, and a shared `run_summary.json`. Solver status, incumbent, and MIP gap are reported. If a Pareto stage has no incumbent, the pure-profit feasible plan is used only as a declared heuristic fallback and is not called Pareto-optimal.

## Acceptance checks

Syntax, input contract, method alignment, reproducibility, output contract, independent rotation/bean/capacity validation, and solver-gap disclosure must all be recorded by the Python reviewer.
