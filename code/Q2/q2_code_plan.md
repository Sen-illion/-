# Q2 Python Code Plan

- Target: Python, `round1`.
- Approved decision: `q2_method_choice`.
- Main: `Q2-M1`, independent-scenario receding-horizon stochastic MILP with downside-risk weight.
- Baseline: `Q2-B1`, mean-parameter receding-horizon MILP evaluated on the same scenarios.
- Dormant fallback: `Q2-F1`, triggered only by solver gap or instability evidence.

## Inputs and scenario contract

Use the same cleaned fields and units as Q1. Generate at most 60 scenarios with seed `20240902`: wheat/corn annual sales growth within 5%–10%; other sales within ±5%; yield within ±10%; cost trend near +5% annually with small bounded variation; grain price stable, vegetable price +5% annually, fungi prices decline within the stated ranges and morel by 5%. Excess production sells at 50% normal price.

## Main and baseline

- Main uses shared planting decisions across scenarios, scenario-specific normal sales, expected profit, and a lower-tail/CVaR term with a documented moderate risk weight.
- Baseline solves with mean multipliers only, then is evaluated over the main method's exact scenario set.
- Both use the Q1 receding-horizon hard constraints and fragmentation control.

## Outputs

- `results/Q2/experiments/round1/tables/result2_main.csv`
- baseline plan, annual metrics, scenario-profit table, and comparison table.
- Metrics: mean, standard deviation, 5th percentile, lower-10% mean, expected waste, crop/area concentration, feasibility, runtime and MIP gaps.
- Canonical `run_summary.json` records all scenario assumptions and warnings.

## Monitors and review

Target each window MIP gap ≤5%; record scenario count, seed reproducibility, concentration, and fallback state. Required review checks are the five named Python checks plus scenario-bound and constraint-feasibility checks.
