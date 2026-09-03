from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "workspace" / "data_clean"
YEARS = list(range(2024, 2031))
DRY_TYPES = {"平旱地", "梯田", "山坡地"}
BEANS = set(range(1, 6)) | set(range(17, 20))
DRY_CROPS = list(range(1, 16))
RICE = [16]
VEG1 = list(range(17, 35))
VEG2 = list(range(35, 38))
MUSHROOMS = list(range(38, 42))


def load_data():
    land = pd.read_csv(DATA / "land.csv")
    crops = pd.read_csv(DATA / "crops.csv")
    planting = pd.read_csv(DATA / "planting_2023.csv")
    econ = pd.read_csv(DATA / "economics_2023.csv")
    for frame in (land, crops, planting, econ):
        for column in frame.select_dtypes(include=["object", "string"]):
            frame[column] = frame[column].astype(str).str.strip()
    return land, crops, planting, econ


def valid_slots(land):
    slots = []
    for row in land.itertuples(index=False):
        plot, land_type = row.plot_id, row.land_type
        if land_type in DRY_TYPES:
            pairs = [("单季", crop) for crop in DRY_CROPS]
        elif land_type == "水浇地":
            pairs = [("单季", 16)] + [("第一季", crop) for crop in VEG1] + [("第二季", crop) for crop in VEG2]
        elif land_type == "普通大棚":
            pairs = [("第一季", crop) for crop in VEG1] + [("第二季", crop) for crop in MUSHROOMS]
        elif land_type == "智慧大棚":
            pairs = [(season, crop) for season in ("第一季", "第二季") for crop in VEG1]
        else:
            raise ValueError(f"Unknown land type: {land_type}")
        for year in YEARS:
            slots.extend((plot, land_type, year, season, crop) for season, crop in pairs)
    return slots


def economic_maps(econ):
    detail = {}
    for row in econ.itertuples(index=False):
        key = (int(row.crop_id), row.land_type, row.season)
        detail[key] = {
            "yield": float(row.yield_jin_per_mu),
            "cost": float(row.cost_yuan_per_mu),
            "price": (float(row.price_low_yuan_per_jin) + float(row.price_high_yuan_per_jin)) / 2,
        }
    for crop in VEG1:
        second = (crop, "智慧大棚", "第二季")
        first = (crop, "智慧大棚", "第一季")
        if first not in detail and second in detail:
            detail[first] = dict(detail[second])
    prices = defaultdict(list)
    for (crop, _, _), value in detail.items():
        prices[crop].append(value["price"])
    crop_price = {crop: float(np.mean(values)) for crop, values in prices.items()}
    return detail, crop_price


def demand_2023(land, planting, detail):
    land_type = dict(zip(land.plot_id, land.land_type))
    demand = defaultdict(float)
    bean_area = defaultdict(float)
    for row in planting.itertuples(index=False):
        plot = row.plot_id
        crop = int(row.crop_id)
        season = row.season
        area = float(row.area_mu)
        key = (crop, land_type[plot], season)
        demand[(crop, season)] += area * detail[key]["yield"]
        if crop in BEANS:
            bean_area[plot] += area
    return dict(demand), dict(bean_area)


class ConstraintBuilder:
    def __init__(self):
        self.rows = []
        self.lower = []
        self.upper = []

    def add(self, coefficients, lower=-np.inf, upper=np.inf):
        self.rows.append(coefficients)
        self.lower.append(lower)
        self.upper.append(upper)

    def matrix(self, nvars):
        rr, cc, vv = [], [], []
        for row_no, coefficients in enumerate(self.rows):
            for col, value in coefficients.items():
                if value:
                    rr.append(row_no)
                    cc.append(col)
                    vv.append(value)
        matrix = coo_matrix((vv, (rr, cc)), shape=(len(self.rows), nvars)).tocsr()
        return LinearConstraint(matrix, np.asarray(self.lower), np.asarray(self.upper))


def solve_q1(land, planting, econ, case, waste_weight=0.0, price_shift=None, time_limit=45):
    detail, crop_price = economic_maps(econ)
    demand, bean_2023 = demand_2023(land, planting, detail)
    area = dict(zip(land.plot_id, land.area_mu.astype(float)))
    slots = valid_slots(land)
    nslots = len(slots)
    x_index = {slot: k for k, slot in enumerate(slots)}
    y_index = {slot: nslots + k for k, slot in enumerate(slots)}
    next_var = 2 * nslots

    water_mode = {}
    for row in land.itertuples(index=False):
        if row.land_type == "水浇地":
            for year in YEARS:
                water_mode[(row.plot_id, year)] = next_var
                next_var += 1

    sale_keys = sorted({(crop, year, season) for _, _, year, season, crop in slots})
    sold_index = {}
    for key in sale_keys:
        sold_index[key] = next_var
        next_var += 1

    c = np.zeros(next_var)
    lower = np.zeros(next_var)
    upper = np.full(next_var, np.inf)
    integrality = np.zeros(next_var, dtype=np.uint8)
    for slot in slots:
        plot, land_type, _, season, crop = slot
        x = x_index[slot]
        y = y_index[slot]
        values = detail[(crop, land_type, season)]
        price = crop_price[crop]
        if price_shift is not None:
            price *= price_shift.get(crop, 1.0)
        if case == "waste":
            c[x] = values["cost"] + waste_weight * price * values["yield"]
        elif case == "half_price":
            c[x] = values["cost"] - 0.5 * price * values["yield"]
        else:
            raise ValueError(case)
        integrality[y] = 1
        upper[y] = 1
    for index in water_mode.values():
        integrality[index] = 1
        upper[index] = 1
    for (crop, _, _), index in sold_index.items():
        price = crop_price[crop]
        if price_shift is not None:
            price *= price_shift.get(crop, 1.0)
        c[index] = -(1 + waste_weight) * price if case == "waste" else -0.5 * price

    constraints = ConstraintBuilder()
    for slot in slots:
        plot, land_type, _, _, _ = slot
        x, y = x_index[slot], y_index[slot]
        plot_area = area[plot]
        minimum = 0.1 if "大棚" in land_type else max(0.5, 0.05 * plot_area)
        constraints.add({x: 1, y: -plot_area}, upper=0)
        constraints.add({x: -1, y: minimum}, upper=0)

    by_plot_year_season = defaultdict(list)
    for slot in slots:
        plot, _, year, season, _ = slot
        by_plot_year_season[(plot, year, season)].append(x_index[slot])
    land_type_map = dict(zip(land.plot_id, land.land_type))
    for (plot, year, season), indexes in by_plot_year_season.items():
        coefficients = {index: 1 for index in indexes}
        if land_type_map[plot] == "水浇地":
            mode = water_mode[(plot, year)]
            if season == "单季":
                coefficients[mode] = -area[plot]
                constraints.add(coefficients, upper=0)
            else:
                coefficients[mode] = area[plot]
                constraints.add(coefficients, upper=area[plot])
        else:
            constraints.add(coefficients, upper=area[plot])

    for row in land.itertuples(index=False):
        plot, land_type = row.plot_id, row.land_type
        if land_type in DRY_TYPES:
            for crop in DRY_CROPS:
                for y1, y2 in zip(YEARS[:-1], YEARS[1:]):
                    constraints.add({y_index[(plot, land_type, y1, "单季", crop)]: 1,
                                     y_index[(plot, land_type, y2, "单季", crop)]: 1}, upper=1)
        elif land_type == "水浇地":
            for y1, y2 in zip(YEARS[:-1], YEARS[1:]):
                constraints.add({y_index[(plot, land_type, y1, "单季", 16)]: 1,
                                 y_index[(plot, land_type, y2, "单季", 16)]: 1}, upper=1)
        elif land_type == "智慧大棚":
            for crop in VEG1:
                for year in YEARS:
                    constraints.add({y_index[(plot, land_type, year, "第一季", crop)]: 1,
                                     y_index[(plot, land_type, year, "第二季", crop)]: 1}, upper=1)
                for y1, y2 in zip(YEARS[:-1], YEARS[1:]):
                    constraints.add({y_index[(plot, land_type, y1, "第二季", crop)]: 1,
                                     y_index[(plot, land_type, y2, "第一季", crop)]: 1}, upper=1)

    bean_x = defaultdict(list)
    for slot in slots:
        plot, _, year, _, crop = slot
        if crop in BEANS:
            bean_x[(plot, year)].append(x_index[slot])
    for plot, plot_area in area.items():
        for start in range(2023, max(YEARS) - 1):
            coefficients = {}
            for year in range(max(2024, start), min(2030, start + 2) + 1):
                for index in bean_x[(plot, year)]:
                    coefficients[index] = -1
            prior = bean_2023.get(plot, 0.0) if start == 2023 else 0.0
            constraints.add(coefficients, upper=-(plot_area - min(prior, plot_area)))

    production_terms = defaultdict(dict)
    for slot in slots:
        _, land_type, year, season, crop = slot
        index = x_index[slot]
        production_terms[(crop, year, season)][index] = detail[(crop, land_type, season)]["yield"]
    for key, index in sold_index.items():
        crop, _, season = key
        coefficients = {index: 1}
        coefficients.update({col: -value for col, value in production_terms[key].items()})
        constraints.add(coefficients, upper=0)
        constraints.add({index: 1}, upper=demand.get((crop, season), 0.0))

    start = time.perf_counter()
    result = milp(
        c,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=constraints.matrix(next_var),
        options={"time_limit": time_limit, "mip_rel_gap": 0.01, "presolve": True},
    )
    runtime = time.perf_counter() - start
    if result.x is None:
        return {"status": "FAIL", "message": result.message, "runtime_seconds": runtime,
                "variables": next_var, "constraints": len(constraints.rows)}, None

    solution = {slot: max(0.0, result.x[index]) for slot, index in x_index.items() if result.x[index] > 1e-7}
    metrics = evaluate_plan(solution, land, detail, crop_price, demand, case, price_shift)
    metrics.update({
        "status": "PASS" if result.success else "CONDITIONAL",
        "solver_status": int(result.status),
        "message": result.message,
        "runtime_seconds": runtime,
        "variables": next_var,
        "binary_variables": int(integrality.sum()),
        "constraints": len(constraints.rows),
        "objective_minimized": float(result.fun),
        "mip_gap": None if getattr(result, "mip_gap", None) is None else float(result.mip_gap),
    })
    return metrics, solution


def evaluate_plan(solution, land, detail, crop_price, demand, case, price_shift=None,
                  multipliers=None):
    production = defaultdict(float)
    cost = 0.0
    area_by_crop = defaultdict(float)
    for (plot, land_type, year, season, crop), planted_area in solution.items():
        values = detail[(crop, land_type, season)]
        ym = multipliers.get(("yield", crop, year), 1.0) if multipliers else 1.0
        cm = multipliers.get(("cost", crop, year), 1.0) if multipliers else 1.0
        production[(crop, year, season)] += planted_area * values["yield"] * ym
        cost += planted_area * values["cost"] * cm
        area_by_crop[crop] += planted_area
    revenue = 0.0
    waste = 0.0
    for (crop, year, season), quantity in production.items():
        dm = multipliers.get(("demand", crop, year), 1.0) if multipliers else 1.0
        pm = multipliers.get(("price", crop, year), 1.0) if multipliers else 1.0
        expected = demand.get((crop, season), 0.0) * dm
        normal = min(quantity, expected)
        excess = max(0.0, quantity - expected)
        price = crop_price[crop] * pm
        if price_shift is not None:
            price *= price_shift.get(crop, 1.0)
        revenue += price * normal + (0.5 * price * excess if case == "half_price" else 0.0)
        waste += excess
    total_area = sum(area_by_crop.values())
    shares = sorted((value / total_area for value in area_by_crop.values()), reverse=True) if total_area else []
    positives = list(solution.values())
    return {
        "profit_yuan": revenue - cost,
        "revenue_yuan": revenue,
        "cost_yuan": cost,
        "waste_jin": waste,
        "waste_to_production": waste / max(sum(production.values()), 1e-9),
        "unique_crops": len(area_by_crop),
        "top1_area_mass": shares[0] if shares else 0.0,
        "top5_area_mass": sum(shares[:5]),
        "positive_plot_crop_assignments": len(positives),
        "minimum_positive_area_mu": min(positives) if positives else 0.0,
    }


def greedy_baseline(land, planting, econ):
    detail, crop_price = economic_maps(econ)
    demand, bean_2023 = demand_2023(land, planting, detail)
    area = dict(zip(land.plot_id, land.area_mu.astype(float)))
    solution = {}
    previous = {}

    def margin(crop, land_type, season):
        values = detail[(crop, land_type, season)]
        return values["yield"] * crop_price[crop] - values["cost"]

    def best(candidates, land_type, season, excluded=None):
        excluded = set() if excluded is None else set(excluded)
        eligible = [crop for crop in candidates if crop not in excluded]
        return max(eligible, key=lambda crop: margin(crop, land_type, season))

    for plot_no, row in enumerate(land.itertuples(index=False)):
        plot, land_type, plot_area = row.plot_id, row.land_type, float(row.area_mu)
        planted_bean_2023 = bean_2023.get(plot, 0.0) >= plot_area - 1e-9
        bean_years = {2026, 2029} if planted_bean_2023 else {2025, 2028}
        for year in YEARS:
            force_bean = year in bean_years
            if land_type in DRY_TYPES:
                candidates = list(range(1, 6)) if force_bean else list(range(6, 16))
                crop = best(candidates, land_type, "单季", {previous.get((plot, "last"))})
                solution[(plot, land_type, year, "单季", crop)] = plot_area
                previous[(plot, "last")] = crop
            elif land_type == "水浇地":
                if force_bean or previous.get((plot, "last")) == 16:
                    first = best(list(range(17, 20)) if force_bean else VEG1, land_type, "第一季",
                                 {previous.get((plot, "last"))})
                    second = best(VEG2, land_type, "第二季", {first})
                    solution[(plot, land_type, year, "第一季", first)] = plot_area
                    solution[(plot, land_type, year, "第二季", second)] = plot_area
                    previous[(plot, "last")] = second
                else:
                    rice_margin = margin(16, land_type, "单季")
                    first = best(VEG1, land_type, "第一季", {previous.get((plot, "last"))})
                    second = best(VEG2, land_type, "第二季", {first})
                    if rice_margin >= margin(first, land_type, "第一季") + margin(second, land_type, "第二季"):
                        solution[(plot, land_type, year, "单季", 16)] = plot_area
                        previous[(plot, "last")] = 16
                    else:
                        solution[(plot, land_type, year, "第一季", first)] = plot_area
                        solution[(plot, land_type, year, "第二季", second)] = plot_area
                        previous[(plot, "last")] = second
            elif land_type == "普通大棚":
                first = best(list(range(17, 20)) if force_bean else VEG1, land_type, "第一季",
                             {previous.get((plot, "last"))})
                second = best(MUSHROOMS, land_type, "第二季", {first})
                solution[(plot, land_type, year, "第一季", first)] = plot_area
                solution[(plot, land_type, year, "第二季", second)] = plot_area
                previous[(plot, "last")] = second
            elif land_type == "智慧大棚":
                first = best(list(range(17, 20)) if force_bean else VEG1, land_type, "第一季",
                             {previous.get((plot, "last"))})
                second = best(VEG1, land_type, "第二季", {first})
                solution[(plot, land_type, year, "第一季", first)] = plot_area
                solution[(plot, land_type, year, "第二季", second)] = plot_area
                previous[(plot, "last")] = second
    return solution, detail, crop_price, demand


def scenario_multipliers(crops, n, seed, correlated):
    rng = np.random.default_rng(seed)
    crop_ids = sorted(int(x) for x in crops.crop_id.unique())
    scenarios = []
    if correlated:
        corr = np.array([[1.0, -0.35, 0.25, 0.30], [-0.35, 1.0, -0.10, -0.20],
                         [0.25, -0.10, 1.0, 0.40], [0.30, -0.20, 0.40, 1.0]])
        eigenvalues = np.linalg.eigvalsh(corr)
        chol = np.linalg.cholesky(corr)
    else:
        corr = np.eye(4)
        eigenvalues = np.ones(4)
        chol = np.eye(4)
    for scenario_no in range(n):
        values = {}
        for year in YEARS:
            common = rng.normal(size=4) @ chol.T
            for crop in crop_ids:
                idio = rng.normal(size=4)
                z = 0.65 * common + math.sqrt(1 - 0.65 ** 2) * idio
                yield_m = 1 + 0.10 * np.tanh(z[0])
                cost_m = (1.05 ** (year - 2023)) * (1 + 0.02 * np.tanh(z[1]))
                if crop in (6, 7):
                    demand_m = (1 + 0.075 * (0.5 + 0.5 * np.tanh(z[2]))) ** (year - 2023)
                else:
                    demand_m = 1 + 0.05 * np.tanh(z[2])
                if crop <= 16:
                    price_m = 1.0
                elif crop <= 37:
                    price_m = 1.05 ** (year - 2023)
                elif crop == 41:
                    price_m = 0.95 ** (year - 2023)
                else:
                    decline = 0.03 + 0.02 * np.tanh(z[3])
                    price_m = (1 - decline) ** (year - 2023)
                values[("yield", crop, year)] = float(yield_m)
                values[("cost", crop, year)] = float(cost_m)
                values[("demand", crop, year)] = float(demand_m)
                values[("price", crop, year)] = float(price_m)
        scenarios.append(values)
    return scenarios, {"matrix": corr.tolist(), "min_eigenvalue": float(eigenvalues.min())}


def distribution_summary(values):
    values = np.asarray(values, dtype=float)
    lower = values[values <= np.quantile(values, 0.10)]
    return {
        "mean": float(values.mean()),
        "std": float(values.std(ddof=1)),
        "p05": float(np.quantile(values, 0.05)),
        "p50": float(np.quantile(values, 0.50)),
        "p95": float(np.quantile(values, 0.95)),
        "lower_10pct_mean": float(lower.mean()),
    }


def main():
    land, crops, planting, econ = load_data()
    detail, crop_price = economic_maps(econ)
    demand, _ = demand_2023(land, planting, detail)

    q1_profit_only, _ = solve_q1(land, planting, econ, "waste", waste_weight=0.0)
    q1_waste, solution_waste = solve_q1(land, planting, econ, "waste", waste_weight=0.50)
    q1_half, solution_half = solve_q1(land, planting, econ, "half_price")
    rng = np.random.default_rng(240902)
    perturb = {int(crop): float(1 + rng.uniform(-0.05, 0.05)) for crop in crops.crop_id}
    q1_perturbed, perturbed_solution = solve_q1(
        land, planting, econ, "waste", waste_weight=0.50, price_shift=perturb, time_limit=45
    )

    baseline_solution, _, _, _ = greedy_baseline(land, planting, econ)
    baseline_waste = evaluate_plan(baseline_solution, land, detail, crop_price, demand, "waste")
    baseline_half = evaluate_plan(baseline_solution, land, detail, crop_price, demand, "half_price")

    def area_overlap(a, b):
        keys = set(a) | set(b)
        numerator = sum(min(a.get(key, 0.0), b.get(key, 0.0)) for key in keys)
        denominator = sum(max(a.get(key, 0.0), b.get(key, 0.0)) for key in keys)
        return numerator / denominator if denominator else 1.0

    independent, independent_corr = scenario_multipliers(crops, 100, 20240902, False)
    correlated, correlated_corr = scenario_multipliers(crops, 100, 20240902, True)
    independent_repeat, _ = scenario_multipliers(crops, 100, 20240902, False)
    reproducible = independent[0] == independent_repeat[0] and independent[-1] == independent_repeat[-1]

    q2_profit = [evaluate_plan(solution_half, land, detail, crop_price, demand, "half_price", multipliers=s)["profit_yuan"]
                 for s in independent]
    q2_baseline_profit = [evaluate_plan(baseline_solution, land, detail, crop_price, demand, "half_price", multipliers=s)["profit_yuan"]
                          for s in independent]
    q3_profit = [evaluate_plan(solution_half, land, detail, crop_price, demand, "half_price", multipliers=s)["profit_yuan"]
                 for s in correlated]

    slots_per_year = len(valid_slots(land)) // len(YEARS)
    scale = {
        "valid_area_variables_per_year": slots_per_year,
        "valid_area_variables_7_year": slots_per_year * len(YEARS),
        "estimated_q1_total_variables": int(q1_waste["variables"]),
        "estimated_q2_extra_sales_variables_at_200_scenarios": len({(crop, year, season) for _, _, year, season, crop in valid_slots(land)}) * 200,
    }
    output = {
        "generated_at": "2026-09-02T22:50:00+08:00",
        "q1": {
            "profit_only": q1_profit_only,
            "waste_priority": q1_waste,
            "half_price": q1_half,
            "price_perturbed": q1_perturbed,
            "price_perturbation_area_jaccard": area_overlap(solution_waste, perturbed_solution),
            "baseline_waste": baseline_waste,
            "baseline_half_price": baseline_half,
            "waste_priority_profit_change_vs_profit_only": q1_waste["profit_yuan"] - q1_profit_only["profit_yuan"],
            "waste_priority_waste_change_vs_profit_only": q1_waste["waste_jin"] - q1_profit_only["waste_jin"],
        },
        "q2": {
            "scenario_count": len(independent),
            "seed": 20240902,
            "seed_reproducible": reproducible,
            "correlation_check": independent_corr,
            "mean_value_plan_profit_distribution": distribution_summary(q2_profit),
            "greedy_baseline_profit_distribution": distribution_summary(q2_baseline_profit),
            "surplus_rule_warning": "Probe evaluation uses 50% salvage for excess; Q2 statement does not explicitly select the inherited surplus rule."
        },
        "q3": {
            "scenario_count": len(correlated),
            "seed": 20240902,
            "correlation_check": correlated_corr,
            "correlated_profit_distribution": distribution_summary(q3_profit),
            "independent_profit_distribution": distribution_summary(q2_profit),
            "mean_profit_change_correlated_vs_independent": float(np.mean(q3_profit) - np.mean(q2_profit)),
            "lower_tail_change_correlated_vs_independent": distribution_summary(q3_profit)["lower_10pct_mean"] - distribution_summary(q2_profit)["lower_10pct_mean"],
        },
        "scale": scale,
    }
    out = ROOT / "methods" / "probe_metrics.json"
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"q1": {k: q1_waste[k] for k in ("status", "runtime_seconds", "profit_yuan", "waste_jin", "unique_crops", "top5_area_mass")},
                      "q2": output["q2"]["mean_value_plan_profit_distribution"],
                      "q3": output["q3"]["correlated_profit_distribution"],
                      "scale": scale}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
