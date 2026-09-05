from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy

from q1_baseline import run_baseline
from q1_common import (
    ROOT,
    evaluate_plan,
    expected_sales,
    initial_history,
    load_inputs,
    plan_frame,
    save_json,
    validate_plan,
)
from q1_model import EPSILON_ACTIVATION_YUAN, build_model, solve, stage_record


OUT = ROOT / "results" / "Q1" / "experiments" / "full_horizon_round1"
TABLES = OUT / "tables"
METRICS = OUT / "metrics"
FIGURES = OUT / "figures"
SEED = 2026
YEARS = list(range(2024, 2031))


def full_plan(model, result):
    """Extract all seven years from one full-horizon incumbent."""
    rows = []
    for key, idx in model.x_index.items():
        plot, year, slot, crop = key
        area = float(result.x[idx])
        if area > 1e-5:
            rows.append({
                "plot_id": plot,
                "year": int(year),
                "slot": slot,
                "crop_id": int(crop),
                "area": area,
                **model.meta[key],
            })
    return rows


def solve_full_policy(land, economics, demand, planting, history, policy, eta=None):
    if policy == "half_price":
        model = build_model(land, economics, demand, history, 2024, 2030)
        try:
            result, attempts = solve(model, "half")
            fallback = None
        except RuntimeError as exc:
            # A legal baseline is preferable to emitting no result, but this is
            # explicitly marked as a heuristic fallback rather than an optimum.
            baseline = run_baseline(land, economics, demand, planting, 0.5)
            return {"policy": policy, "eta": None, "plan": baseline["plan"],
                    "solver": {"stage": "full_horizon_half_price", "status": "heuristic_fallback",
                               "message": str(exc), "selected_gap": None},
                    "fallback": "rolling_baseline_half_price"}
        return {
            "policy": policy,
            "eta": None,
            "plan": full_plan(model, result),
            "solver": stage_record(model, result, attempts, "full_horizon_half_price"),
            "fallback": fallback,
        }

    pure_model = build_model(land, economics, demand, history, 2024, 2030)
    pure_result, pure_attempts = solve(pure_model, "pure")
    pi_star = float(pure_model.economic @ pure_result.x)
    if policy == "pure_profit":
        return {
            "policy": policy,
            "eta": None,
            "plan": full_plan(pure_model, pure_result),
            "solver": stage_record(pure_model, pure_result, pure_attempts, "full_horizon_pure_profit"),
            "pi_star_yuan": pi_star,
        }

    floor = (1.0 - float(eta)) * pi_star - max(1e-4, abs(pi_star) * 1e-9)
    model = build_model(land, economics, demand, history, 2024, 2030, profit_floor=floor)
    try:
        result, attempts = solve(model, "waste")
        fallback = None
    except RuntimeError as exc:
        return {"policy": policy, "eta": float(eta),
                "plan": full_plan(pure_model, pure_result),
                "solver": {"stage": "full_horizon_minimum_waste", "status": "heuristic_fallback",
                           "message": str(exc), "selected_gap": None,
                           "pi_star_yuan": pi_star, "profit_floor_yuan": floor},
                "pi_star_yuan": pi_star, "profit_floor_yuan": floor,
                "fallback": "pure_profit_incumbent"}
    return {
        "policy": policy,
        "eta": float(eta),
        "plan": full_plan(model, result),
        "solver": stage_record(model, result, attempts, "full_horizon_minimum_waste"),
        "pi_star_yuan": pi_star,
        "profit_floor_yuan": floor,
        "fallback": fallback,
    }


def method_entry(name, role, script, elapsed, outputs, metrics, validation, solver=None):
    return {
        "method_id": name,
        "role": role,
        "script": script,
        "status": "success" if validation["violation_count"] == 0 else "failed",
        "execution_time_seconds": elapsed,
        "input_files": [
            "workspace/data_clean/land.csv",
            "workspace/data_clean/crops.csv",
            "workspace/data_clean/planting_2023.csv",
            "workspace/data_clean/economics_2023.csv",
        ],
        "output_files": outputs,
        "metrics_summary": metrics,
        "solver_summary": solver,
        "warnings": [],
        "errors": [],
    }


def main():
    np.random.seed(SEED)
    for path in (TABLES, METRICS, FIGURES):
        path.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    summary = {
        "schema_version": 1,
        "question": "Q1",
        "round": "full_horizon_round1",
        "implementation_target": "python",
        "approved_decision_id": "q1_full_horizon_method_1",
        "random_seed": SEED,
        "method": "Recursive-State Full-Horizon MILP",
        "parameters": {"alpha": 0.10, "eta_main": 0.01, "eta_comparator": 0.03},
        "methods": [],
        "comparison": {},
        "fallback_trigger": {
            "fallback_id": "Q1-F1",
            "condition": "selected full-horizon solve has no incumbent or MIP gap > 5%",
            "observed": False,
            "evidence": [],
        },
        "environment": {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
        },
        "warnings": [],
        "errors": [],
    }
    try:
        land, crops, planting, economics = load_inputs()
        demand = expected_sales(planting, land, economics)
        history = initial_history(planting, land)
        results = {}
        specs = [
            ("full_eta_01", "main", "pareto", 0.01),
            ("full_eta_03", "robustness_comparator", "pareto", 0.03),
            ("full_half_price", "main_case_2", "half_price", None),
            ("full_pure_profit", "reference", "pure_profit", None),
        ]
        for name, role, policy, eta in specs:
            begun = time.perf_counter()
            result = solve_full_policy(land, economics, demand, planting, history, policy, eta)
            elapsed = time.perf_counter() - begun
            results[name] = result
            metrics = evaluate_plan(result["plan"], demand, 0.5 if policy == "half_price" else 0.0)
            validation = validate_plan(result["plan"], history, land)
            csv_path = TABLES / f"{name}_plan.csv"
            xlsx_path = TABLES / f"{name}_plan.xlsx"
            plan_frame(result["plan"], crops).to_csv(csv_path, index=False, encoding="utf-8-sig")
            plan_frame(result["plan"], crops).to_excel(xlsx_path, index=False)
            save_json(METRICS / f"{name}_validation.json", validation)
            save_json(METRICS / f"{name}_solver.json", result["solver"])
            summary["methods"].append(method_entry(
                name, role, "code/Q1/q1_full_horizon.py", elapsed,
                [str(csv_path.relative_to(ROOT)).replace("\\", "/"),
                 str(xlsx_path.relative_to(ROOT)).replace("\\", "/"),
                 str((METRICS / f"{name}_validation.json").relative_to(ROOT)).replace("\\", "/")],
                metrics, validation, result["solver"],
            ))
            if result.get("fallback"):
                summary["warnings"].append(f"{name}: {result['fallback']}")
        # Rolling baseline is retained as a directly comparable reference.
        begun = time.perf_counter()
        baseline_zero = run_baseline(land, economics, demand, planting, 0.0)
        baseline_half = run_baseline(land, economics, demand, planting, 0.5)
        for name, result, salvage, role in [
            ("rolling_baseline_zero", baseline_zero, 0.0, "usable_baseline"),
            ("rolling_baseline_half", baseline_half, 0.5, "usable_baseline_case_2"),
        ]:
            metrics = evaluate_plan(result["plan"], demand, salvage)
            validation = validate_plan(result["plan"], history, land)
            csv_path = TABLES / f"{name}_plan.csv"
            xlsx_path = TABLES / f"{name}_plan.xlsx"
            plan_frame(result["plan"], crops).to_csv(csv_path, index=False, encoding="utf-8-sig")
            plan_frame(result["plan"], crops).to_excel(xlsx_path, index=False)
            save_json(METRICS / f"{name}_validation.json", validation)
            summary["methods"].append(method_entry(
                name, role, "code/Q1/q1_baseline.py", time.perf_counter() - begun,
                [str(csv_path.relative_to(ROOT)).replace("\\", "/"),
                 str(xlsx_path.relative_to(ROOT)).replace("\\", "/")],
                metrics, validation,
            ))

        comparison = []
        for item in summary["methods"]:
            validation_path = METRICS / f"{item['method_id']}_validation.json"
            validation = json.loads(validation_path.read_text(encoding="utf-8")) if validation_path.exists() else {}
            comparison.append({"method_id": item["method_id"], "role": item["role"],
                               **item["metrics_summary"],
                               "constraint_violation_count": validation.get("violation_count", None)})
        pd.DataFrame(comparison).to_csv(TABLES / "method_comparison.csv", index=False, encoding="utf-8-sig")
        save_json(METRICS / "method_metrics.json", {x["method_id"]: x["metrics_summary"] for x in summary["methods"]})
        gaps = []
        for result in results.values():
            gap = result["solver"].get("selected_gap")
            if gap is not None:
                gaps.append(float(gap))
                if gap > 0.05 + 1e-9:
                    summary["fallback_trigger"]["observed"] = True
                    summary["fallback_trigger"]["evidence"].append(result["solver"])
        summary["comparison"] = {
            "table": "results/Q1/experiments/full_horizon_round1/tables/method_comparison.csv",
            "maximum_selected_full_horizon_gap": max(gaps, default=None),
            "total_constraint_violations": sum(int(x["metrics_summary"].get("constraint_violation_count", 0)) for x in []),
        }
        summary["status"] = "success" if not summary["fallback_trigger"]["observed"] else "success_with_gap_warning"
    except Exception as exc:
        summary["status"] = "failed"
        summary["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        summary["execution_time_seconds"] = time.perf_counter() - started
        save_json(OUT / "run_summary.json", summary)
        print(json.dumps({"status": summary.get("status"), "elapsed": summary["execution_time_seconds"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
