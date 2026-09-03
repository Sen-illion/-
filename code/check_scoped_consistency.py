from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def read_jsonl(relative):
    return [json.loads(line) for line in (ROOT / relative).read_text(encoding="utf-8").splitlines() if line.strip()]


def audit(question):
    q = question.lower()
    manifest = read_json(f"planning/manifests/{question}.json")
    run = read_json(f"results/{question}/experiments/round1/run_summary.json")
    robustness = read_json(f"robustness/{question}/{q}_robustness_summary.json")
    decisions = read_jsonl(f"methods/{question}/{q}_decisions.jsonl")
    decision_ids = {item["decision_id"] for item in decisions}
    checks = []

    def add(name, passed, evidence):
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "evidence": evidence})

    add("manifest freeze state", manifest["status"] == "lean_results_judged_and_frozen" and manifest["allowed"]["freeze"], manifest["status"])
    add("result verdict exists", f"{q}_result_verdict_round1" in decision_ids, sorted(decision_ids))
    add("stability verdict exists", f"{q}_stability_verdict_round1" in decision_ids, sorted(decision_ids))
    refs = [manifest["artifacts"][key] for key in ("latest_run", "code_review", "robustness_summary")]
    add("canonical references exist", all((ROOT / ref).exists() for ref in refs), refs)
    review = read_json(manifest["artifacts"]["code_review"])
    add("hard-constraint review passed", review["verdict"] == "PASSED" and review["checks"]["output_contract"]["status"] == "PASS", manifest["artifacts"]["code_review"])

    if question == "Q1":
        nominal = run["methods"][0]["metrics_summary"]["case1"]["mean_excess_rate"]
        robust_nominal = next(r["mean_excess_rate"] for r in robustness["observations"] if r["plan"] == "case1_main" and r["demand_scale"] == 1.0)
        add("nominal Q1 excess rate agrees", abs(nominal - robust_nominal) < 1e-12, {"run": nominal, "robustness": robust_nominal})
        add("Q1 limitation retained", robustness["overall_status"] == "FAIL" and len(manifest.get("claim_limitations", [])) >= 2, manifest.get("claim_limitations", []))
    elif question == "Q2":
        add("Q2 robustness direction agrees", robustness["overall_status"] == "PASS" and all(r["mean_difference_yuan"] > 0 and r["lower_tail_difference_yuan"] > 0 for r in robustness["observations"]), "all five seeds positive")
        add("Q2 main value resolves", run["comparison"]["main_mean_profit_yuan"] == run["methods"][0]["metrics_summary"]["mean_profit_yuan"], run["comparison"]["main_mean_profit_yuan"])
    else:
        add("Q3 non-superiority agrees", run["comparison"]["mean_profit_change_yuan"] < 0 and all(r["mean_difference_yuan"] <= 0 for r in robustness["observations"]), run["comparison"]["mean_profit_change_yuan"])
        add("Q3 limitation retained", len(manifest.get("claim_limitations", [])) >= 3, manifest.get("claim_limitations", []))

    verdict = "PASSED" if all(item["status"] == "PASS" for item in checks) else "FAILED"
    result = {
        "schema_version": 1,
        "mode": "scoped",
        "impact_class": "FROZEN",
        "question": question,
        "verdict": verdict,
        "scope": "run summary, robustness summary, human result/stability decisions, manifest freeze state",
        "checks": checks,
    }
    target = ROOT / "results" / question / "reports" / "scoped_consistency.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return verdict, target


if __name__ == "__main__":
    for item in ("Q1", "Q2", "Q3"):
        verdict, target = audit(item)
        print(f"{item}: {verdict} -> {target.relative_to(ROOT)}")
