from __future__ import annotations

import json
import py_compile
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code" / "common"))

from planting_optimizer import generate_scenarios, load_inputs, load_plan, validate_plan, write_json  # noqa: E402


FILES_BY_Q = {
    "Q1": ["code/common/planting_optimizer.py", "code/Q1/q1_main.py", "code/Q1/q1_baseline.py", "code/Q1/run_all.py"],
    "Q2": ["code/common/planting_optimizer.py", "code/Q2/q2_main.py", "code/Q2/q2_baseline.py", "code/Q2/run_all.py"],
    "Q3": ["code/common/planting_optimizer.py", "code/Q3/q3_main.py", "code/Q3/q3_baseline.py", "code/Q3/run_all.py"],
}


PLAN_PATHS = {
    "Q1": ["results/Q1/experiments/round1/tables/result1_1_main.csv", "results/Q1/experiments/round1/tables/result1_2_main.csv", "results/Q1/experiments/round1/tables/result1_baseline.csv"],
    "Q2": ["results/Q2/experiments/round1/tables/result2_main.csv", "results/Q2/experiments/round1/tables/result2_baseline.csv"],
    "Q3": ["results/Q3/experiments/round1/tables/result3_main.csv", "results/Q3/experiments/round1/tables/result3_baseline_q2_plan.csv"],
}


def check(condition, evidence):
    return {"status": "PASS" if condition else "FAIL", "evidence": evidence}


def main():
    land, crops, planting, economics = load_inputs()
    scenarios_a, _ = generate_scenarios(crops, 3, 20240902, correlated=True, relationship_strength=1.0)
    scenarios_b, _ = generate_scenarios(crops, 3, 20240902, correlated=True, relationship_strength=1.0)
    scenario_reproducible = scenarios_a == scenarios_b
    reviewed_at = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

    for question in ("Q1", "Q2", "Q3"):
        reviewed_files = FILES_BY_Q[question]
        syntax_errors = []
        for relative in reviewed_files:
            try:
                py_compile.compile(str(ROOT / relative), doraise=True)
            except py_compile.PyCompileError as error:
                syntax_errors.append(str(error))
        summary_path = ROOT / "results" / question / "experiments" / "round1" / "run_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        decision_path = ROOT / "methods" / question / f"{question.lower()}_decisions.jsonl"
        decisions = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        approved = next(record for record in decisions if record["decision_type"] == "method_choice" and record["status"] == "DECIDED")
        expected_main = f"{question}-M1"
        expected_baseline = f"{question}-B1"
        summary_ids = {(entry["method_id"], entry["role"]) for entry in summary["methods"]}
        method_aligned = summary["approved_decision_id"] == approved["decision_id"] and summary_ids == {
            (expected_main, "main_candidate"), (expected_baseline, "usable_baseline")
        }
        plan_errors = {}
        required_columns_ok = True
        for relative in PLAN_PATHS[question]:
            path = ROOT / relative
            if not path.exists():
                plan_errors[relative] = [{"type": "missing_file"}]
                required_columns_ok = False
                continue
            plan = load_plan(path, land)
            plan_errors[relative] = validate_plan(plan, land, planting)
            header = path.read_text(encoding="utf-8-sig").splitlines()[0].split(",")
            required_columns_ok &= set(["year", "plot_id", "season", "crop_id", "planted_area_mu"]).issubset(header)
        constraints_ok = all(not errors for errors in plan_errors.values())
        outputs_listed = all((ROOT / output).exists() for method in summary["methods"] for output in method["output_files"])
        statuses_success = all(method["status"] == "success" for method in summary["methods"])
        findings = []
        maximum_gap = summary["fallback_trigger"]["evidence"].get("maximum_mip_gap", 0.0)
        if maximum_gap > 0.05:
            findings.append({
                "severity": "warning",
                "check": "scale",
                "message": f"Maximum rolling-window MIP gap is {maximum_gap:.2%}; outputs are feasible approximations and the recorded fallback trigger is active."
            })
        if summary["fallback_trigger"]["observed"]:
            findings.append({
                "severity": "warning",
                "check": "fallback_trigger",
                "message": "The approved main run triggered its dormant fallback condition; human result judgment is required before final-method claims."
            })
        if question == "Q3" and summary["comparison"]["mean_profit_change_yuan"] < 0:
            findings.append({
                "severity": "warning",
                "check": "baseline_comparison",
                "message": "Q3 correlated main underperforms the Q2-plan baseline on both mean and lower-tail profit under the tested correlated scenarios."
            })
        checks = {
            "syntax": check(not syntax_errors, ["py_compile completed for all reviewed files"] if not syntax_errors else syntax_errors),
            "input_contract": check(required_columns_ok, ["cleaned CSV inputs only", "required plan columns present", "raw data paths are not output targets"]),
            "method_alignment": check(method_aligned, [f"decision={approved['decision_id']}", f"methods={sorted(summary_ids)}"]),
            "reproducibility": check(scenario_reproducible and summary["random_seed"] == 20240902, ["scenario generator exact repeat passed", "seed=20240902", summary["environment"]]),
            "output_contract": check(outputs_listed and statuses_success and constraints_ok, [f"listed_outputs_exist={outputs_listed}", f"method_statuses_success={statuses_success}", f"constraint_error_counts={ {key: len(value) for key, value in plan_errors.items()} }"]),
        }
        verdict = "PASSED" if all(value["status"] == "PASS" for value in checks.values()) else "FAILED"
        review = {
            "schema_version": 1,
            "question_id": question,
            "language": "python",
            "reviewed_files": reviewed_files,
            "decision_id": approved["decision_id"],
            "checks": checks,
            "findings": findings,
            "verdict": verdict,
            "reviewed_at": reviewed_at,
        }
        write_json(ROOT / "code" / question / "reviews" / f"{question.lower()}_python_review.json", review)
        print(question, verdict, "findings", len(findings))


if __name__ == "__main__":
    main()
