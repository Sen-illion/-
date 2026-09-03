from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "code" / "common"))

from planting_optimizer import environment_record, load_inputs, plan_overlap, validate_plan, write_json  # noqa: E402
from q3_baseline import run_baseline  # noqa: E402
from q3_main import run_main  # noqa: E402


OUTPUT = PROJECT_ROOT / "results" / "Q3" / "experiments" / "round1"


def main():
    started = time.perf_counter()
    main_plan, _, _, metadata, main_metrics = run_main()
    baseline_plan, _, _, _, baseline_metrics = run_baseline()
    land, _, planting, _ = load_inputs()
    main_errors = validate_plan(main_plan, land, planting)
    baseline_errors = validate_plan(baseline_plan, land, planting)
    sensitivity = main_metrics["relationship_sensitivity"]
    lower_tail_values = [sensitivity[key]["lower_10pct_mean_profit_yuan"] for key in sorted(sensitivity)]
    direction_stable = all(value >= baseline_metrics["lower_10pct_mean_profit_yuan"] for value in lower_tail_values) or all(
        value <= baseline_metrics["lower_10pct_mean_profit_yuan"] for value in lower_tail_values
    )
    comparison = {
        "q3_main_mean_profit_yuan": main_metrics["mean_profit_yuan"],
        "q2_plan_mean_profit_under_q3_scenarios_yuan": baseline_metrics["mean_profit_yuan"],
        "mean_profit_change_yuan": main_metrics["mean_profit_yuan"] - baseline_metrics["mean_profit_yuan"],
        "q3_main_lower_10pct_mean_profit_yuan": main_metrics["lower_10pct_mean_profit_yuan"],
        "q2_plan_lower_10pct_mean_profit_yuan": baseline_metrics["lower_10pct_mean_profit_yuan"],
        "lower_tail_change_yuan": main_metrics["lower_10pct_mean_profit_yuan"] - baseline_metrics["lower_10pct_mean_profit_yuan"],
        "q3_main_mean_excess_rate": main_metrics["mean_excess_rate"],
        "q2_plan_mean_excess_rate": baseline_metrics["mean_excess_rate"],
        "plan_area_overlap": plan_overlap(main_plan, baseline_plan),
        "relationship_strength_direction_stable": direction_stable,
    }
    pd.DataFrame([comparison]).to_csv(OUTPUT / "tables" / "comparison_q2_q3.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([
        {"strength": key, **{k: v for k, v in value.items() if k != "metadata"}}
        for key, value in sensitivity.items()
    ]).to_csv(OUTPUT / "tables" / "relationship_sensitivity_summary.csv", index=False, encoding="utf-8-sig")
    max_gap = max(metric.get("mip_gap") or 0.0 for metric in main_metrics["windows"])
    fallback_observed = max_gap > 0.05 or comparison["plan_area_overlap"] < 0.70 or not direction_stable
    summary = {
        "schema_version": 1,
        "question": "Q3",
        "round": "round1",
        "implementation_target": "python",
        "random_seed": 20240902,
        "approved_decision_id": "q3_method_choice",
        "methods": [
            {
                "method_id": "Q3-M1",
                "role": "main_candidate",
                "script": "code/Q3/run_all.py",
                "status": "success" if not main_errors else "failed_validation",
                "execution_time_seconds": main_metrics["execution_time_seconds"],
                "input_files": ["workspace/data_clean/land.csv", "workspace/data_clean/crops.csv", "workspace/data_clean/planting_2023.csv", "workspace/data_clean/economics_2023.csv"],
                "output_files": ["results/Q3/experiments/round1/tables/result3_main.csv", "results/Q3/experiments/round1/tables/relationship_sensitivity_summary.csv"],
                "figure_files": [],
                "metrics_summary": main_metrics,
                "warnings": ["替代、互补和相关关系均为模拟设定，不是附件数据估计"],
                "errors": main_errors,
            },
            {
                "method_id": "Q3-B1",
                "role": "usable_baseline",
                "script": "code/Q3/q3_baseline.py",
                "status": "success" if not baseline_errors else "failed_validation",
                "execution_time_seconds": 0.0,
                "input_files": ["results/Q2/experiments/round1/tables/result2_main.csv"],
                "output_files": ["results/Q3/experiments/round1/tables/result3_baseline_q2_plan.csv"],
                "figure_files": [],
                "metrics_summary": baseline_metrics,
                "warnings": [],
                "errors": baseline_errors,
            },
        ],
        "comparison": comparison,
        "scenario_metadata": metadata,
        "fallback_trigger": {
            "fallback_id": "Q3-F1",
            "condition": "窗口gap>5%、与Q2重合度<70%或强度敏感性方向反转",
            "observed": fallback_observed,
            "evidence": {"maximum_mip_gap": max_gap, "plan_area_overlap": comparison["plan_area_overlap"], "direction_stable": direction_stable},
        },
        "environment": environment_record(),
        "total_execution_time_seconds": time.perf_counter() - started,
    }
    write_json(OUTPUT / "run_summary.json", summary)
    print(json.dumps({"status": [method["status"] for method in summary["methods"]], "maximum_mip_gap": max_gap, "comparison": comparison, "fallback_observed": fallback_observed}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
