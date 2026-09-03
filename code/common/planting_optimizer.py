from __future__ import annotations

import json
import math
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "workspace" / "data_clean"
ALL_YEARS = list(range(2024, 2031))
DRY_TYPES = {"平旱地", "梯田", "山坡地"}
DRY_CROPS = list(range(1, 16))
RICE = [16]
VEG1 = list(range(17, 35))
VEG2 = list(range(35, 38))
MUSHROOMS = list(range(38, 42))
BEANS = set(range(1, 6)) | set(range(17, 20))
SEASON_ORDER = {"单季": 1, "第一季": 1, "第二季": 2}


def load_inputs():
    land = pd.read_csv(DATA_DIR / "land.csv")
    crops = pd.read_csv(DATA_DIR / "crops.csv")
    planting = pd.read_csv(DATA_DIR / "planting_2023.csv")
    economics = pd.read_csv(DATA_DIR / "economics_2023.csv")
    for frame in (land, crops, planting, economics):
        for column in frame.select_dtypes(include=["object", "string"]):
            frame[column] = frame[column].astype(str).str.strip()
    return land, crops, planting, economics


def build_economic_maps(economics):
    detail = {}
    prices = defaultdict(list)
    for row in economics.itertuples(index=False):
        crop = int(row.crop_id)
        value = {
            "yield": float(row.yield_jin_per_mu),
            "cost": float(row.cost_yuan_per_mu),
            "price": (float(row.price_low_yuan_per_jin) + float(row.price_high_yuan_per_jin)) / 2,
        }
        detail[(crop, row.land_type, row.season)] = value
        prices[crop].append(value["price"])
    reused_smart_first = []
    for crop in VEG1:
        first = (crop, "智慧大棚", "第一季")
        second = (crop, "智慧大棚", "第二季")
        if first not in detail and second in detail:
            detail[first] = dict(detail[second])
            reused_smart_first.append(crop)
    crop_price = {crop: float(np.mean(values)) for crop, values in prices.items()}
    return detail, crop_price, reused_smart_first


def legal_pairs(land_type):
    if land_type in DRY_TYPES:
        return [("单季", crop) for crop in DRY_CROPS]
    if land_type == "水浇地":
        return [("单季", 16)] + [("第一季", crop) for crop in VEG1] + [("第二季", crop) for crop in VEG2]
    if land_type == "普通大棚":
        return [("第一季", crop) for crop in VEG1] + [("第二季", crop) for crop in MUSHROOMS]
    if land_type == "智慧大棚":
        return [(season, crop) for season in ("第一季", "第二季") for crop in VEG1]
    raise ValueError(f"Unknown land type: {land_type}")


def valid_slots(land, years):
    return [
        (row.plot_id, row.land_type, year, season, crop)
        for row in land.itertuples(index=False)
        for year in years
        for season, crop in legal_pairs(row.land_type)
    ]


def initial_state(land, planting, detail):
    land_type = dict(zip(land.plot_id, land.land_type))
    demand = defaultdict(float)
    bean_area = defaultdict(float)
    planted = defaultdict(set)
    for row in planting.itertuples(index=False):
        plot = row.plot_id
        crop = int(row.crop_id)
        season = row.season
        area = float(row.area_mu)
        demand[(crop, season)] += area * detail[(crop, land_type[plot], season)]["yield"]
        planted[(plot, season)].add(crop)
        if crop in BEANS:
            bean_area[plot] += area
    return dict(demand), dict(bean_area), planted


def unit_scenario():
    return {}


def scenario_value(scenario, kind, crop, year):
    return float(scenario.get((kind, crop, year), 1.0))


def mean_scenario(scenarios):
    keys = set().union(*(scenario.keys() for scenario in scenarios))
    return {key: float(np.mean([scenario.get(key, 1.0) for scenario in scenarios])) for key in keys}


def generate_scenarios(crops, count, seed, correlated=False, relationship_strength=1.0):
    rng = np.random.default_rng(seed)
    crop_ids = sorted(int(value) for value in crops.crop_id.unique())
    if correlated:
        base = np.array([
            [1.00, -0.35, 0.25, 0.30],
            [-0.35, 1.00, -0.10, -0.20],
            [0.25, -0.10, 1.00, 0.40],
            [0.30, -0.20, 0.40, 1.00],
        ])
        corr = np.eye(4) + relationship_strength * (base - np.eye(4))
        minimum = float(np.linalg.eigvalsh(corr).min())
        if minimum <= 1e-9:
            corr += np.eye(4) * (1e-8 - minimum)
        chol = np.linalg.cholesky(corr)
    else:
        corr = np.eye(4)
        chol = np.eye(4)

    def group(crop):
        if crop in BEANS:
            return "legume"
        if crop <= 16:
            return "grain"
        if crop <= 37:
            return "vegetable"
        return "fungus"

    scenarios = []
    for _ in range(count):
        scenario = {}
        annual_group_shocks = {
            year: {name: rng.normal(size=4) @ chol.T for name in ("legume", "grain", "vegetable", "fungus")}
            for year in ALL_YEARS
        }
        preliminary_price = {}
        preliminary_demand = {}
        for year in ALL_YEARS:
            for crop in crop_ids:
                common = annual_group_shocks[year][group(crop)]
                idiosyncratic = rng.normal(size=4)
                z = 0.65 * common + math.sqrt(1 - 0.65**2) * idiosyncratic
                yield_multiplier = 1 + 0.10 * np.tanh(z[0])
                cost_multiplier = (1.05 ** (year - 2023)) * (1 + 0.01 * np.tanh(z[1]))
                if crop in (6, 7):
                    annual_growth = 0.075 + 0.025 * np.tanh(z[2])
                    demand_multiplier = (1 + annual_growth) ** (year - 2023)
                else:
                    demand_multiplier = 1 + 0.05 * np.tanh(z[2])
                if crop <= 16:
                    price_multiplier = 1.0
                elif crop <= 37:
                    price_multiplier = (1.05 ** (year - 2023)) * (1 + 0.01 * np.tanh(z[3]))
                elif crop == 41:
                    price_multiplier = 0.95 ** (year - 2023)
                else:
                    decline = 0.03 + 0.02 * np.tanh(z[3])
                    price_multiplier = (1 - decline) ** (year - 2023)
                scenario[("yield", crop, year)] = float(yield_multiplier)
                scenario[("cost", crop, year)] = float(cost_multiplier)
                preliminary_demand[(crop, year)] = float(demand_multiplier)
                preliminary_price[(crop, year)] = float(price_multiplier)

        for year in ALL_YEARS:
            for group_name in ("legume", "grain", "vegetable", "fungus"):
                members = [crop for crop in crop_ids if group(crop) == group_name]
                deviations = np.array([preliminary_price[(crop, year)] for crop in members])
                relative = deviations / max(float(deviations.mean()), 1e-9) - 1
                for position, crop in enumerate(members):
                    cross = float((relative.sum() - relative[position]) / max(len(members) - 1, 1))
                    own = float(relative[position])
                    response = relationship_strength * (-0.15 * own + 0.15 * cross) if correlated else 0.0
                    complement = 0.0
                    if correlated and group_name == "grain":
                        legume_shock = annual_group_shocks[year]["legume"][2]
                        complement = relationship_strength * 0.03 * np.tanh(legume_shock)
                    scenario[("demand", crop, year)] = float(np.clip(preliminary_demand[(crop, year)] * (1 + response + complement), 0.5, 2.5))
                    scenario[("price", crop, year)] = preliminary_price[(crop, year)]
        scenarios.append(scenario)
    return scenarios, {
        "correlation_matrix": corr.tolist(),
        "minimum_eigenvalue": float(np.linalg.eigvalsh(corr).min()),
        "relationship_strength": relationship_strength,
        "count": count,
        "seed": seed,
    }


class ConstraintBuilder:
    def __init__(self):
        self.rows = []
        self.lower = []
        self.upper = []

    def add(self, coefficients, lower=-np.inf, upper=np.inf):
        self.rows.append(coefficients)
        self.lower.append(lower)
        self.upper.append(upper)

    def build(self, nvars):
        row_indexes, column_indexes, values = [], [], []
        for row, coefficients in enumerate(self.rows):
            for column, value in coefficients.items():
                if value:
                    row_indexes.append(row)
                    column_indexes.append(column)
                    values.append(value)
        matrix = coo_matrix(
            (values, (row_indexes, column_indexes)), shape=(len(self.rows), nvars)
        ).tocsr()
        return LinearConstraint(matrix, np.asarray(self.lower), np.asarray(self.upper))


def _committed_crop_sets(committed):
    values = defaultdict(set)
    for (plot, _, year, season, crop), area in committed.items():
        if area > 1e-7:
            values[(plot, year, season)].add(crop)
    return values


def solve_window(
    land,
    planting,
    economics,
    years,
    committed,
    scenarios,
    surplus_fraction,
    waste_weight=0.0,
    risk_weight=0.0,
    alpha=0.90,
    time_limit=20,
    mip_gap=0.05,
):
    detail, crop_price, reused_smart_first = build_economic_maps(economics)
    demand, bean_2023, planted_2023 = initial_state(land, planting, detail)
    area = dict(zip(land.plot_id, land.area_mu.astype(float)))
    land_type_map = dict(zip(land.plot_id, land.land_type))
    slots = valid_slots(land, years)
    nslots = len(slots)
    x_index = {slot: position for position, slot in enumerate(slots)}
    y_index = {slot: nslots + position for position, slot in enumerate(slots)}
    next_variable = 2 * nslots

    water_mode = {}
    for row in land.itertuples(index=False):
        if row.land_type == "水浇地":
            for year in years:
                water_mode[(row.plot_id, year)] = next_variable
                next_variable += 1

    sale_keys = sorted({(crop, year, season) for _, _, year, season, crop in slots})
    sold_index = {}
    for scenario_no in range(len(scenarios)):
        for key in sale_keys:
            sold_index[(scenario_no, *key)] = next_variable
            next_variable += 1

    eta_index = None
    xi_index = {}
    if risk_weight > 0 and len(scenarios) > 1:
        eta_index = next_variable
        next_variable += 1
        for scenario_no in range(len(scenarios)):
            xi_index[scenario_no] = next_variable
            next_variable += 1

    objective = np.zeros(next_variable)
    lower = np.zeros(next_variable)
    upper = np.full(next_variable, np.inf)
    integrality = np.zeros(next_variable, dtype=np.uint8)
    if eta_index is not None:
        lower[eta_index] = -np.inf
        upper[eta_index] = np.inf

    median_margin = []
    for _, land_type, _, season, crop in slots:
        values = detail[(crop, land_type, season)]
        median_margin.append(max(values["yield"] * crop_price[crop] - values["cost"], 0.0))
    fragmentation_penalty = 0.01 * float(np.median(median_margin))

    scenario_profit = [defaultdict(float) for _ in scenarios]
    scenario_count = len(scenarios)
    for slot in slots:
        plot, land_type, year, season, crop = slot
        x = x_index[slot]
        y = y_index[slot]
        values = detail[(crop, land_type, season)]
        integrality[y] = 1
        upper[y] = 1
        objective[y] += fragmentation_penalty
        for scenario_no, scenario in enumerate(scenarios):
            yield_value = values["yield"] * scenario_value(scenario, "yield", crop, year)
            cost_value = values["cost"] * scenario_value(scenario, "cost", crop, year)
            price_value = crop_price[crop] * scenario_value(scenario, "price", crop, year)
            profit_coefficient = surplus_fraction * price_value * yield_value - cost_value
            scenario_profit[scenario_no][x] += profit_coefficient
            objective[x] += -profit_coefficient / scenario_count
            objective[x] += waste_weight * price_value * yield_value / scenario_count
    for index in water_mode.values():
        integrality[index] = 1
        upper[index] = 1
    for (scenario_no, crop, year, season), index in sold_index.items():
        scenario = scenarios[scenario_no]
        price_value = crop_price[crop] * scenario_value(scenario, "price", crop, year)
        revenue_coefficient = (1 - surplus_fraction) * price_value
        scenario_profit[scenario_no][index] += revenue_coefficient
        objective[index] += -revenue_coefficient / scenario_count
        objective[index] += -waste_weight * price_value / scenario_count
    if eta_index is not None:
        objective[eta_index] = risk_weight
        for index in xi_index.values():
            objective[index] = risk_weight / ((1 - alpha) * scenario_count)

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

    committed_sets = _committed_crop_sets(committed)
    first_year = min(years)
    for row in land.itertuples(index=False):
        plot, land_type = row.plot_id, row.land_type
        if land_type in DRY_TYPES:
            for crop in DRY_CROPS:
                previous = planted_2023[(plot, "单季")] if first_year == 2024 else committed_sets[(plot, first_year - 1, "单季")]
                if crop in previous:
                    constraints.add({y_index[(plot, land_type, first_year, "单季", crop)]: 1}, upper=0)
                for y1, y2 in zip(years[:-1], years[1:]):
                    constraints.add({y_index[(plot, land_type, y1, "单季", crop)]: 1,
                                     y_index[(plot, land_type, y2, "单季", crop)]: 1}, upper=1)
        elif land_type == "水浇地":
            previous = planted_2023[(plot, "单季")] if first_year == 2024 else committed_sets[(plot, first_year - 1, "单季")]
            if 16 in previous:
                constraints.add({y_index[(plot, land_type, first_year, "单季", 16)]: 1}, upper=0)
            for y1, y2 in zip(years[:-1], years[1:]):
                constraints.add({y_index[(plot, land_type, y1, "单季", 16)]: 1,
                                 y_index[(plot, land_type, y2, "单季", 16)]: 1}, upper=1)
        elif land_type == "智慧大棚":
            previous = planted_2023[(plot, "第二季")] if first_year == 2024 else committed_sets[(plot, first_year - 1, "第二季")]
            for crop in VEG1:
                if crop in previous:
                    constraints.add({y_index[(plot, land_type, first_year, "第一季", crop)]: 1}, upper=0)
                for year in years:
                    constraints.add({y_index[(plot, land_type, year, "第一季", crop)]: 1,
                                     y_index[(plot, land_type, year, "第二季", crop)]: 1}, upper=1)
                for y1, y2 in zip(years[:-1], years[1:]):
                    constraints.add({y_index[(plot, land_type, y1, "第二季", crop)]: 1,
                                     y_index[(plot, land_type, y2, "第一季", crop)]: 1}, upper=1)

    fixed_bean = defaultdict(float)
    for plot, value in bean_2023.items():
        fixed_bean[(plot, 2023)] += value
    for (plot, _, year, _, crop), value in committed.items():
        if crop in BEANS:
            fixed_bean[(plot, year)] += value
    bean_variables = defaultdict(list)
    for slot in slots:
        plot, _, year, _, crop = slot
        if crop in BEANS:
            bean_variables[(plot, year)].append(x_index[slot])
    maximum_year = max(years)
    for plot, plot_area in area.items():
        for start in range(2023, maximum_year - 1):
            end = start + 2
            if end < first_year or end > maximum_year:
                continue
            coefficients = {}
            fixed = 0.0
            for year in range(start, end + 1):
                fixed += fixed_bean[(plot, year)]
                for index in bean_variables[(plot, year)]:
                    coefficients[index] = -1
            constraints.add(coefficients, upper=-(plot_area - min(fixed, plot_area)))

    production_terms = [defaultdict(dict) for _ in scenarios]
    for slot in slots:
        _, land_type, year, season, crop = slot
        x = x_index[slot]
        values = detail[(crop, land_type, season)]
        for scenario_no, scenario in enumerate(scenarios):
            production_terms[scenario_no][(crop, year, season)][x] = values["yield"] * scenario_value(scenario, "yield", crop, year)
    for (scenario_no, crop, year, season), index in sold_index.items():
        coefficients = {index: 1}
        coefficients.update({column: -value for column, value in production_terms[scenario_no][(crop, year, season)].items()})
        constraints.add(coefficients, upper=0)
        demand_limit = demand.get((crop, season), 0.0) * scenario_value(scenarios[scenario_no], "demand", crop, year)
        constraints.add({index: 1}, upper=demand_limit)

    if eta_index is not None:
        for scenario_no in range(scenario_count):
            coefficients = {column: -value for column, value in scenario_profit[scenario_no].items()}
            coefficients[eta_index] = -1
            coefficients[xi_index[scenario_no]] = -1
            constraints.add(coefficients, upper=0)

    started = time.perf_counter()
    result = milp(
        objective,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=constraints.build(next_variable),
        options={"time_limit": time_limit, "mip_rel_gap": mip_gap, "presolve": True},
    )
    runtime = time.perf_counter() - started
    if result.x is None:
        raise RuntimeError(f"MILP failed for years {years}: {result.message}")
    plan = {slot: max(0.0, float(result.x[index])) for slot, index in x_index.items() if result.x[index] > 1e-7}
    return plan, {
        "years": years,
        "status": "success" if result.success else "time_limit_feasible",
        "solver_status": int(result.status),
        "message": result.message,
        "runtime_seconds": runtime,
        "mip_gap": None if getattr(result, "mip_gap", None) is None else float(result.mip_gap),
        "variables": next_variable,
        "binary_variables": int(integrality.sum()),
        "constraints": len(constraints.rows),
        "objective": float(result.fun),
        "smart_greenhouse_first_season_reused_crop_ids": reused_smart_first,
        "fragmentation_penalty_yuan_per_assignment": fragmentation_penalty,
    }


def rolling_optimize(
    land,
    planting,
    economics,
    scenarios,
    surplus_fraction,
    waste_weight=0.0,
    risk_weight=0.0,
    time_limit=20,
    mip_gap=0.05,
):
    committed = {}
    windows = []
    schedule = [([2024, 2025, 2026], [2024, 2025]), ([2026, 2027, 2028], [2026, 2027]), ([2028, 2029, 2030], [2028, 2029, 2030])]
    for years, commit_years in schedule:
        candidate, metrics = solve_window(
            land, planting, economics, years, committed, scenarios,
            surplus_fraction=surplus_fraction,
            waste_weight=waste_weight,
            risk_weight=risk_weight,
            time_limit=time_limit,
            mip_gap=mip_gap,
        )
        committed.update({slot: value for slot, value in candidate.items() if slot[2] in commit_years})
        metrics["committed_years"] = commit_years
        windows.append(metrics)
    return committed, windows


def greedy_baseline(land, planting, economics):
    detail, crop_price, _ = build_economic_maps(economics)
    _, bean_2023, _ = initial_state(land, planting, detail)
    solution = {}
    previous = {}

    def margin(crop, land_type, season):
        values = detail[(crop, land_type, season)]
        return values["yield"] * crop_price[crop] - values["cost"]

    def best(candidates, land_type, season, excluded=()):
        eligible = [crop for crop in candidates if crop not in set(excluded)]
        return max(eligible, key=lambda crop: margin(crop, land_type, season))

    for row in land.itertuples(index=False):
        plot, land_type, plot_area = row.plot_id, row.land_type, float(row.area_mu)
        planted_bean = bean_2023.get(plot, 0.0) >= plot_area - 1e-9
        bean_years = {2026, 2029} if planted_bean else {2025, 2028}
        for year in ALL_YEARS:
            force_bean = year in bean_years
            if land_type in DRY_TYPES:
                candidates = list(range(1, 6)) if force_bean else list(range(6, 16))
                crop = best(candidates, land_type, "单季", [previous.get(plot)])
                solution[(plot, land_type, year, "单季", crop)] = plot_area
                previous[plot] = crop
            elif land_type == "水浇地":
                if force_bean or previous.get(plot) == 16:
                    first = best(list(range(17, 20)) if force_bean else VEG1, land_type, "第一季", [previous.get(plot)])
                    second = best(VEG2, land_type, "第二季", [first])
                    solution[(plot, land_type, year, "第一季", first)] = plot_area
                    solution[(plot, land_type, year, "第二季", second)] = plot_area
                    previous[plot] = second
                else:
                    rice_margin = margin(16, land_type, "单季")
                    first = best(VEG1, land_type, "第一季", [previous.get(plot)])
                    second = best(VEG2, land_type, "第二季", [first])
                    if rice_margin >= margin(first, land_type, "第一季") + margin(second, land_type, "第二季"):
                        solution[(plot, land_type, year, "单季", 16)] = plot_area
                        previous[plot] = 16
                    else:
                        solution[(plot, land_type, year, "第一季", first)] = plot_area
                        solution[(plot, land_type, year, "第二季", second)] = plot_area
                        previous[plot] = second
            elif land_type == "普通大棚":
                first = best(list(range(17, 20)) if force_bean else VEG1, land_type, "第一季", [previous.get(plot)])
                second = best(MUSHROOMS, land_type, "第二季", [first])
                solution[(plot, land_type, year, "第一季", first)] = plot_area
                solution[(plot, land_type, year, "第二季", second)] = plot_area
                previous[plot] = second
            elif land_type == "智慧大棚":
                first = best(list(range(17, 20)) if force_bean else VEG1, land_type, "第一季", [previous.get(plot)])
                second = best(VEG1, land_type, "第二季", [first])
                solution[(plot, land_type, year, "第一季", first)] = plot_area
                solution[(plot, land_type, year, "第二季", second)] = plot_area
                previous[plot] = second
    return solution


def evaluate_plan(plan, land, planting, economics, scenarios, surplus_fraction):
    detail, crop_price, _ = build_economic_maps(economics)
    demand, _, _ = initial_state(land, planting, detail)
    rows = []
    for scenario_no, scenario in enumerate(scenarios):
        production = defaultdict(float)
        costs = defaultdict(float)
        area_by_crop = defaultdict(float)
        for (_, land_type, year, season, crop), planted_area in plan.items():
            values = detail[(crop, land_type, season)]
            production[(crop, year, season)] += planted_area * values["yield"] * scenario_value(scenario, "yield", crop, year)
            costs[year] += planted_area * values["cost"] * scenario_value(scenario, "cost", crop, year)
            area_by_crop[crop] += planted_area
        revenue = defaultdict(float)
        waste = defaultdict(float)
        total_production = defaultdict(float)
        for (crop, year, season), quantity in production.items():
            expected = demand.get((crop, season), 0.0) * scenario_value(scenario, "demand", crop, year)
            normal = min(quantity, expected)
            excess = max(0.0, quantity - expected)
            price = crop_price[crop] * scenario_value(scenario, "price", crop, year)
            revenue[year] += price * normal + surplus_fraction * price * excess
            waste[year] += excess
            total_production[year] += quantity
        for year in ALL_YEARS:
            rows.append({
                "scenario": scenario_no,
                "year": year,
                "revenue_yuan": revenue[year],
                "cost_yuan": costs[year],
                "profit_yuan": revenue[year] - costs[year],
                "excess_jin": waste[year],
                "production_jin": total_production[year],
                "excess_rate": waste[year] / max(total_production[year], 1e-9),
            })
    return pd.DataFrame(rows)


def validate_plan(plan, land, planting):
    area = dict(zip(land.plot_id, land.area_mu.astype(float)))
    errors = []
    by_capacity = defaultdict(float)
    crop_periods = defaultdict(set)
    bean_area = defaultdict(float)
    for (plot, land_type, year, season, crop), value in plan.items():
        if (season, crop) not in legal_pairs(land_type):
            errors.append({"type": "suitability", "plot": plot, "year": year, "season": season, "crop": crop})
        by_capacity[(plot, year, season)] += value
        crop_periods[(plot, year, season)].add(crop)
        if crop in BEANS:
            bean_area[(plot, year)] += value
    for (plot, year, season), value in by_capacity.items():
        if value > area[plot] + 1e-6:
            errors.append({"type": "capacity", "plot": plot, "year": year, "season": season, "value": value, "limit": area[plot]})
    for plot, land_type in zip(land.plot_id, land.land_type):
        if land_type in DRY_TYPES:
            for year in ALL_YEARS[:-1]:
                repeat = crop_periods[(plot, year, "单季")] & crop_periods[(plot, year + 1, "单季")]
                if repeat:
                    errors.append({"type": "rotation", "plot": plot, "period": [year, year + 1], "crops": sorted(repeat)})
        elif land_type == "水浇地":
            for year in ALL_YEARS:
                if crop_periods[(plot, year, "单季")] and (crop_periods[(plot, year, "第一季")] or crop_periods[(plot, year, "第二季")]):
                    errors.append({"type": "water_mode", "plot": plot, "year": year})
            for year in ALL_YEARS[:-1]:
                repeat = crop_periods[(plot, year, "单季")] & crop_periods[(plot, year + 1, "单季")]
                if repeat:
                    errors.append({"type": "rotation", "plot": plot, "period": [year, year + 1], "crops": sorted(repeat)})
        elif land_type == "智慧大棚":
            for year in ALL_YEARS:
                repeat = crop_periods[(plot, year, "第一季")] & crop_periods[(plot, year, "第二季")]
                if repeat:
                    errors.append({"type": "rotation", "plot": plot, "period": [year, "within"], "crops": sorted(repeat)})
            for year in ALL_YEARS[:-1]:
                repeat = crop_periods[(plot, year, "第二季")] & crop_periods[(plot, year + 1, "第一季")]
                if repeat:
                    errors.append({"type": "rotation", "plot": plot, "period": [year, year + 1], "crops": sorted(repeat)})
    bean_2023 = defaultdict(float)
    for row in planting.itertuples(index=False):
        if int(row.crop_id) in BEANS:
            bean_2023[row.plot_id] += float(row.area_mu)
    for plot, plot_area in area.items():
        for start in range(2023, 2029):
            total = bean_2023[plot] if start == 2023 else 0.0
            total += sum(bean_area[(plot, year)] for year in range(max(start, 2024), min(start + 2, 2030) + 1))
            if total + 1e-6 < plot_area:
                errors.append({"type": "bean_window", "plot": plot, "start": start, "value": total, "required": plot_area})
    return errors


def plan_dataframe(plan, land, crops):
    crop_lookup = crops.set_index("crop_id")[["crop_name", "crop_type"]].to_dict("index")
    area_lookup = dict(zip(land.plot_id, land.area_mu.astype(float)))
    rows = []
    for (plot, land_type, year, season, crop), area in sorted(plan.items(), key=lambda item: (item[0][2], item[0][0], SEASON_ORDER[item[0][3]], item[0][4])):
        rows.append({
            "year": year,
            "plot_id": plot,
            "land_type": land_type,
            "plot_area_mu": area_lookup[plot],
            "season": season,
            "crop_id": crop,
            "crop_name": crop_lookup[crop]["crop_name"],
            "crop_type": crop_lookup[crop]["crop_type"],
            "planted_area_mu": area,
        })
    return pd.DataFrame(rows)


def concentration_metrics(plan):
    by_crop = defaultdict(float)
    positives = []
    for (_, _, _, _, crop), area in plan.items():
        by_crop[crop] += area
        positives.append(area)
    total = sum(by_crop.values())
    shares = sorted((value / total for value in by_crop.values()), reverse=True) if total else []
    return {
        "unique_crops": len(by_crop),
        "top1_area_mass": shares[0] if shares else 0.0,
        "top5_area_mass": sum(shares[:5]),
        "assignment_count": len(positives),
        "minimum_positive_area_mu": min(positives) if positives else 0.0,
    }


def profit_distribution(evaluation):
    totals = evaluation.groupby("scenario", as_index=False).agg(
        profit_yuan=("profit_yuan", "sum"),
        excess_jin=("excess_jin", "sum"),
        production_jin=("production_jin", "sum"),
    )
    profits = totals.profit_yuan.to_numpy()
    threshold = np.quantile(profits, 0.10)
    return {
        "mean_profit_yuan": float(np.mean(profits)),
        "std_profit_yuan": float(np.std(profits, ddof=1)) if len(profits) > 1 else 0.0,
        "p05_profit_yuan": float(np.quantile(profits, 0.05)),
        "median_profit_yuan": float(np.quantile(profits, 0.50)),
        "p95_profit_yuan": float(np.quantile(profits, 0.95)),
        "lower_10pct_mean_profit_yuan": float(np.mean(profits[profits <= threshold])),
        "mean_excess_jin": float(totals.excess_jin.mean()),
        "mean_excess_rate": float(totals.excess_jin.sum() / max(totals.production_jin.sum(), 1e-9)),
    }


def plan_overlap(first, second):
    keys = set(first) | set(second)
    numerator = sum(min(first.get(key, 0.0), second.get(key, 0.0)) for key in keys)
    denominator = sum(max(first.get(key, 0.0), second.get(key, 0.0)) for key in keys)
    return numerator / denominator if denominator else 1.0


def environment_record():
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
    }


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_plan(path, plan, land, crops):
    path.parent.mkdir(parents=True, exist_ok=True)
    plan_dataframe(plan, land, crops).to_csv(path, index=False, encoding="utf-8-sig")


def load_plan(path, land):
    frame = pd.read_csv(path)
    land_type = dict(zip(land.plot_id, land.land_type))
    return {
        (row.plot_id, land_type[row.plot_id], int(row.year), row.season, int(row.crop_id)): float(row.planted_area_mu)
        for row in frame.itertuples(index=False)
    }
