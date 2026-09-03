from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FROZEN_AT = "2026-09-03T01:16:00+08:00"


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def decisions(question):
    path = ROOT / "methods" / question / f"{question.lower()}_decisions.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def entry(claim_id, value, unit, source_file, locator, decision_id):
    return {
        "claim_id": claim_id,
        "value": float(value),
        "unit": unit,
        "source_file": source_file,
        "source_locator": locator,
        "frozen_at": FROZEN_AT,
        "frozen_by_skill": "solution-package-builder",
        "decision_id": decision_id,
    }


def freeze_q1():
    source = "results/Q1/experiments/round1/run_summary.json"
    robust_source = "robustness/Q1/q1_robustness_summary.json"
    run, robust = load(source), load(robust_source)
    c1 = run["methods"][0]["metrics_summary"]["case1"]
    c2 = run["methods"][0]["metrics_summary"]["case2"]
    b1 = run["methods"][1]["metrics_summary"]["Q1_case_1"]
    b2 = run["methods"][1]["metrics_summary"]["Q1_case_2"]
    rows = [
        entry("Q1-C1", c1["mean_profit_yuan"], "yuan/year", source, "$.methods[0].metrics_summary.case1.mean_profit_yuan", "q1_package_signoff"),
        entry("Q1-C2", c1["mean_excess_rate"], "proportion", source, "$.methods[0].metrics_summary.case1.mean_excess_rate", "q1_package_signoff"),
        entry("Q1-C3", c2["mean_profit_yuan"], "yuan/year", source, "$.methods[0].metrics_summary.case2.mean_profit_yuan", "q1_package_signoff"),
        entry("Q1-C4", run["fallback_trigger"]["evidence"]["maximum_mip_gap"], "proportion", source, "$.fallback_trigger.evidence.maximum_mip_gap", "q1_package_signoff"),
        entry("Q1-case1-baseline-profit", b1["mean_profit_yuan"], "yuan/year", source, "$.methods[1].metrics_summary.Q1_case_1.mean_profit_yuan", "q1_package_signoff"),
        entry("Q1-case1-baseline-excess", b1["mean_excess_rate"], "proportion", source, "$.methods[1].metrics_summary.Q1_case_1.mean_excess_rate", "q1_package_signoff"),
        entry("Q1-case1-main-top5", c1["top5_area_mass"], "proportion", source, "$.methods[0].metrics_summary.case1.top5_area_mass", "q1_package_signoff"),
        entry("Q1-case1-baseline-top5", b1["top5_area_mass"], "proportion", source, "$.methods[1].metrics_summary.Q1_case_1.top5_area_mass", "q1_package_signoff"),
        entry("Q1-case2-baseline-profit", b2["mean_profit_yuan"], "yuan/year", source, "$.methods[1].metrics_summary.Q1_case_2.mean_profit_yuan", "q1_package_signoff"),
        entry("Q1-case2-main-excess", c2["mean_excess_rate"], "proportion", source, "$.methods[0].metrics_summary.case2.mean_excess_rate", "q1_package_signoff"),
        entry("Q1-case2-baseline-excess", b2["mean_excess_rate"], "proportion", source, "$.methods[1].metrics_summary.Q1_case_2.mean_excess_rate", "q1_package_signoff"),
    ]
    for idx, observation in enumerate(robust["observations"]):
        if observation["plan"] in {"case1_main", "baseline"}:
            rows.append(entry(
                f"Q1-robust-{observation['plan']}-{observation['demand_scale']}",
                observation["mean_excess_rate"], "proportion", robust_source,
                f"$.observations[{idx}].mean_excess_rate", "q1_package_signoff"
            ))
    return rows


def freeze_q2():
    source = "results/Q2/experiments/round1/run_summary.json"
    robust_source = "robustness/Q2/q2_robustness_summary.json"
    run, robust = load(source), load(robust_source)
    comp = run["comparison"]
    main = run["methods"][0]["metrics_summary"]
    values = [
        ("Q2-C1", comp["main_mean_profit_yuan"], "yuan/year", "$.comparison.main_mean_profit_yuan"),
        ("Q2-C2", comp["baseline_mean_profit_yuan"], "yuan/year", "$.comparison.baseline_mean_profit_yuan"),
        ("Q2-C3", comp["main_lower_10pct_mean_profit_yuan"], "yuan/year", "$.comparison.main_lower_10pct_mean_profit_yuan"),
        ("Q2-C4", comp["main_mean_excess_rate"], "proportion", "$.comparison.main_mean_excess_rate"),
        ("Q2-baseline-lower10", comp["baseline_lower_10pct_mean_profit_yuan"], "yuan/year", "$.comparison.baseline_lower_10pct_mean_profit_yuan"),
        ("Q2-main-p05", comp["main_p05_profit_yuan"], "yuan/year", "$.comparison.main_p05_profit_yuan"),
        ("Q2-baseline-p05", comp["baseline_p05_profit_yuan"], "yuan/year", "$.comparison.baseline_p05_profit_yuan"),
        ("Q2-baseline-excess", comp["baseline_mean_excess_rate"], "proportion", "$.comparison.baseline_mean_excess_rate"),
        ("Q2-plan-overlap", comp["plan_area_overlap"], "proportion", "$.comparison.plan_area_overlap"),
        ("Q2-main-std", main["std_profit_yuan"], "yuan/year", "$.methods[0].metrics_summary.std_profit_yuan"),
        ("Q2-C5", max(w["mip_gap"] for w in main["windows"]), "proportion", "$.methods[0].metrics_summary.windows[*].mip_gap|max"),
    ]
    rows = [entry(cid, val, unit, source, loc, "q2_package_signoff") for cid, val, unit, loc in values]
    mean_diffs = [r["mean_difference_yuan"] for r in robust["observations"]]
    tail_diffs = [r["lower_tail_difference_yuan"] for r in robust["observations"]]
    rows += [
        entry("Q2-robust-mean-diff-min", min(mean_diffs), "yuan/year", robust_source, "$.observations[*].mean_difference_yuan|min", "q2_package_signoff"),
        entry("Q2-robust-mean-diff-max", max(mean_diffs), "yuan/year", robust_source, "$.observations[*].mean_difference_yuan|max", "q2_package_signoff"),
        entry("Q2-robust-tail-diff-min", min(tail_diffs), "yuan/year", robust_source, "$.observations[*].lower_tail_difference_yuan|min", "q2_package_signoff"),
        entry("Q2-robust-tail-diff-max", max(tail_diffs), "yuan/year", robust_source, "$.observations[*].lower_tail_difference_yuan|max", "q2_package_signoff"),
    ]
    for idx, observation in enumerate(robust["observations"]):
        rows += [
            entry(f"Q2-seed-{observation['seed']}-mean-diff", observation["mean_difference_yuan"], "yuan/year", robust_source, f"$.observations[{idx}].mean_difference_yuan", "q2_package_signoff"),
            entry(f"Q2-seed-{observation['seed']}-tail-diff", observation["lower_tail_difference_yuan"], "yuan/year", robust_source, f"$.observations[{idx}].lower_tail_difference_yuan", "q2_package_signoff"),
        ]
    return rows


def freeze_q3():
    source = "results/Q3/experiments/round1/run_summary.json"
    robust_source = "robustness/Q3/q3_robustness_summary.json"
    run, robust = load(source), load(robust_source)
    comp = run["comparison"]
    main = run["methods"][0]["metrics_summary"]
    values = [
        ("Q3-C1", comp["q3_main_mean_profit_yuan"], "yuan/year", "$.comparison.q3_main_mean_profit_yuan"),
        ("Q3-C2", comp["q2_plan_mean_profit_under_q3_scenarios_yuan"], "yuan/year", "$.comparison.q2_plan_mean_profit_under_q3_scenarios_yuan"),
        ("Q3-C3", comp["mean_profit_change_yuan"], "yuan/year", "$.comparison.mean_profit_change_yuan"),
        ("Q3-C4", comp["q3_main_lower_10pct_mean_profit_yuan"], "yuan/year", "$.comparison.q3_main_lower_10pct_mean_profit_yuan"),
        ("Q3-C5", comp["plan_area_overlap"], "proportion", "$.comparison.plan_area_overlap"),
        ("Q3-q2-lower10", comp["q2_plan_lower_10pct_mean_profit_yuan"], "yuan/year", "$.comparison.q2_plan_lower_10pct_mean_profit_yuan"),
        ("Q3-lower-tail-change", comp["lower_tail_change_yuan"], "yuan/year", "$.comparison.lower_tail_change_yuan"),
        ("Q3-main-excess", comp["q3_main_mean_excess_rate"], "proportion", "$.comparison.q3_main_mean_excess_rate"),
        ("Q3-q2-excess", comp["q2_plan_mean_excess_rate"], "proportion", "$.comparison.q2_plan_mean_excess_rate"),
        ("Q3-max-gap", max(w["mip_gap"] for w in main["windows"]), "proportion", "$.methods[0].metrics_summary.windows[*].mip_gap|max"),
    ]
    rows = [entry(cid, val, unit, source, loc, "q3_package_signoff") for cid, val, unit, loc in values]
    for strength in ("0.5", "1.0", "1.5"):
        rows.append(entry(
            f"Q3-strength-{strength}-mean", main["relationship_sensitivity"][f"strength_{strength}"]["mean_profit_yuan"],
            "yuan/year", source, f"$.methods[0].metrics_summary.relationship_sensitivity.strength_{strength}.mean_profit_yuan", "q3_package_signoff"
        ))
    diffs = [r["mean_difference_yuan"] for r in robust["observations"]]
    relative_range = next(c["observed_value"] for c in robust["checks"] if "not dominated" in c["tested_claim"])
    rows += [
        entry("Q3-robust-diff-min", min(diffs), "yuan/year", robust_source, "$.observations[*].mean_difference_yuan|min", "q3_package_signoff"),
        entry("Q3-robust-diff-max", max(diffs), "yuan/year", robust_source, "$.observations[*].mean_difference_yuan|max", "q3_package_signoff"),
        entry("Q3-robust-relative-range", relative_range, "proportion", robust_source, "$.checks[1].observed_value", "q3_package_signoff"),
    ]
    for idx, observation in enumerate(robust["observations"]):
        rows.append(entry(
            f"Q3-strength-{observation['strength']}-seed-{observation['seed']}-mean-diff",
            observation["mean_difference_yuan"], "yuan/year", robust_source,
            f"$.observations[{idx}].mean_difference_yuan", "q3_package_signoff"
        ))
    return rows


if __name__ == "__main__":
    builders = {"Q1": freeze_q1, "Q2": freeze_q2, "Q3": freeze_q3}
    for question, builder in builders.items():
        required = f"{question.lower()}_package_signoff"
        if required not in {row["decision_id"] for row in decisions(question)}:
            raise RuntimeError(f"missing {required}")
        payload = {
            "schema_version": 1,
            "question": question,
            "frozen_at": FROZEN_AT,
            "package_signoff_decision": required,
            "claims": builder(),
        }
        target = ROOT / "results" / question / "reports" / "frozen_numbers.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{question}: {len(payload['claims'])} claims -> {target.relative_to(ROOT)}")
