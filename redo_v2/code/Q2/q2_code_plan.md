# Q2 Python implementation plan

Approved decision: `q2_full_horizon_scenario_reduction_1`.

The implementation generates complete 2024--2030 Monte Carlo paths, reduces raw paths with weighted K-medoids, solves a shared-decision seven-year stochastic MILP with weighted CVaR budget, and evaluates all plans on an independent test set. Q2-W and Q2-H are solved independently. Q2-B1 is the Q1 full-horizon mean-parameter plan; Q2-B2 is retained as a structural rolling comparator.

Inputs are the cleaned Q1 CSV contracts under `workspace/data_clean/`. Outputs go under `results/Q2/experiments/full_horizon_scenario_reduction_round1/`.

Default controls: seed 2026, N_raw=1000, K={20,40,60,80,100}, N_test=2000, triangular shocks, beta=0.95, area alpha=0.10. The executable supports environment overrides for probe runs (`Q2_N_RAW`, `Q2_K_LIST`, `Q2_N_TEST`, `Q2_TIME_LIMIT`).

Required evidence: scenario bounds/reproducibility, weighted medoid diagnostics, distribution and reference-plan CVaR errors, solver diagnostics, constraint validation, common-set out-of-sample metrics, seed/K stability, and ordinary-versus-tail reduction comparison. A fallback is recorded but not implemented unless the trigger is evidenced.

## Dynamic-programming path-reduction revision

Because the K=5 shared-decision MILP diagnostic showed excessive solve time and no CVaR incumbent, the next implementation revision is specified in `methods/Q2/q2_dynamic_programming_path_optimization_plan.md`: generate legal seven-year per-plot paths with DP/beam search, then solve a reduced shared path-selection stochastic MILP. This revision preserves the expected-profit objective, `CVaR^-_0.95(Pi) >= B` hard constraint, independent annual shocks with recursive cumulative levels, separate W/H rules, and no lambda weighting. Large-K formal experiments remain gated on K=5 CVaR incumbent evidence.
