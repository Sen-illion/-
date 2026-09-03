from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import probe_screening as probe


def main():
    probe.YEARS = [2024, 2025, 2026]
    land, crops, planting, econ = probe.load_data()
    profit_only, solution_profit = probe.solve_q1(
        land, planting, econ, "waste", waste_weight=0.0, time_limit=20
    )
    waste_priority, solution_waste = probe.solve_q1(
        land, planting, econ, "waste", waste_weight=0.50, time_limit=20
    )
    rng = np.random.default_rng(240902)
    shift = {int(crop): float(1 + rng.uniform(-0.05, 0.05)) for crop in crops.crop_id}
    perturbed, solution_perturbed = probe.solve_q1(
        land, planting, econ, "waste", waste_weight=0.50,
        price_shift=shift, time_limit=20
    )

    def overlap(a, b):
        keys = set(a) | set(b)
        numerator = sum(min(a.get(key, 0.0), b.get(key, 0.0)) for key in keys)
        denominator = sum(max(a.get(key, 0.0), b.get(key, 0.0)) for key in keys)
        return numerator / denominator if denominator else 1.0

    output = {
        "years": probe.YEARS,
        "profit_only": profit_only,
        "waste_priority": waste_priority,
        "price_perturbed": perturbed,
        "waste_change_with_priority_jin": waste_priority["waste_jin"] - profit_only["waste_jin"],
        "profit_change_with_priority_yuan": waste_priority["profit_yuan"] - profit_only["profit_yuan"],
        "price_perturbation_area_jaccard": overlap(solution_waste, solution_perturbed),
    }
    path = Path(__file__).resolve().parent / "probe_reduced_metrics.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "profit_only": {k: profit_only[k] for k in ("status", "runtime_seconds", "mip_gap", "profit_yuan", "waste_jin")},
        "waste_priority": {k: waste_priority[k] for k in ("status", "runtime_seconds", "mip_gap", "profit_yuan", "waste_jin")},
        "waste_change_with_priority_jin": output["waste_change_with_priority_jin"],
        "profit_change_with_priority_yuan": output["profit_change_with_priority_yuan"],
        "price_perturbation_area_jaccard": output["price_perturbation_area_jaccard"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
