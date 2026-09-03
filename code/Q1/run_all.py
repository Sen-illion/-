from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "code" / "common"))

from planting_optimizer import environment_record, load_inputs, validate_plan, write_json  # noqa: E402
from q1_baseline import run_baseline  # noqa: E402
from q1_main import run_main  # noqa: E402


OUTPUT = PROJECT_ROOT / "results" / "Q1" / "experiments" / "round1"


def main():
    started = time.perf_counter()
    case1_plan, case2_plan, main_metrics = run_main()
    baseline_plan, baseline_metrics = run_baseline()
    land, _, planting, _ = load_inputs()
    case1_errors = validate_plan(case1_plan, land, planting)
    case2_errors = validate_plan(case2_plan, land, planting)
    comparison_rows = []
    for case in ("Q1_case_1", "Q1_case_2"):
        comparison_rows.append({
            "case": case,
            "main_mean_profit_yuan": main_metrics[case]["mean_profit_yuan"],
            "baseline_mean_profit_yuan": baseline_metrics[case]["mean_profit_yuan"],
            "profit_improvement_yuan": main_metrics[case]["mean_profit_yuan"] - baseline_metrics[case]["mean_profit_yuan"],
            "main_excess_rate": main_metrics[case]["mean_excess_rate"],
            "baseline_excess_rate": baseline_metrics[case]["mean_excess_rate"],
            "main_top5_area_mass": main_metrics[case]["top5_area_mass"],
            "baseline_top5_area_mass": baseline_metrics[case]["top5_area_mass"],
        })
    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(OUTPUT / "tables" / "comparison.csv", index=False, encoding="utf-8-sig")
    max_gap = max(
        metric.get("mip_gap") or 0.0
        for case in ("Q1_case_1", "Q1_case_2")
        for metric in main_metrics[case]["windows"]
    )
    summary = {
        "schema_version": 1,
        "question": "Q1",
        "round": "round1",
        "implementation_target": "python",
        "random_seed": 20240902,
        "approved_decision_id": "q1_method_choice",
        "methods": [
            {
                "method_id": "Q1-M1",
                "role": "main_candidate",
                "script": "code/Q1/run_all.py",
                "status": "success" if not case1_errors and not case2_errors else "failed_validation",
                "execution_time_seconds": main_metrics["execution_time_seconds"],
                "input_files": ["workspace/data_clean/land.csv", "workspace/data_clean/crops.csv", "workspace/data_clean/planting_2023.csv", "workspace/data_clean/economics_2023.csv"],
                "output_files": ["results/Q1/experiments/round1/tables/result1_1_main.csv", "results/Q1/experiments/round1/tables/result1_2_main.csv"],
                "figure_files": [],
                "metrics_summary": {"case1": main_metrics["Q1_case_1"], "case2": main_metrics["Q1_case_2"], "constraint_errors": len(case1_errors) + len(case2_errors)},
                "warnings": ["智慧大棚第一季暂复用第二季经济参数"],
                "errors": case1_errors + case2_errors,
            },
            {
                "method_id": "Q1-B1",
                "role": "usable_baseline",
                "script": "code/Q1/q1_baseline.py",
                "status": "success" if baseline_metrics["constraint_error_count"] == 0 else "failed_validation",
                "execution_time_seconds": baseline_metrics["execution_time_seconds"],
                "input_files": ["workspace/data_clean/land.csv", "workspace/data_clean/planting_2023.csv", "workspace/data_clean/economics_2023.csv"],
                "output_files": ["results/Q1/experiments/round1/tables/result1_baseline.csv"],
                "figure_files": [],
                "metrics_summary": baseline_metrics,
                "warnings": ["基线按利润排序，预期会高度集中，仅作比较"],
                "errors": baseline_metrics["constraint_errors"],
            },
        ],
        "comparison": comparison_rows,
        "fallback_trigger": {
            "fallback_id": "Q1-F1",
            "condition": "任一滚动窗口MIP gap超过5%",
            "observed": max_gap > 0.05,
            "evidence": {"maximum_mip_gap": max_gap},
        },
        "environment": environment_record(),
        "total_execution_time_seconds": time.perf_counter() - started,
    }
    write_json(OUTPUT / "run_summary.json", summary)
    print(json.dumps({"status": [method["status"] for method in summary["methods"]], "maximum_mip_gap": max_gap, "comparison": comparison_rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
