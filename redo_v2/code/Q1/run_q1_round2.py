from __future__ import annotations

import platform
import sys
import time
import traceback

import numpy as np
import pandas as pd
import scipy

from q1_baseline import run_baseline
from q1_common import ROOT, evaluate_plan, expected_sales, initial_history, load_inputs, plan_frame, save_json, validate_plan
from q1_model import EPSILON_ACTIVATION_YUAN, run_policy
from run_q1_round1 import flatten_windows, method_entry


ROUND = ROOT / "results" / "Q1" / "experiments" / "round2"
TABLES = ROUND / "tables"
METRICS = ROUND / "metrics"
LOGS = ROUND / "logs"
SEED = 2026


def main() -> None:
    np.random.seed(SEED)
    TABLES.mkdir(parents=True, exist_ok=True)
    METRICS.mkdir(parents=True, exist_ok=True)
    started_all = time.perf_counter()
    run_summary: dict = {
        "schema_version": 1,
        "question": "Q1",
        "round": "round2",
        "implementation_target": "python",
        "random_seed": SEED,
        "approved_decision_id": "q1_method_choice_1",
        "change_scope": "Strict adjacent planting-cycle rotation; whole-plot activation retained; no surplus-ratio constraint added.",
        "methods": [],
        "comparison": {},
        "fallback_trigger": {
            "fallback_id": "Q1-F1",
            "condition": "any formal rolling window has no incumbent or gap > 5% after one 180-second retry",
            "observed": False,
            "evidence": None,
        },
        "environment": {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
        },
        "legacy_result_isolation": "Round2 rebuilt every plan from cleaned attachments; round1 plans and metrics were not read.",
        "warnings": [],
        "errors": [],
    }
    try:
        land, crops, planting, economics = load_inputs()
        demand = expected_sales(planting, land, economics)
        history = initial_history(planting, land)
        specs = [
            ("m1_zero_price_profit", "main_reference", lambda: run_policy(land, economics, demand, history, "pure"), 0.0),
            ("m1_eta_01", "main", lambda: run_policy(land, economics, demand, history, "pareto", 0.01), 0.0),
            ("m1_eta_03", "robustness_comparator", lambda: run_policy(land, economics, demand, history, "pareto", 0.03), 0.0),
            ("m1_half_price", "main_case_2", lambda: run_policy(land, economics, demand, history, "half_price"), 0.5),
            ("b1_zero_price", "usable_baseline", lambda: run_baseline(land, economics, demand, planting, 0.0), 0.0),
            ("b1_half_price", "usable_baseline_case_2", lambda: run_baseline(land, economics, demand, planting, 0.5), 0.5),
        ]
        metrics_all: dict = {}
        validation_all: dict = {}
        solver_rows: list[dict] = []
        window_details: dict = {}
        for name, role, runner, salvage in specs:
            begun = time.perf_counter()
            result = runner()
            elapsed = time.perf_counter() - begun
            plan = result["plan"]
            metrics = evaluate_plan(plan, demand, salvage)
            validation = validate_plan(plan, history, land)
            metrics_all[name] = metrics
            validation_all[name] = validation
            path = TABLES / f"{name}_plan.csv"
            plan_frame(plan, crops).to_csv(path, index=False, encoding="utf-8-sig")
            outputs = [str(path.relative_to(ROOT)).replace("\\", "/")]
            warnings = list(result.get("warnings", []))
            if "windows" in result:
                solver_rows.extend(flatten_windows(name, result["windows"]))
                window_details[name] = result["windows"]
                outputs.extend([
                    "results/Q1/experiments/round2/tables/window_solver_records.csv",
                    "results/Q1/experiments/round2/metrics/window_details.json",
                ])
            run_summary["methods"].append(method_entry(
                name,
                role,
                "code/Q1/q1_model.py" if name.startswith("m1_") else "code/Q1/q1_baseline.py",
                elapsed,
                outputs,
                metrics,
                warnings,
                validation,
            ))
            run_summary["warnings"].extend(f"{name}: {value}" for value in warnings)
        pd.DataFrame(solver_rows).to_csv(TABLES / "window_solver_records.csv", index=False, encoding="utf-8-sig")
        save_json(METRICS / "method_metrics.json", metrics_all)
        save_json(METRICS / "constraint_validation.json", validation_all)
        save_json(METRICS / "window_details.json", window_details)
        zero_profit = float(metrics_all["m1_zero_price_profit"]["profit_yuan"])
        comparison_rows: list[dict] = []
        for name, metrics in metrics_all.items():
            reference = (float(metrics_all["m1_half_price"]["profit_yuan"])
                         if name in {"m1_half_price", "b1_half_price"} else zero_profit)
            comparison_rows.append({
                "policy": name,
                **metrics,
                "profit_loss_rate_vs_case_reference":
                    (reference - float(metrics["profit_yuan"])) / max(abs(reference), 1.0),
                "constraint_violation_count": validation_all[name]["violation_count"],
            })
        pd.DataFrame(comparison_rows).to_csv(TABLES / "method_comparison.csv", index=False, encoding="utf-8-sig")
        gaps = [float(row["mip_gap"]) for row in solver_rows if row["mip_gap"] is not None]
        selected: dict[tuple[str, str, str], dict] = {}
        for row in solver_rows:
            key = (row["policy"], str(row["committed_year"]), row["stage"])
            if key not in selected or int(row["attempt"]) > int(selected[key]["attempt"]):
                selected[key] = row
        selected_gaps = [float(row["mip_gap"]) for row in selected.values() if row["mip_gap"] is not None]
        failed_gap_rows = [
            row for row in selected.values()
            if not row["has_incumbent"] or row["mip_gap"] is None or float(row["mip_gap"]) > 0.05 + 1e-9
        ]
        violations = sum(item["violation_count"] for item in validation_all.values())
        if failed_gap_rows:
            run_summary["fallback_trigger"] = {
                **run_summary["fallback_trigger"], "observed": True, "evidence": failed_gap_rows
            }
        epsilon_upper = EPSILON_ACTIVATION_YUAN * max(int(item["activation_count"]) for item in metrics_all.values())
        run_summary["comparison"] = {
            "metrics_file": "results/Q1/experiments/round2/tables/method_comparison.csv",
            "total_constraint_violations": violations,
            "maximum_gap_across_all_attempts": max(gaps, default=None),
            "maximum_selected_solver_gap": max(selected_gaps, default=None),
            "retried_stage_count": sum(int(row["attempt"]) == 2 for row in selected.values()),
            "activation_tie_break_upper_bound_yuan": epsilon_upper,
            "activation_tie_break_share_of_zero_price_profit": epsilon_upper / max(abs(zero_profit), 1.0),
        }
        if run_summary["warnings"]:
            LOGS.mkdir(parents=True, exist_ok=True)
            save_json(LOGS / "warnings.json", run_summary["warnings"])
        run_summary["status"] = "success" if violations == 0 and not failed_gap_rows else "failed"
    except Exception as exc:
        LOGS.mkdir(parents=True, exist_ok=True)
        (LOGS / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        run_summary["status"] = "failed"
        run_summary["errors"].append({
            "type": type(exc).__name__, "message": str(exc),
            "log": "results/Q1/experiments/round2/logs/failure.txt",
        })
    run_summary["execution_time_seconds"] = time.perf_counter() - started_all
    save_json(ROUND / "run_summary.json", run_summary)
    print(f"status={run_summary['status']} elapsed={run_summary['execution_time_seconds']:.2f}s")
    if run_summary["status"] != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
