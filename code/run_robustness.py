from __future__ import annotations

from pathlib import Path

from common.planting_optimizer import (
    ALL_YEARS,
    evaluate_plan,
    generate_scenarios,
    load_inputs,
    load_plan,
    profit_distribution,
    validate_plan,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
SEEDS = [20240903, 20240904, 20240905, 20240906, 20240907]


def fixed_demand_scenario(crop_ids, scale):
    return {
        ("demand", int(crop), year): float(scale)
        for crop in crop_ids
        for year in ALL_YEARS
    }


def q1_checks(land, crops, planting, economics):
    table_dir = ROOT / "results" / "Q1" / "experiments" / "round1" / "tables"
    plans = {
        "case1_main": load_plan(table_dir / "result1_1_main.csv", land),
        "case2_main": load_plan(table_dir / "result1_2_main.csv", land),
        "baseline": load_plan(table_dir / "result1_baseline.csv", land),
    }
    scales = [0.95, 1.00, 1.05]
    observations = []
    for scale in scales:
        scenario = fixed_demand_scenario(crops.crop_id.unique(), scale)
        for name, surplus in (("case1_main", 0.0), ("case2_main", 0.5), ("baseline", 0.0)):
            metrics = profit_distribution(
                evaluate_plan(plans[name], land, planting, economics, [scenario], surplus)
            )
            observations.append({"demand_scale": scale, "plan": name, **metrics})

    case1 = [row for row in observations if row["plan"] == "case1_main"]
    baseline = [row for row in observations if row["plan"] == "baseline"]
    feasibility = {name: len(validate_plan(plan, land, planting)) for name, plan in plans.items()}
    checks = [
        {
            "tested_claim": "Q1(1) prioritizes avoiding unsold waste",
            "perturbation": "expected sales multiplied by 0.95, 1.00, and 1.05 with the accepted plan fixed",
            "metric_threshold": "main excess rate <= 10% at every tested level (predeclared)",
            "observed_value": {str(row["demand_scale"]): row["mean_excess_rate"] for row in case1},
            "status": "PASS" if max(row["mean_excess_rate"] for row in case1) <= 0.10 else "FAIL",
            "limitation": "This does not reduce the accepted rolling-window optimality gap.",
            "fallback_trigger_relevance": "Q1-F1 remains triggered by the recorded 48.858% MIP gap.",
        },
        {
            "tested_claim": "The accepted Q1 plans remain feasible",
            "perturbation": "re-run all hard-constraint checks on saved plans",
            "metric_threshold": "zero constraint errors",
            "observed_value": feasibility,
            "status": "PASS" if max(feasibility.values()) == 0 else "FAIL",
            "limitation": "Economic-parameter assumptions are not feasibility constraints.",
            "fallback_trigger_relevance": "No new feasibility trigger.",
        },
        {
            "tested_claim": "Waste control materially improves on the usable baseline",
            "perturbation": "same ±5% expected-sales evaluation for main and baseline",
            "metric_threshold": "main excess rate below baseline at every tested level",
            "observed_value": {
                str(scale): {
                    "main": next(r["mean_excess_rate"] for r in case1 if r["demand_scale"] == scale),
                    "baseline": next(r["mean_excess_rate"] for r in baseline if r["demand_scale"] == scale),
                }
                for scale in scales
            },
            "status": "PASS" if all(
                next(r["mean_excess_rate"] for r in case1 if r["demand_scale"] == scale)
                < next(r["mean_excess_rate"] for r in baseline if r["demand_scale"] == scale)
                for scale in scales
            ) else "FAIL",
            "limitation": "The baseline is a concentration-prone greedy lower bound.",
            "fallback_trigger_relevance": "Supports the accepted main plan but not global optimality.",
        },
    ]
    return {
        "schema_version": 1,
        "question": "Q1",
        "profile": "lean",
        "input_sources": [
            "results/Q1/experiments/round1/run_summary.json",
            "results/Q1/experiments/round1/tables/result1_1_main.csv",
            "results/Q1/experiments/round1/tables/result1_2_main.csv",
            "results/Q1/experiments/round1/tables/result1_baseline.csv",
        ],
        "checks": checks,
        "observations": observations,
        "overall_status": "CONDITIONAL" if all(c["status"] == "PASS" for c in checks) else "FAIL",
        "overall_limitation": "Human accepted a feasible approximation; maximum recorded MIP gap remains 48.858%.",
    }


def q2_checks(land, crops, planting, economics):
    table_dir = ROOT / "results" / "Q2" / "experiments" / "round1" / "tables"
    main = load_plan(table_dir / "result2_main.csv", land)
    baseline = load_plan(table_dir / "result2_baseline.csv", land)
    observations = []
    for seed in SEEDS:
        scenarios, _ = generate_scenarios(crops, 100, seed, correlated=False)
        main_metrics = profit_distribution(evaluate_plan(main, land, planting, economics, scenarios, 0.5))
        base_metrics = profit_distribution(evaluate_plan(baseline, land, planting, economics, scenarios, 0.5))
        observations.append({
            "seed": seed,
            "main_mean_profit_yuan": main_metrics["mean_profit_yuan"],
            "baseline_mean_profit_yuan": base_metrics["mean_profit_yuan"],
            "mean_difference_yuan": main_metrics["mean_profit_yuan"] - base_metrics["mean_profit_yuan"],
            "main_lower_10pct_mean_profit_yuan": main_metrics["lower_10pct_mean_profit_yuan"],
            "baseline_lower_10pct_mean_profit_yuan": base_metrics["lower_10pct_mean_profit_yuan"],
            "lower_tail_difference_yuan": main_metrics["lower_10pct_mean_profit_yuan"] - base_metrics["lower_10pct_mean_profit_yuan"],
            "main_excess_rate": main_metrics["mean_excess_rate"],
            "baseline_excess_rate": base_metrics["mean_excess_rate"],
        })
    feasibility = {"main": len(validate_plan(main, land, planting)), "baseline": len(validate_plan(baseline, land, planting))}
    checks = [
        {
            "tested_claim": "Q2 main has higher mean profit than the usable baseline",
            "perturbation": "five new fixed seeds, 100 independent scenarios per seed",
            "metric_threshold": "positive mean-profit difference for every seed",
            "observed_value": {str(r["seed"]): r["mean_difference_yuan"] for r in observations},
            "status": "PASS" if all(r["mean_difference_yuan"] > 0 for r in observations) else "FAIL",
            "limitation": "Fixed-plan evaluation does not re-optimize under each seed.",
            "fallback_trigger_relevance": "A sign reversal would make the accepted superiority claim conditional.",
        },
        {
            "tested_claim": "Q2 main improves lower-tail profit",
            "perturbation": "same five 100-scenario evaluation sets",
            "metric_threshold": "positive lower-10%-mean difference for every seed",
            "observed_value": {str(r["seed"]): r["lower_tail_difference_yuan"] for r in observations},
            "status": "PASS" if all(r["lower_tail_difference_yuan"] > 0 for r in observations) else "FAIL",
            "limitation": "Tail estimates remain Monte Carlo estimates.",
            "fallback_trigger_relevance": "Tests the accepted risk-balanced direction.",
        },
        {
            "tested_claim": "Accepted Q2 plans remain feasible",
            "perturbation": "re-run all hard-constraint checks",
            "metric_threshold": "zero constraint errors",
            "observed_value": feasibility,
            "status": "PASS" if max(feasibility.values()) == 0 else "FAIL",
            "limitation": "Does not test missing economic fields.",
            "fallback_trigger_relevance": "No new feasibility trigger.",
        },
    ]
    return {
        "schema_version": 1,
        "question": "Q2",
        "profile": "lean",
        "input_sources": [
            "results/Q2/experiments/round1/run_summary.json",
            "results/Q2/experiments/round1/tables/result2_main.csv",
            "results/Q2/experiments/round1/tables/result2_baseline.csv",
        ],
        "checks": checks,
        "observations": observations,
        "overall_status": "PASS" if all(c["status"] == "PASS" for c in checks) else "CONDITIONAL",
    }


def q3_checks(land, crops, planting, economics):
    table_dir = ROOT / "results" / "Q3" / "experiments" / "round1" / "tables"
    main = load_plan(table_dir / "result3_main.csv", land)
    q2_plan = load_plan(table_dir / "result3_baseline_q2_plan.csv", land)
    observations = []
    for strength in [0.5, 1.0, 1.5]:
        for seed in SEEDS[:3]:
            scenarios, metadata = generate_scenarios(
                crops, 100, seed, correlated=True, relationship_strength=strength
            )
            main_metrics = profit_distribution(evaluate_plan(main, land, planting, economics, scenarios, 0.5))
            q2_metrics = profit_distribution(evaluate_plan(q2_plan, land, planting, economics, scenarios, 0.5))
            observations.append({
                "strength": strength,
                "seed": seed,
                "minimum_correlation_eigenvalue": metadata["minimum_eigenvalue"],
                "q3_mean_profit_yuan": main_metrics["mean_profit_yuan"],
                "q2_mean_profit_yuan": q2_metrics["mean_profit_yuan"],
                "mean_difference_yuan": main_metrics["mean_profit_yuan"] - q2_metrics["mean_profit_yuan"],
                "q3_lower_10pct_mean_profit_yuan": main_metrics["lower_10pct_mean_profit_yuan"],
                "q2_lower_10pct_mean_profit_yuan": q2_metrics["lower_10pct_mean_profit_yuan"],
                "lower_tail_difference_yuan": main_metrics["lower_10pct_mean_profit_yuan"] - q2_metrics["lower_10pct_mean_profit_yuan"],
            })
    feasibility = {"q3_main": len(validate_plan(main, land, planting)), "q2_plan": len(validate_plan(q2_plan, land, planting))}
    profit_values = [r["q3_mean_profit_yuan"] for r in observations]
    relative_range = (max(profit_values) - min(profit_values)) / (sum(profit_values) / len(profit_values))
    checks = [
        {
            "tested_claim": "Q3 main is retained without claiming superiority over Q2",
            "perturbation": "three relationship strengths and three new seeds, 100 correlated scenarios per cell",
            "metric_threshold": "Q3-Q2 mean-profit difference <= 0 in every tested cell",
            "observed_value": {f"strength_{r['strength']}_seed_{r['seed']}": r["mean_difference_yuan"] for r in observations},
            "status": "PASS" if all(r["mean_difference_yuan"] <= 0 for r in observations) else "CONDITIONAL",
            "limitation": "The relationship matrix and substitution/complement response remain simulated assumptions.",
            "fallback_trigger_relevance": "Supports the explicit non-superiority limitation; it does not activate Q3-F1 because the human retained Q3-M1.",
        },
        {
            "tested_claim": "Q3 plan-level profit is not dominated by relationship-strength instability",
            "perturbation": "relationship strength 0.5, 1.0, 1.5 across three seeds",
            "metric_threshold": "relative range of mean profit < 1% (predeclared)",
            "observed_value": relative_range,
            "status": "PASS" if relative_range < 0.01 else "FAIL",
            "limitation": "A small profit range does not validate the assumed causal relationships.",
            "fallback_trigger_relevance": "Tests the recorded ±50% sensitivity condition.",
        },
        {
            "tested_claim": "Accepted Q3 plan remains feasible",
            "perturbation": "re-run all hard-constraint checks",
            "metric_threshold": "zero constraint errors",
            "observed_value": feasibility,
            "status": "PASS" if max(feasibility.values()) == 0 else "FAIL",
            "limitation": "Scenario assumptions do not affect deterministic planting feasibility.",
            "fallback_trigger_relevance": "No new feasibility trigger.",
        },
    ]
    return {
        "schema_version": 1,
        "question": "Q3",
        "profile": "lean",
        "input_sources": [
            "results/Q3/experiments/round1/run_summary.json",
            "results/Q3/experiments/round1/tables/result3_main.csv",
            "results/Q3/experiments/round1/tables/result3_baseline_q2_plan.csv",
        ],
        "checks": checks,
        "observations": observations,
        "overall_status": "PASS" if all(c["status"] == "PASS" for c in checks) else "CONDITIONAL",
    }


def main():
    land, crops, planting, economics = load_inputs()
    summaries = {
        "Q1": q1_checks(land, crops, planting, economics),
        "Q2": q2_checks(land, crops, planting, economics),
        "Q3": q3_checks(land, crops, planting, economics),
    }
    for question, summary in summaries.items():
        target = ROOT / "robustness" / question / f"{question.lower()}_robustness_summary.json"
        write_json(target, summary)
        print(f"{question}: {summary['overall_status']} -> {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
