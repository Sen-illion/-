from __future__ import annotations

import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "code" / "common"))

from planting_optimizer import (  # noqa: E402
    concentration_metrics,
    evaluate_plan,
    greedy_baseline,
    load_inputs,
    profit_distribution,
    save_plan,
    unit_scenario,
    validate_plan,
    write_json,
)


OUTPUT = PROJECT_ROOT / "results" / "Q1" / "experiments" / "round1"


def run_baseline():
    land, crops, planting, economics = load_inputs()
    tables = OUTPUT / "tables"
    metrics_dir = OUTPUT / "metrics"
    tables.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    plan = greedy_baseline(land, planting, economics)
    errors = validate_plan(plan, land, planting)
    save_plan(tables / "result1_baseline.csv", plan, land, crops)
    case1_eval = evaluate_plan(plan, land, planting, economics, [unit_scenario()], 0.0)
    case2_eval = evaluate_plan(plan, land, planting, economics, [unit_scenario()], 0.5)
    case1_eval.to_csv(tables / "result1_1_baseline_annual_metrics.csv", index=False, encoding="utf-8-sig")
    case2_eval.to_csv(tables / "result1_2_baseline_annual_metrics.csv", index=False, encoding="utf-8-sig")
    metrics = {
        "Q1_case_1": {**profit_distribution(case1_eval), **concentration_metrics(plan)},
        "Q1_case_2": {**profit_distribution(case2_eval), **concentration_metrics(plan)},
        "constraint_error_count": len(errors),
        "constraint_errors": errors,
        "execution_time_seconds": time.perf_counter() - started,
    }
    write_json(metrics_dir / "baseline_metrics.json", metrics)
    return plan, metrics


if __name__ == "__main__":
    run_baseline()
