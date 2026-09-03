# Q3 Python Code Plan

- Target: Python, `round1`.
- Approved decision: `q3_method_choice`.
- Main: `Q3-M1`, correlated category-level scenario receding-horizon stochastic MILP.
- Baseline: `Q3-B1`, Q2 independent-scenario plan evaluated against comparable marginals.
- Dormant fallback: `Q3-F1`.

## Simulated relationship contract

Use the Q2 marginal ranges. Introduce a positive-definite moderate correlation structure among yield, cost, demand and price shocks; group crops into grains, legumes, vegetables and fungi for substitute cross-price responses. Add a small simulated complementarity response between legume availability and non-legume demand/yield context. These are labeled simulated assumptions, not estimates. Run relationship strengths at 0.5×, 1.0× and 1.5×; optimize at 1.0× and use the others for sensitivity.

## Computation and outputs

- Main uses the same approved stochastic rolling MILP and 50% surplus rule as Q2, changing only the joint scenario generator.
- Baseline is the Q2 independent scenario result under the same marginal distributions and metrics.
- Save `result3_main.csv`, relationship-sensitivity metrics, scenario profits, and a direct Q2-versus-Q3 comparison under `results/Q3/experiments/round1/`.
- Report mean profit, 5th percentile, lower-10% mean, waste, concentration, plan-area overlap, and direction stability across 0.5×/1.0×/1.5×.

## Monitors and review

Require positive semidefinite correlation matrices, bounded marginals, fixed seed, legal plans, and claims explicitly marked as simulation-dependent. Trigger `Q3-F1` if strength perturbation gives plan overlap below70% or reverses the main comparison direction. Required review checks are the five named Python checks plus correlation validity and sensitivity completeness.
