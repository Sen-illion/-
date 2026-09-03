"""Lightweight Q1 method probe; not production optimization code.

Uses a deterministic, land-type-covering plot sample and a three-year rolling
look-ahead. It tests the profit/waste epsilon-constraint design and the
relative minimum-area constraint requested by the human modeler.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "workspace" / "data_clean"
OUTPUT = Path(__file__).with_name("q1_tradeoff_probe_results.json")
YEARS = list(range(2024, 2031))
BEAN_CROPS = {1, 2, 3, 4, 5, 17, 18, 19}
DRY_TYPES = {"平旱地", "梯田", "山坡地"}
EPSILON_YUAN = 1.0
TIME_LIMIT_SECONDS = 8.0
WASTE_TIME_LIMIT_SECONDS = 30.0
MIP_REL_GAP = 0.02
TOL = 1e-6


@dataclass
class ModelData:
    c_profit_min: np.ndarray
    c_waste_min: np.ndarray
    profit_coeff: np.ndarray
    waste_coeff: np.ndarray
    integrality: np.ndarray
    bounds: Bounds
    constraint: LinearConstraint
    x_index: dict[tuple[str, int, str, int], int]
    combo_meta: dict[tuple[str, int, str, int], dict[str, float | str | int]]
    year_start: int
    year_end: int
    constraint_count: int


class Builder:
    def __init__(self) -> None:
        self.lb: list[float] = []
        self.ub: list[float] = []
        self.integrality: list[int] = []
        self.profit: list[float] = []
        self.waste: list[float] = []
        self.rows: list[dict[int, float]] = []
        self.row_lb: list[float] = []
        self.row_ub: list[float] = []

    def var(
        self,
        lower: float,
        upper: float,
        integer: int = 0,
        profit: float = 0.0,
        waste: float = 0.0,
    ) -> int:
        idx = len(self.lb)
        self.lb.append(lower)
        self.ub.append(upper)
        self.integrality.append(integer)
        self.profit.append(profit)
        self.waste.append(waste)
        return idx

    def con(self, coeffs: dict[int, float], lower: float = -np.inf, upper: float = np.inf) -> None:
        self.rows.append({idx: value for idx, value in coeffs.items() if abs(value) > 0})
        self.row_lb.append(lower)
        self.row_ub.append(upper)

    def arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, Bounds, LinearConstraint]:
        rr: list[int] = []
        cc: list[int] = []
        vv: list[float] = []
        for row_id, row in enumerate(self.rows):
            for col_id, value in row.items():
                rr.append(row_id)
                cc.append(col_id)
                vv.append(value)
        matrix = coo_matrix((vv, (rr, cc)), shape=(len(self.rows), len(self.lb))).tocsr()
        return (
            np.asarray(self.profit, dtype=float),
            np.asarray(self.waste, dtype=float),
            np.asarray(self.integrality, dtype=int),
            Bounds(np.asarray(self.lb, dtype=float), np.asarray(self.ub, dtype=float)),
            LinearConstraint(matrix, np.asarray(self.row_lb), np.asarray(self.row_ub)),
        )


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    land = pd.read_csv(DATA / "land.csv")
    crops = pd.read_csv(DATA / "crops.csv")
    planting = pd.read_csv(DATA / "planting_2023.csv")
    economics = pd.read_csv(DATA / "economics_2023.csv")
    return land, crops, planting, economics


def representative_plots(land: pd.DataFrame) -> pd.DataFrame:
    selected: list[pd.DataFrame] = []
    for _, group in land.groupby("land_type", sort=True):
        group = group.sort_values(["area_mu", "plot_id"]).reset_index(drop=True)
        selected.append(group.iloc[[len(group) // 2]])
    return pd.concat(selected, ignore_index=True).sort_values("plot_id").reset_index(drop=True)


def annual_slot_capacity(land: pd.DataFrame) -> float:
    multiplier = land["land_type"].map(
        lambda value: 1.0 if value in DRY_TYPES else 2.0
    )
    return float((land["area_mu"] * multiplier).sum())


def crop_slots(land_type: str) -> list[tuple[str, list[int], str, str]]:
    if land_type in DRY_TYPES:
        return [("单季", list(range(1, 16)), land_type, "单季")]
    if land_type == "水浇地":
        return [
            ("单季", [16], "水浇地", "单季"),
            ("第一季", list(range(17, 35)), "水浇地", "第一季"),
            ("第二季", list(range(35, 38)), "水浇地", "第二季"),
        ]
    if land_type == "普通大棚":
        return [
            ("第一季", list(range(17, 35)), "普通大棚", "第一季"),
            ("第二季", list(range(38, 42)), "普通大棚", "第二季"),
        ]
    if land_type == "智慧大棚":
        return [
            ("第一季", list(range(17, 35)), "普通大棚", "第一季"),
            ("第二季", list(range(17, 35)), "智慧大棚", "第二季"),
        ]
    raise ValueError(f"Unknown land type: {land_type}")


def economics_map(economics: pd.DataFrame) -> dict[tuple[int, str, str], dict[str, float]]:
    result: dict[tuple[int, str, str], dict[str, float]] = {}
    for row in economics.itertuples(index=False):
        result[(int(row.crop_id), row.land_type, row.season)] = {
            "yield": float(row.yield_jin_per_mu),
            "cost": float(row.cost_yuan_per_mu),
            "price": (float(row.price_low_yuan_per_jin) + float(row.price_high_yuan_per_jin)) / 2.0,
        }
    return result


def planting_with_land(planting: pd.DataFrame, land: pd.DataFrame) -> pd.DataFrame:
    # Keep Attachment 2's planted area as ``area_mu``; retain the plot capacity
    # separately so pandas does not silently rename both columns to _x/_y.
    return planting.merge(
        land[["plot_id", "land_type", "area_mu"]].rename(columns={"area_mu": "plot_area_mu"}),
        on="plot_id",
        validate="many_to_one",
    )


def econ_key_for_observed(crop_id: int, land_type: str, season: str) -> tuple[int, str, str]:
    if land_type == "智慧大棚" and season == "第一季":
        return crop_id, "普通大棚", "第一季"
    return crop_id, land_type, season


def expected_sales(
    planting_land: pd.DataFrame,
    econ: dict[tuple[int, str, str], dict[str, float]],
    scale: float,
) -> dict[int, float]:
    totals = {crop_id: 0.0 for crop_id in range(1, 42)}
    for row in planting_land.itertuples(index=False):
        key = econ_key_for_observed(int(row.crop_id), row.land_type, row.season)
        totals[int(row.crop_id)] += float(row.area_mu) * econ[key]["yield"]
    return {crop_id: value * scale for crop_id, value in totals.items()}


def initial_history(planting_land: pd.DataFrame, sample_ids: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in planting_land.itertuples(index=False):
        if row.plot_id in sample_ids:
            rows.append(
                {
                    "plot_id": row.plot_id,
                    "year": 2023,
                    "slot": row.season,
                    "crop_id": int(row.crop_id),
                    "area": float(row.area_mu),
                }
            )
    return rows


def add_coeff(target: dict[int, float], idx: int, value: float) -> None:
    target[idx] = target.get(idx, 0.0) + value


def build_model(
    plots: pd.DataFrame,
    econ: dict[tuple[int, str, str], dict[str, float]],
    demand: dict[int, float],
    history: list[dict[str, Any]],
    year_start: int,
    year_end: int,
    alpha: float,
    profit_floor: float | None = None,
) -> ModelData:
    builder = Builder()
    x_index: dict[tuple[str, int, str, int], int] = {}
    y_index: dict[tuple[str, int, str, int], int] = {}
    u_index: dict[tuple[str, int, str, int], int] = {}
    mode_index: dict[tuple[str, int], int] = {}
    combo_meta: dict[tuple[str, int, str, int], dict[str, float | str | int]] = {}

    plot_rows = {row.plot_id: row for row in plots.itertuples(index=False)}
    for year in range(year_start, year_end + 1):
        for plot in plots.itertuples(index=False):
            if plot.land_type == "水浇地":
                mode_index[(plot.plot_id, year)] = builder.var(0.0, 1.0, integer=1)
            for slot, crop_ids, econ_land, econ_season in crop_slots(plot.land_type):
                for crop_id in crop_ids:
                    key = (plot.plot_id, year, slot, crop_id)
                    params = econ[(crop_id, econ_land, econ_season)]
                    x_idx = builder.var(
                        0.0,
                        float(plot.area_mu),
                        profit=-params["cost"],
                        waste=params["yield"],
                    )
                    y_idx = builder.var(0.0, 1.0, integer=1, profit=-EPSILON_YUAN)
                    u_idx = builder.var(
                        0.0,
                        float(plot.area_mu) * params["yield"],
                        profit=params["price"],
                        waste=-1.0,
                    )
                    x_index[key] = x_idx
                    y_index[key] = y_idx
                    u_index[key] = u_idx
                    combo_meta[key] = {
                        "land_type": plot.land_type,
                        "area_mu": float(plot.area_mu),
                        "yield": params["yield"],
                        "cost": params["cost"],
                        "price": params["price"],
                    }
                    builder.con({x_idx: 1.0, y_idx: -float(plot.area_mu)}, upper=0.0)
                    builder.con({x_idx: -1.0, y_idx: alpha * float(plot.area_mu)}, upper=0.0)
                    builder.con({u_idx: 1.0, x_idx: -params["yield"]}, upper=0.0)

    # Plot capacity and irrigated-mode exclusivity.
    for year in range(year_start, year_end + 1):
        for plot in plots.itertuples(index=False):
            slot_rows: dict[str, dict[int, float]] = {}
            for key, idx in x_index.items():
                plot_id, key_year, slot, _ = key
                if plot_id == plot.plot_id and key_year == year:
                    slot_rows.setdefault(slot, {})[idx] = 1.0
            if plot.land_type == "水浇地":
                mode = mode_index[(plot.plot_id, year)]
                rice = dict(slot_rows["单季"])
                add_coeff(rice, mode, -float(plot.area_mu))
                builder.con(rice, upper=0.0)
                for slot in ("第一季", "第二季"):
                    row = dict(slot_rows[slot])
                    add_coeff(row, mode, float(plot.area_mu))
                    builder.con(row, upper=float(plot.area_mu))
            else:
                for row in slot_rows.values():
                    builder.con(row, upper=float(plot.area_mu))

    # Annual crop sales cap, with normal-price units allocated to the highest-value origins.
    for year in range(year_start, year_end + 1):
        for crop_id in range(1, 42):
            row = {
                idx: 1.0
                for (plot_id, key_year, slot, crop), idx in u_index.items()
                if key_year == year and crop == crop_id
            }
            if row:
                builder.con(row, upper=float(demand[crop_id]))

    # Conservative year-adjacency rotation, plus within-year smart-greenhouse adjacency.
    history_active = {
        (item["plot_id"], int(item["year"]), int(item["crop_id"]))
        for item in history
        if float(item["area"]) > TOL
    }
    for plot in plots.itertuples(index=False):
        for crop_id in range(1, 42):
            first_row = {
                idx: 1.0
                for (plot_id, year, slot, crop), idx in y_index.items()
                if plot_id == plot.plot_id and year == year_start and crop == crop_id
            }
            if (plot.plot_id, year_start - 1, crop_id) in history_active and first_row:
                builder.con(first_row, upper=0.0)
            for year in range(year_start, year_end):
                row = {
                    idx: 1.0
                    for (plot_id, key_year, slot, crop), idx in y_index.items()
                    if plot_id == plot.plot_id and crop == crop_id and key_year in {year, year + 1}
                }
                if row:
                    builder.con(row, upper=1.0)
            if plot.land_type == "智慧大棚":
                for year in range(year_start, year_end + 1):
                    row = {
                        idx: 1.0
                        for (plot_id, key_year, slot, crop), idx in y_index.items()
                        if plot_id == plot.plot_id and key_year == year and crop == crop_id
                    }
                    if row:
                        builder.con(row, upper=1.0)

    # Three-year cumulative bean-area coverage, including observed/committed history.
    for plot in plots.itertuples(index=False):
        for end_year in range(max(2025, year_start), year_end + 1):
            start_year = end_year - 2
            fixed_area = sum(
                float(item["area"])
                for item in history
                if item["plot_id"] == plot.plot_id
                and start_year <= int(item["year"]) <= end_year
                and int(item["crop_id"]) in BEAN_CROPS
            )
            row = {
                idx: 1.0
                for (plot_id, year, slot, crop), idx in x_index.items()
                if plot_id == plot.plot_id
                and start_year <= year <= end_year
                and crop in BEAN_CROPS
            }
            builder.con(row, lower=max(0.0, float(plot.area_mu) - fixed_area))

    profit_coeff, waste_coeff, integrality, bounds, constraint = builder.arrays()
    if profit_floor is not None:
        builder.con(
            {idx: -value for idx, value in enumerate(profit_coeff) if abs(value) > 0},
            upper=-float(profit_floor),
        )
        profit_coeff, waste_coeff, integrality, bounds, constraint = builder.arrays()

    c_profit_min = -profit_coeff
    c_waste_min = waste_coeff.copy()
    for idx, integer in enumerate(integrality):
        if integer == 1:
            c_waste_min[idx] += 1e-3
    return ModelData(
        c_profit_min=c_profit_min,
        c_waste_min=c_waste_min,
        profit_coeff=profit_coeff,
        waste_coeff=waste_coeff,
        integrality=integrality,
        bounds=bounds,
        constraint=constraint,
        x_index=x_index,
        combo_meta=combo_meta,
        year_start=year_start,
        year_end=year_end,
        constraint_count=len(constraint.lb),
    )


def solve_model(model: ModelData, objective: str) -> tuple[Any, float]:
    c = model.c_profit_min if objective == "profit" else model.c_waste_min
    time_limit = TIME_LIMIT_SECONDS if objective == "profit" else WASTE_TIME_LIMIT_SECONDS
    started = time.perf_counter()
    result = milp(
        c=c,
        integrality=model.integrality,
        bounds=model.bounds,
        constraints=model.constraint,
        options={
            "time_limit": time_limit,
            "mip_rel_gap": MIP_REL_GAP,
            "presolve": True,
        },
    )
    elapsed = time.perf_counter() - started
    if result.x is None:
        raise RuntimeError(f"MILP returned no incumbent: {result.message}")
    return result, elapsed


def solution_summary(model: ModelData, result: Any, elapsed: float, stage: str) -> dict[str, Any]:
    adjusted_profit = float(model.profit_coeff @ result.x)
    waste = max(0.0, float(model.waste_coeff @ result.x))
    return {
        "stage": stage,
        "years": [model.year_start, model.year_end],
        "status": int(result.status),
        "message": str(result.message),
        "runtime_seconds": round(elapsed, 6),
        "mip_gap": None if getattr(result, "mip_gap", None) is None else float(result.mip_gap),
        "mip_node_count": None
        if getattr(result, "mip_node_count", None) is None
        else int(result.mip_node_count),
        "adjusted_profit_yuan": adjusted_profit,
        "waste_jin": waste,
        "variables": len(result.x),
        "binary_variables": int(model.integrality.sum()),
        "constraints": model.constraint_count,
    }


def committed_rows(model: ModelData, result: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, idx in model.x_index.items():
        plot_id, year, slot, crop_id = key
        area = float(result.x[idx])
        if year == model.year_start and area > 1e-5:
            meta = model.combo_meta[key]
            rows.append(
                {
                    "plot_id": plot_id,
                    "year": year,
                    "slot": slot,
                    "crop_id": crop_id,
                    "area": area,
                    "land_type": meta["land_type"],
                    "plot_area": meta["area_mu"],
                    "yield": meta["yield"],
                    "cost": meta["cost"],
                    "price": meta["price"],
                }
            )
    return rows


def evaluate_plan(plan: list[dict[str, Any]], demand: dict[int, float]) -> dict[str, float | int]:
    total_production = 0.0
    total_waste = 0.0
    total_revenue = 0.0
    total_cost = 0.0
    for row in plan:
        total_cost += row["area"] * row["cost"]
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in plan:
        grouped.setdefault((row["year"], row["crop_id"]), []).append(row)
    for (_, crop_id), rows in grouped.items():
        remaining = demand[crop_id]
        for row in sorted(rows, key=lambda item: item["price"], reverse=True):
            production = row["area"] * row["yield"]
            sold = min(production, remaining)
            remaining -= sold
            total_production += production
            total_waste += production - sold
            total_revenue += sold * row["price"]
    crop_area: dict[int, float] = {}
    for row in plan:
        crop_area[row["crop_id"]] = crop_area.get(row["crop_id"], 0.0) + row["area"]
    areas = sorted(crop_area.values(), reverse=True)
    total_area = sum(areas)
    activation_count = len(plan)
    return {
        "profit_yuan": total_revenue - total_cost,
        "production_jin": total_production,
        "waste_jin": total_waste,
        "waste_rate": 0.0 if total_production <= 0 else total_waste / total_production,
        "activation_count": activation_count,
        "average_area_per_activation_mu": 0.0
        if activation_count == 0
        else total_area / activation_count,
        "top5_area_mass": 0.0 if total_area <= 0 else sum(areas[:5]) / total_area,
        "unique_crop_count": len(crop_area),
        "total_planted_area_mu": total_area,
    }


def validate_plan(
    plan: list[dict[str, Any]],
    history_2023: list[dict[str, Any]],
    plots: pd.DataFrame,
    alpha: float,
) -> dict[str, Any]:
    violations: list[str] = []
    plot_info = {row.plot_id: row for row in plots.itertuples(index=False)}
    by_slot: dict[tuple[str, int, str], float] = {}
    active: dict[tuple[str, int], set[int]] = {}
    smart_slots: dict[tuple[str, int, int], set[str]] = {}
    for row in plan:
        key = (row["plot_id"], row["year"], row["slot"])
        by_slot[key] = by_slot.get(key, 0.0) + row["area"]
        active.setdefault((row["plot_id"], row["year"]), set()).add(row["crop_id"])
        if row["area"] + 1e-5 < alpha * row["plot_area"]:
            violations.append(f"minimum-area:{row['plot_id']}:{row['year']}:{row['slot']}:{row['crop_id']}")
        if row["land_type"] == "智慧大棚":
            smart_slots.setdefault((row["plot_id"], row["year"], row["crop_id"]), set()).add(row["slot"])
    for (plot_id, year, slot), area in by_slot.items():
        if area > float(plot_info[plot_id].area_mu) + 1e-5:
            violations.append(f"capacity:{plot_id}:{year}:{slot}")
    for plot in plots.itertuples(index=False):
        if plot.land_type == "水浇地":
            for year in YEARS:
                rice = by_slot.get((plot.plot_id, year, "单季"), 0.0)
                vegetables = by_slot.get((plot.plot_id, year, "第一季"), 0.0) + by_slot.get(
                    (plot.plot_id, year, "第二季"), 0.0
                )
                if rice > TOL and vegetables > TOL:
                    violations.append(f"irrigated-mode:{plot.plot_id}:{year}")
    for plot in plots.itertuples(index=False):
        previous = {
            item["crop_id"]
            for item in history_2023
            if item["plot_id"] == plot.plot_id and item["area"] > TOL
        }
        for year in YEARS:
            current = active.get((plot.plot_id, year), set())
            for crop_id in previous & current:
                violations.append(f"rotation:{plot.plot_id}:{year}:{crop_id}")
            previous = current
    for (plot_id, year, crop_id), slots in smart_slots.items():
        if len(slots) > 1:
            violations.append(f"smart-within-year-rotation:{plot_id}:{year}:{crop_id}")
    all_rows = history_2023 + plan
    for plot in plots.itertuples(index=False):
        for end_year in range(2025, 2031):
            bean_area = sum(
                float(item["area"])
                for item in all_rows
                if item["plot_id"] == plot.plot_id
                and end_year - 2 <= int(item["year"]) <= end_year
                and int(item["crop_id"]) in BEAN_CROPS
            )
            if bean_area + 1e-5 < float(plot.area_mu):
                violations.append(f"bean-area-coverage:{plot.plot_id}:{end_year}")
    return {"violation_count": len(violations), "violations": violations[:50]}


def run_policy(
    plots: pd.DataFrame,
    econ: dict[tuple[int, str, str], dict[str, float]],
    demand: dict[int, float],
    history_2023: list[dict[str, Any]],
    alpha: float,
    eta: float | None,
) -> dict[str, Any]:
    history = [dict(item) for item in history_2023]
    plan: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
    for start in YEARS:
        end = min(2030, start + 2)
        pure_model = build_model(plots, econ, demand, history, start, end, alpha)
        pure_result, pure_elapsed = solve_model(pure_model, "profit")
        pure_summary = solution_summary(pure_model, pure_result, pure_elapsed, "pure_profit")
        chosen_model = pure_model
        chosen_result = pure_result
        window_record: dict[str, Any] = {"pure_profit": pure_summary}
        if eta is not None:
            pi_star = pure_summary["adjusted_profit_yuan"]
            # Numerical-only slack: Pi* is an incumbent from a gap-limited MILP,
            # so enforcing its floating-point value exactly can make eta=0
            # artificially infeasible after rebuilding the same model.
            numeric_slack = max(1e-4, abs(pi_star) * 1e-9)
            floor = (1.0 - eta) * pi_star - numeric_slack
            pareto_model = build_model(plots, econ, demand, history, start, end, alpha, profit_floor=floor)
            pareto_result, pareto_elapsed = solve_model(pareto_model, "waste")
            pareto_summary = solution_summary(pareto_model, pareto_result, pareto_elapsed, "minimum_waste")
            pareto_summary["profit_floor_yuan"] = floor
            pareto_summary["eta"] = eta
            window_record["pareto"] = pareto_summary
            chosen_model = pareto_model
            chosen_result = pareto_result
        committed = committed_rows(chosen_model, chosen_result)
        if not committed:
            raise RuntimeError(f"No committed decisions for year {start}")
        plan.extend(committed)
        history.extend(committed)
        window_record["committed_year"] = start
        window_record["committed_activations"] = len(committed)
        windows.append(window_record)
    metrics = evaluate_plan(plan, demand)
    validation = validate_plan(plan, history_2023, plots, alpha)
    return {
        "alpha": alpha,
        "eta": eta,
        "policy": "zero_price_pure_profit" if eta is None else "profit_floor_then_minimum_waste",
        "metrics": metrics,
        "validation": validation,
        "windows": windows,
    }


def geometric_knee(eta_results: list[dict[str, Any]]) -> float:
    ordered = sorted(eta_results, key=lambda item: item["eta"])
    profits = np.array([item["metrics"]["profit_yuan"] for item in ordered], dtype=float)
    wastes = np.array([item["metrics"]["waste_jin"] for item in ordered], dtype=float)
    profit_loss = (profits.max() - profits) / max(abs(profits.max()), 1.0)
    waste_reduction = (wastes.max() - wastes) / max(wastes.max() - wastes.min(), 1.0)
    x = profit_loss
    y = waste_reduction
    start = np.array([x[0], y[0]])
    end = np.array([x[-1], y[-1]])
    line = end - start
    denom = np.linalg.norm(line)
    if denom <= 1e-12:
        return float(ordered[0]["eta"])
    distances = [
        abs(line[0] * (yy - start[1]) - line[1] * (xx - start[0])) / denom
        for xx, yy in zip(x, y)
    ]
    return float(ordered[int(np.argmax(distances))]["eta"])


def choose_alpha(alpha_results: list[dict[str, Any]]) -> float:
    ordered = sorted(alpha_results, key=lambda item: item["alpha"])
    chosen = ordered[0]
    for candidate in ordered[1:]:
        prior_activations = chosen["metrics"]["activation_count"]
        activation_reduction = (prior_activations - candidate["metrics"]["activation_count"]) / max(
            prior_activations, 1
        )
        incremental_loss = (
            chosen["metrics"]["profit_yuan"] - candidate["metrics"]["profit_yuan"]
        ) / max(abs(chosen["metrics"]["profit_yuan"]), 1.0)
        if (
            candidate["validation"]["violation_count"] == 0
            and activation_reduction >= 0.10
            and incremental_loss <= 0.01
        ):
            chosen = candidate
    return float(chosen["alpha"])


def annotate_losses(results: list[dict[str, Any]], reference_profit: float) -> None:
    for item in results:
        item["metrics"]["profit_loss_rate_vs_alpha10_pure"] = (
            reference_profit - item["metrics"]["profit_yuan"]
        ) / max(abs(reference_profit), 1.0)


def main() -> None:
    land, crops, planting, economics = load_inputs()
    plots = representative_plots(land)
    econ = economics_map(economics)
    planting_land = planting_with_land(planting, land)
    scale = annual_slot_capacity(plots) / annual_slot_capacity(land)
    demand = expected_sales(planting_land, econ, scale)
    history_2023 = initial_history(planting_land, set(plots["plot_id"]))

    # Predeclared one-factor probes.
    alpha_results = [run_policy(plots, econ, demand, history_2023, alpha, None) for alpha in (0.10, 0.20, 0.30)]
    eta_results = [run_policy(plots, econ, demand, history_2023, 0.10, eta) for eta in (0.00, 0.01, 0.03, 0.05)]
    reference_profit = alpha_results[0]["metrics"]["profit_yuan"]
    annotate_losses(alpha_results, reference_profit)
    annotate_losses(eta_results, reference_profit)

    eta_candidate = geometric_knee(eta_results)
    alpha_candidate = choose_alpha(alpha_results)

    # Small joint validation: candidate pair and immediate grid neighbors only.
    eta_grid = [0.00, 0.01, 0.03, 0.05]
    alpha_grid = [0.10, 0.20, 0.30]
    eta_pos = eta_grid.index(eta_candidate)
    alpha_pos = alpha_grid.index(alpha_candidate)
    joint_pairs = {(eta_candidate, alpha_candidate)}
    if eta_pos > 0:
        joint_pairs.add((eta_grid[eta_pos - 1], alpha_candidate))
    if eta_pos < len(eta_grid) - 1:
        joint_pairs.add((eta_grid[eta_pos + 1], alpha_candidate))
    if alpha_pos > 0:
        joint_pairs.add((eta_candidate, alpha_grid[alpha_pos - 1]))
    if alpha_pos < len(alpha_grid) - 1:
        joint_pairs.add((eta_candidate, alpha_grid[alpha_pos + 1]))
    existing = {(item["eta"], item["alpha"]): item for item in eta_results}
    joint_results: list[dict[str, Any]] = []
    for eta, alpha in sorted(joint_pairs):
        item = existing.get((eta, alpha))
        if item is None:
            item = run_policy(plots, econ, demand, history_2023, alpha, eta)
            annotate_losses([item], reference_profit)
        joint_results.append(item)

    output = {
        "schema_version": 1,
        "question_id": "Q1",
        "probe_type": "pre-code_method_confirmation",
        "generated_at": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
        "not_formal_solution": True,
        "input_paths": [
            "workspace/data_clean/land.csv",
            "workspace/data_clean/crops.csv",
            "workspace/data_clean/planting_2023.csv",
            "workspace/data_clean/economics_2023.csv",
        ],
        "sample": {
            "rule": "per land type select the median-area plot; ties/order resolved by plot_id",
            "scope_reason": "micro-instance adopted after the 18-plot stratified probe produced no eta=0 second-stage incumbent within 30 seconds; preserves all six land types and the 0.6-mu greenhouse scale",
            "plot_count": int(len(plots)),
            "plot_ids": plots["plot_id"].tolist(),
            "land_type_counts": plots.groupby("land_type").size().to_dict(),
            "annual_capacity_scale_vs_full": scale,
            "demand_scaling": "full 2023 crop production proxy multiplied by sample/full annual land-season capacity",
        },
        "formulation": {
            "rolling_policy": "three-year look-ahead; commit first year; final two windows shrink to two and one year",
            "smart_greenhouse_first_season": "ordinary-greenhouse first-season economics",
            "surplus_price": 0.0,
            "pure_profit_objective": "economic profit minus 1 yuan per active crop-plot-season combination",
            "pareto_objective": "minimize waste subject to adjusted profit >= (1-eta)*Pi_star",
            "minimum_area": "x_ijts >= alpha*A_i*y_ijts",
            "bean_rotation": "sum of bean area over each three-year window >= plot area, including 2023 observed area",
            "rotation": "conservative year-adjacency prohibition; smart greenhouse also prohibits same crop in both seasons of one year",
        },
        "solver": {
            "engine": "scipy.optimize.milp (HiGHS)",
            "pure_profit_time_limit_seconds_per_solve": TIME_LIMIT_SECONDS,
            "minimum_waste_time_limit_seconds_per_solve": WASTE_TIME_LIMIT_SECONDS,
            "target_mip_relative_gap": MIP_REL_GAP,
            "profit_floor_numeric_slack": "max(0.0001 yuan, 1e-9 * abs(Pi_star)); solver feasibility only",
        },
        "predeclared_selection_rules": {
            "eta": "geometric knee on normalized final profit-loss and waste-reduction curve; retain interval if knee is unstable in joint checks",
            "alpha": "start at 10%; move upward only if each step reduces activations by at least 10%, adds at most 1% incremental profit loss, and has zero hard-constraint violations",
            "joint": "candidate pair plus immediate eta/alpha grid neighbors only",
        },
        "zero_price_pure_profit_alpha_scan": alpha_results,
        "eta_scan_at_alpha_10_percent": eta_results,
        "preliminary_candidates": {"eta": eta_candidate, "alpha": alpha_candidate},
        "joint_validation": joint_results,
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT),
        "sample_plot_count": len(plots),
        "eta_candidate": eta_candidate,
        "alpha_candidate": alpha_candidate,
        "alpha_metrics": [item["metrics"] for item in alpha_results],
        "eta_metrics": [item["metrics"] for item in eta_results],
        "joint_count": len(joint_results),
        "all_validation_counts": [
            item["validation"]["violation_count"]
            for item in alpha_results + eta_results + joint_results
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
