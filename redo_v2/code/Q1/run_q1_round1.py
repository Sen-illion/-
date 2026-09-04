from __future__ import annotations

import platform
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import scipy

from q1_baseline import run_baseline
from q1_common import ROOT, evaluate_plan, initial_history, load_inputs, plan_frame, save_json, validate_plan, expected_sales
from q1_model import EPSILON_ACTIVATION_YUAN, run_policy


ROUND = ROOT / "results" / "Q1" / "experiments" / "round1"
TABLES = ROUND / "tables"
METRICS = ROUND / "metrics"
LOGS = ROUND / "logs"
SEED = 2026


def flatten_windows(name: str, windows: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for window in windows:
        for key in ("pure_profit", "pareto", "half_price"):
            if key not in window:
                continue
            stage = window[key]
            for attempt_number, attempt in enumerate(stage["attempts"], start=1):
                rows.append({"policy": name, "committed_year": window["committed_year"],
                             "window_start": stage["years"][0], "window_end": stage["years"][1],
                             "stage": stage["stage"], "attempt": attempt_number, **attempt})
    return rows


def method_entry(method_id: str, role: str, script: str, elapsed: float, outputs: list[str],
                 metrics: dict, warnings: list[str], validation: dict) -> dict:
    status = "success" if validation["violation_count"] == 0 else "failed"
    return {"method_id": method_id, "role": role, "script": script, "status": status,
            "execution_time_seconds": elapsed,
            "input_files": ["workspace/data_clean/land.csv", "workspace/data_clean/crops.csv",
                            "workspace/data_clean/planting_2023.csv", "workspace/data_clean/economics_2023.csv"],
            "output_files": outputs, "figure_files": [], "metrics_summary": metrics,
            "warnings": warnings, "errors": [] if status == "success" else validation["details"][:20]}


def main() -> None:
    np.random.seed(SEED)
    TABLES.mkdir(parents=True, exist_ok=True); METRICS.mkdir(parents=True, exist_ok=True)
    started_all = time.perf_counter()
    run_summary: dict = {"schema_version": 1, "question": "Q1", "round": "round1",
                         "implementation_target": "python", "random_seed": SEED,
                         "approved_decision_id": "q1_method_choice_1", "methods": [], "comparison": {},
                         "fallback_trigger": {"fallback_id": "Q1-F1", "condition": "any formal rolling window has no incumbent or gap > 5% after one 180-second retry", "observed": False, "evidence": None},
                         "environment": {"python": sys.version, "executable": sys.executable,
                                         "platform": platform.platform(), "numpy": np.__version__,
                                         "pandas": pd.__version__, "scipy": scipy.__version__},
                         "legacy_result_isolation": "No legacy plan or result file was read; all plans were rebuilt from cleaned attachments.",
                         "warnings": [], "errors": []}
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
        metrics_all: dict = {}; validation_all: dict = {}; solver_rows: list[dict] = []; window_details: dict = {}
        for name, role, runner, salvage in specs:
            begun = time.perf_counter(); result = runner(); elapsed = time.perf_counter() - begun
            plan = result["plan"]
            metrics = evaluate_plan(plan, demand, salvage)
            validation = validate_plan(plan, history, land)
            metrics_all[name] = metrics; validation_all[name] = validation
            path = TABLES / f"{name}_plan.csv"
            plan_frame(plan, crops).to_csv(path, index=False, encoding="utf-8-sig")
            outputs = [str(path.relative_to(ROOT)).replace("\\", "/")]
            warnings = list(result.get("warnings", []))
            if "windows" in result:
                solver_rows.extend(flatten_windows(name, result["windows"]))
                window_details[name] = result["windows"]
                outputs.append("results/Q1/experiments/round1/tables/window_solver_records.csv")
                outputs.append("results/Q1/experiments/round1/metrics/window_details.json")
            run_summary["methods"].append(method_entry(name, role,
                "code/Q1/q1_model.py" if name.startswith("m1_") else "code/Q1/q1_baseline.py",
                elapsed, outputs, metrics, warnings, validation))
            if warnings:
                run_summary["warnings"].extend([f"{name}: {value}" for value in warnings])
        pd.DataFrame(solver_rows).to_csv(TABLES / "window_solver_records.csv", index=False, encoding="utf-8-sig")
        save_json(METRICS / "method_metrics.json", metrics_all)
        save_json(METRICS / "constraint_validation.json", validation_all)
        save_json(METRICS / "window_details.json", window_details)
        zero_profit = float(metrics_all["m1_zero_price_profit"]["profit_yuan"])
        comparison_rows: list[dict] = []
        for name, metrics in metrics_all.items():
            reference = zero_profit if name != "m1_half_price" and name != "b1_half_price" else float(metrics_all["m1_half_price"]["profit_yuan"])
            comparison_rows.append({"policy": name, **metrics,
                                    "profit_loss_rate_vs_case_reference": (reference - float(metrics["profit_yuan"])) / max(abs(reference), 1.0),
                                    "constraint_violation_count": validation_all[name]["violation_count"]})
        pd.DataFrame(comparison_rows).to_csv(TABLES / "method_comparison.csv", index=False, encoding="utf-8-sig")
        gaps = [float(row["mip_gap"]) for row in solver_rows if row["mip_gap"] is not None]
        selected: dict[tuple[str, str, str], dict] = {}
        for row in solver_rows:
            key = (row["policy"], str(row["committed_year"]), row["stage"])
            if key not in selected or int(row["attempt"]) > int(selected[key]["attempt"]):
                selected[key] = row
        selected_gaps = [float(row["mip_gap"]) for row in selected.values() if row["mip_gap"] is not None]
        failed_gap_rows = [row for row in solver_rows if row["attempt"] == 2 and
                           (not row["has_incumbent"] or row["mip_gap"] is None or float(row["mip_gap"]) > 0.05 + 1e-9)]
        violations = sum(item["violation_count"] for item in validation_all.values())
        if failed_gap_rows:
            run_summary["fallback_trigger"] = {**run_summary["fallback_trigger"], "observed": True,
                                                "evidence": failed_gap_rows}
        epsilon_upper = EPSILON_ACTIVATION_YUAN * max(int(item["activation_count"]) for item in metrics_all.values())
        run_summary["comparison"] = {"metrics_file": "results/Q1/experiments/round1/tables/method_comparison.csv",
                                     "total_constraint_violations": violations,
                                     "maximum_gap_across_all_attempts": max(gaps, default=None),
                                     "maximum_selected_solver_gap": max(selected_gaps, default=None),
                                     "retried_stage_count": sum(int(row["attempt"]) == 2 for row in selected.values()),
                                     "activation_tie_break_upper_bound_yuan": epsilon_upper,
                                     "activation_tie_break_share_of_zero_price_profit": epsilon_upper / max(abs(zero_profit), 1.0)}
        if run_summary["warnings"]:
            LOGS.mkdir(parents=True, exist_ok=True)
            save_json(LOGS / "warnings.json", run_summary["warnings"])
        run_summary["status"] = "success" if violations == 0 else "failed"
    except Exception as exc:
        LOGS.mkdir(parents=True, exist_ok=True)
        error_text = traceback.format_exc()
        (LOGS / "failure.txt").write_text(error_text, encoding="utf-8")
        run_summary["status"] = "failed"
        run_summary["errors"].append({"type": type(exc).__name__, "message": str(exc),
                                      "log": "results/Q1/experiments/round1/logs/failure.txt"})
    run_summary["execution_time_seconds"] = time.perf_counter() - started_all
    save_json(ROUND / "run_summary.json", run_summary)
    print(f"status={run_summary['status']} elapsed={run_summary['execution_time_seconds']:.2f}s")
    if run_summary["status"] != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
