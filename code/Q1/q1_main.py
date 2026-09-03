from __future__ import annotations

import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "code" / "common"))

from planting_optimizer import (  # noqa: E402
    concentration_metrics,
    evaluate_plan,
    load_inputs,
    profit_distribution,
    rolling_optimize,
    save_plan,
    unit_scenario,
    write_json,
)


OUTPUT = PROJECT_ROOT / "results" / "Q1" / "experiments" / "round1"


def run_main():
    land, crops, planting, economics = load_inputs()
    tables = OUTPUT / "tables"
    metrics_dir = OUTPUT / "metrics"
    tables.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    case1_plan, case1_windows = rolling_optimize(
        land, planting, economics, [unit_scenario()],
        surplus_fraction=0.0,
        waste_weight=0.50,
        risk_weight=0.0,
        time_limit=20,
        mip_gap=0.05,
    )
    case2_plan, case2_windows = rolling_optimize(
        land, planting, economics, [unit_scenario()],
        surplus_fraction=0.50,
        waste_weight=0.0,
        risk_weight=0.0,
        time_limit=20,
        mip_gap=0.05,
    )
    save_plan(tables / "result1_1_main.csv", case1_plan, land, crops)
    save_plan(tables / "result1_2_main.csv", case2_plan, land, crops)
    case1_eval = evaluate_plan(case1_plan, land, planting, economics, [unit_scenario()], 0.0)
    case2_eval = evaluate_plan(case2_plan, land, planting, economics, [unit_scenario()], 0.5)
    case1_eval.to_csv(tables / "result1_1_main_annual_metrics.csv", index=False, encoding="utf-8-sig")
    case2_eval.to_csv(tables / "result1_2_main_annual_metrics.csv", index=False, encoding="utf-8-sig")
    metrics = {
        "Q1_case_1": {**profit_distribution(case1_eval), **concentration_metrics(case1_plan), "windows": case1_windows},
        "Q1_case_2": {**profit_distribution(case2_eval), **concentration_metrics(case2_plan), "windows": case2_windows},
        "execution_time_seconds": time.perf_counter() - started,
    }
    write_json(metrics_dir / "main_metrics.json", metrics)
    return case1_plan, case2_plan, metrics


if __name__ == "__main__":
    run_main()
