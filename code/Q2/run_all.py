from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "code" / "common"))

from planting_optimizer import environment_record, load_inputs, plan_overlap, validate_plan, write_json  # noqa: E402
from q2_baseline import run_baseline  # noqa: E402
from q2_main import run_main  # noqa: E402


OUTPUT = PROJECT_ROOT / "results" / "Q2" / "experiments" / "round1"


def main():
    started = time.perf_counter()
    main_plan, _, _, metadata, main_metrics = run_main()
    baseline_plan, _, _, _, baseline_metrics = run_baseline()
    land, _, planting, _ = load_inputs()
    main_errors = validate_plan(main_plan, land, planting)
    baseline_errors = validate_plan(baseline_plan, land, planting)
    comparison = {
        "main_mean_profit_yuan": main_metrics["mean_profit_yuan"],
        "baseline_mean_profit_yuan": baseline_metrics["mean_profit_yuan"],
        "main_lower_10pct_mean_profit_yuan": main_metrics["lower_10pct_mean_profit_yuan"],
        "baseline_lower_10pct_mean_profit_yuan": baseline_metrics["lower_10pct_mean_profit_yuan"],
        "main_p05_profit_yuan": main_metrics["p05_profit_yuan"],
        "baseline_p05_profit_yuan": baseline_metrics["p05_profit_yuan"],
        "main_mean_excess_rate": main_metrics["mean_excess_rate"],
        "baseline_mean_excess_rate": baseline_metrics["mean_excess_rate"],
        "plan_area_overlap": plan_overlap(main_plan, baseline_plan),
    }
    pd.DataFrame([comparison]).to_csv(OUTPUT / "tables" / "comparison.csv", index=False, encoding="utf-8-sig")
    max_gap = max(metric.get("mip_gap") or 0.0 for metric in main_metrics["windows"] + baseline_metrics["windows"])
    summary = {
        "schema_version": 1,
        "question": "Q2",
        "round": "round1",
        "implementation_target": "python",
        "random_seed": 20240902,
        "approved_decision_id": "q2_method_choice",
        "methods": [
            {
                "method_id": "Q2-M1",
                "role": "main_candidate",
                "script": "code/Q2/run_all.py",
                "status": "success" if not main_errors else "failed_validation",
                "execution_time_seconds": main_metrics["execution_time_seconds"],
                "input_files": ["workspace/data_clean/land.csv", "workspace/data_clean/crops.csv", "workspace/data_clean/planting_2023.csv", "workspace/data_clean/economics_2023.csv"],
                "output_files": ["results/Q2/experiments/round1/tables/result2_main.csv", "results/Q2/experiments/round1/tables/main_scenario_annual_metrics.csv"],
                "figure_files": [],
                "metrics_summary": main_metrics,
                "warnings": ["30个情景用于轻量首轮", "智慧大棚第一季暂复用第二季经济参数"],
                "errors": main_errors,
            },
            {
                "method_id": "Q2-B1",
                "role": "usable_baseline",
                "script": "code/Q2/q2_baseline.py",
                "status": "success" if not baseline_errors else "failed_validation",
                "execution_time_seconds": baseline_metrics["execution_time_seconds"],
                "input_files": ["workspace/data_clean/land.csv", "workspace/data_clean/planting_2023.csv", "workspace/data_clean/economics_2023.csv"],
                "output_files": ["results/Q2/experiments/round1/tables/result2_baseline.csv"],
                "figure_files": [],
                "metrics_summary": baseline_metrics,
                "warnings": [],
                "errors": baseline_errors,
            },
        ],
        "comparison": comparison,
        "scenario_metadata": metadata,
        "fallback_trigger": {
            "fallback_id": "Q2-F1",
            "condition": "任一窗口MIP gap超过5%或分布敏感",
            "observed": max_gap > 0.05,
            "evidence": {"maximum_mip_gap": max_gap, "plan_area_overlap": comparison["plan_area_overlap"]},
        },
        "environment": environment_record(),
        "total_execution_time_seconds": time.perf_counter() - started,
    }
    write_json(OUTPUT / "run_summary.json", summary)
    print(json.dumps({"status": [method["status"] for method in summary["methods"]], "maximum_mip_gap": max_gap, "comparison": comparison}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
