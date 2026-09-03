from __future__ import annotations

import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "code" / "common"))

from planting_optimizer import (  # noqa: E402
    concentration_metrics,
    evaluate_plan,
    generate_scenarios,
    load_inputs,
    profit_distribution,
    rolling_optimize,
    save_plan,
    write_json,
)


OUTPUT = PROJECT_ROOT / "results" / "Q3" / "experiments" / "round1"
SCENARIO_COUNT = 30
SEED = 20240902


def run_main():
    land, crops, planting, economics = load_inputs()
    tables = OUTPUT / "tables"
    metrics_dir = OUTPUT / "metrics"
    tables.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    scenarios, metadata = generate_scenarios(
        crops, SCENARIO_COUNT, SEED, correlated=True, relationship_strength=1.0
    )
    started = time.perf_counter()
    plan, windows = rolling_optimize(
        land, planting, economics, scenarios,
        surplus_fraction=0.50,
        waste_weight=0.0,
        risk_weight=0.15,
        time_limit=20,
        mip_gap=0.05,
    )
    evaluation = evaluate_plan(plan, land, planting, economics, scenarios, 0.50)
    save_plan(tables / "result3_main.csv", plan, land, crops)
    evaluation.to_csv(tables / "main_correlated_scenario_annual_metrics.csv", index=False, encoding="utf-8-sig")
    sensitivity = {}
    for strength in (0.5, 1.0, 1.5):
        strength_scenarios, strength_metadata = generate_scenarios(
            crops, SCENARIO_COUNT, SEED, correlated=True, relationship_strength=strength
        )
        strength_eval = evaluate_plan(plan, land, planting, economics, strength_scenarios, 0.50)
        strength_eval.to_csv(
            tables / f"relationship_strength_{strength:.1f}_scenario_annual_metrics.csv",
            index=False,
            encoding="utf-8-sig",
        )
        sensitivity[f"strength_{strength:.1f}"] = {
            **profit_distribution(strength_eval),
            "metadata": strength_metadata,
        }
    metrics = {
        **profit_distribution(evaluation),
        **concentration_metrics(plan),
        "windows": windows,
        "scenario_metadata": metadata,
        "relationship_sensitivity": sensitivity,
        "risk_weight": 0.15,
        "execution_time_seconds": time.perf_counter() - started,
    }
    write_json(metrics_dir / "main_metrics.json", metrics)
    return plan, evaluation, scenarios, metadata, metrics


if __name__ == "__main__":
    run_main()
