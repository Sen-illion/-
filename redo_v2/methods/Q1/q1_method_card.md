# Q1 Method Card

## Approved main method

**Q1-M2: Recursive-State Full-Horizon MILP (RS-FH-MILP).** Optimize all 2024—2030 planting decisions in one seven-year model with explicit state-transition constraints for strict adjacent-cycle rotation, three-year cumulative bean-area coverage, irrigated-land modes, and greenhouse season states.

## Usable baseline

**Q1-B2: Three-year rolling MILP.** It remains a structural comparator, warm-start source, and computational fallback only. It is not the recommended seven-year policy and must not be described as globally optimal for the full horizon.

## Fixed modeling choices

- Main horizon: 2024—2030 full-horizon optimization.
- Minimum activated area: alpha = 10% of plot area.
- Q1(1) formal Pareto tolerance: eta = 1%; eta = 3% is the registered comparator.
- Price: midpoint of the supplied 2023 price interval.
- Demand proxy: 2023 observed production by crop.
- Bean rule: cumulative bean area >= plot area in every rolling three-year period, initialized with 2023 observations.
- Rotation: strict adjacent chronological planting cycles, with whole-plot activation.
- Q1(2): independently solve the half-price surplus objective.

## Claim boundary

The supplied data cover only 2023. Future values are scenario/modeling assumptions, not estimated historical time-series behavior. A time-limited incumbent is reported with its MIP gap and is not called a strict global optimum. Q1(1) Pareto results are labeled as feasible fallback plans when the minimum-waste stage obtains no new incumbent.

## Required evidence

Every formal plan must have independent hard-constraint validation, solver records, profit/waste metrics, concentration metrics, and a directly comparable rolling-baseline result.
