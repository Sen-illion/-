from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "code" / "common"))

from planting_optimizer import (  # noqa: E402
    concentration_metrics,
    evaluate_plan,
    generate_scenarios,
    load_inputs,
    load_plan,
    profit_distribution,
    save_plan,
    write_json,
)


OUTPUT = PROJECT_ROOT / "results" / "Q3" / "experiments" / "round1"
Q2_PLAN = PROJECT_ROOT / "results" / "Q2" / "experiments" / "round1" / "tables" / "result2_main.csv"
SCENARIO_COUNT = 30
SEED = 20240902


def run_baseline():
    land, crops, planting, economics = load_inputs()
    if not Q2_PLAN.exists():
        raise FileNotFoundError("Q2 main plan is required before Q3 baseline evaluation")
    plan = load_plan(Q2_PLAN, land)
    scenarios, metadata = generate_scenarios(
        crops, SCENARIO_COUNT, SEED, correlated=True, relationship_strength=1.0
    )
    evaluation = evaluate_plan(plan, land, planting, economics, scenarios, 0.50)
    tables = OUTPUT / "tables"
    metrics_dir = OUTPUT / "metrics"
    save_plan(tables / "result3_baseline_q2_plan.csv", plan, land, crops)
    evaluation.to_csv(tables / "baseline_q2_plan_correlated_scenario_metrics.csv", index=False, encoding="utf-8-sig")
    metrics = {
        **profit_distribution(evaluation),
        **concentration_metrics(plan),
        "scenario_metadata": metadata,
    }
    write_json(metrics_dir / "baseline_metrics.json", metrics)
    return plan, evaluation, scenarios, metadata, metrics


if __name__ == "__main__":
    run_baseline()
