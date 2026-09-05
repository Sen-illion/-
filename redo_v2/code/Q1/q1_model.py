from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from q1_common import ALPHA, BEAN_CROPS, YEARS, crop_slots, economics_map


EPSILON_ACTIVATION_YUAN = 1.0
EPSILON_WASTE_TIE = 1e-6
TARGET_GAP = 0.05
INITIAL_TIME_LIMIT = 60.0
RETRY_TIME_LIMIT = 180.0


class Builder:
    def __init__(self) -> None:
        self.lb: list[float] = []
        self.ub: list[float] = []
        self.integer: list[int] = []
        self.economic: list[float] = []
        self.half: list[float] = []
        self.waste: list[float] = []
        self.activation: list[float] = []
        self.rows: list[dict[int, float]] = []
        self.row_lb: list[float] = []
        self.row_ub: list[float] = []

    def var(self, lb: float, ub: float, integer: int = 0, economic: float = 0.0,
            half: float = 0.0, waste: float = 0.0, activation: float = 0.0) -> int:
        idx = len(self.lb)
        self.lb.append(lb); self.ub.append(ub); self.integer.append(integer)
        self.economic.append(economic); self.half.append(half)
        self.waste.append(waste); self.activation.append(activation)
        return idx

    def con(self, row: dict[int, float], lb: float = -np.inf, ub: float = np.inf) -> None:
        self.rows.append({i: v for i, v in row.items() if abs(v) > 0})
        self.row_lb.append(lb); self.row_ub.append(ub)

    def arrays(self) -> tuple[np.ndarray, ...]:
        rr: list[int] = []; cc: list[int] = []; vv: list[float] = []
        for r, row in enumerate(self.rows):
            for c, value in row.items():
                rr.append(r); cc.append(c); vv.append(value)
        matrix = coo_matrix((vv, (rr, cc)), shape=(len(self.rows), len(self.lb))).tocsr()
        return (
            np.asarray(self.economic), np.asarray(self.half), np.asarray(self.waste),
            np.asarray(self.activation), np.asarray(self.integer, dtype=int),
            Bounds(np.asarray(self.lb), np.asarray(self.ub)),
            LinearConstraint(matrix, np.asarray(self.row_lb), np.asarray(self.row_ub)),
        )


@dataclass
class Model:
    economic: np.ndarray
    half: np.ndarray
    waste: np.ndarray
    activation: np.ndarray
    integrality: np.ndarray
    bounds: Bounds
    constraints: LinearConstraint
    x_index: dict[tuple[str, int, str, int], int]
    meta: dict[tuple[str, int, str, int], dict[str, Any]]
    year_start: int
    year_end: int


def add(row: dict[int, float], idx: int, value: float) -> None:
    row[idx] = row.get(idx, 0.0) + value


def build_model(land: pd.DataFrame, economics: pd.DataFrame, demand: dict[int, float],
                history: list[dict[str, Any]], start: int, end: int,
                profit_floor: float | None = None) -> Model:
    econ = economics_map(economics)
    b = Builder()
    x_idx: dict[tuple[str, int, str, int], int] = {}
    y_idx: dict[tuple[str, int, str, int], int] = {}
    u_idx: dict[tuple[str, int, str, int], int] = {}
    modes: dict[tuple[str, int], int] = {}
    meta: dict[tuple[str, int, str, int], dict[str, Any]] = {}
    for year in range(start, end + 1):
        for plot in land.itertuples(index=False):
            if plot.land_type == "水浇地":
                modes[(plot.plot_id, year)] = b.var(0, 1, integer=1)
            for slot, crops, econ_land, econ_season in crop_slots(plot.land_type):
                for crop in crops:
                    p = econ[(crop, econ_land, econ_season)]
                    key = (plot.plot_id, year, slot, crop)
                    x = b.var(0, float(plot.area_mu), economic=-p["cost"],
                              half=-p["cost"] + 0.5 * p["price"] * p["yield"], waste=p["yield"])
                    y = b.var(0, 1, integer=1, activation=1.0)
                    u = b.var(0, float(plot.area_mu) * p["yield"], economic=p["price"],
                              half=0.5 * p["price"], waste=-1.0)
                    x_idx[key] = x; y_idx[key] = y; u_idx[key] = u
                    meta[key] = {"land_type": plot.land_type, "yield_jin_per_mu": p["yield"],
                                 "cost_yuan_per_mu": p["cost"], "price_yuan_per_jin": p["price"]}
                    b.con({x: 1, y: -float(plot.area_mu)}, ub=0)
                    b.con({x: -1, y: ALPHA * float(plot.area_mu)}, ub=0)
                    b.con({u: 1, x: -p["yield"]}, ub=0)
    for year in range(start, end + 1):
        for plot in land.itertuples(index=False):
            slots: dict[str, dict[int, float]] = {}
            for (p, y, slot, _), idx in x_idx.items():
                if p == plot.plot_id and y == year:
                    slots.setdefault(slot, {})[idx] = 1.0
            if plot.land_type == "水浇地":
                mode = modes[(plot.plot_id, year)]
                rice = dict(slots["单季"]); add(rice, mode, -float(plot.area_mu)); b.con(rice, ub=0)
                for slot in ("第一季", "第二季"):
                    row = dict(slots[slot]); add(row, mode, float(plot.area_mu)); b.con(row, ub=float(plot.area_mu))
            else:
                for row in slots.values():
                    b.con(row, ub=float(plot.area_mu))
    for year in range(start, end + 1):
        for crop in range(1, 42):
            row = {idx: 1.0 for (_, y, _, c), idx in u_idx.items() if y == year and c == crop}
            if row:
                b.con(row, ub=float(demand[crop]))
    history_active = {
        (r["plot_id"], int(r["year"]), r["slot"], int(r["crop_id"]))
        for r in history if float(r["area"]) > 1e-6
    }
    for plot in land.itertuples(index=False):
        if plot.land_type in {"平旱地", "梯田", "山坡地"}:
            for crop in range(1, 16):
                first = y_idx.get((plot.plot_id, start, "单季", crop))
                if (plot.plot_id, start - 1, "单季", crop) in history_active and first is not None:
                    b.con({first: 1.0}, ub=0)
                for year in range(start, end):
                    left = y_idx.get((plot.plot_id, year, "单季", crop))
                    right = y_idx.get((plot.plot_id, year + 1, "单季", crop))
                    if left is not None and right is not None:
                        b.con({left: 1.0, right: 1.0}, ub=1)
        elif plot.land_type == "水浇地":
            crop = 16
            first = y_idx.get((plot.plot_id, start, "单季", crop))
            if (plot.plot_id, start - 1, "单季", crop) in history_active and first is not None:
                b.con({first: 1.0}, ub=0)
            for year in range(start, end):
                left = y_idx.get((plot.plot_id, year, "单季", crop))
                right = y_idx.get((plot.plot_id, year + 1, "单季", crop))
                if left is not None and right is not None:
                    b.con({left: 1.0, right: 1.0}, ub=1)
        elif plot.land_type == "智慧大棚":
            for crop in range(17, 35):
                first = y_idx.get((plot.plot_id, start, "第一季", crop))
                if (plot.plot_id, start - 1, "第二季", crop) in history_active and first is not None:
                    b.con({first: 1.0}, ub=0)
                for year in range(start, end + 1):
                    season_1 = y_idx.get((plot.plot_id, year, "第一季", crop))
                    season_2 = y_idx.get((plot.plot_id, year, "第二季", crop))
                    if season_1 is not None and season_2 is not None:
                        b.con({season_1: 1.0, season_2: 1.0}, ub=1)
                    if year < end:
                        next_season_1 = y_idx.get((plot.plot_id, year + 1, "第一季", crop))
                        if season_2 is not None and next_season_1 is not None:
                            b.con({season_2: 1.0, next_season_1: 1.0}, ub=1)
    for plot in land.itertuples(index=False):
        for end_year in range(max(2025, start), end + 1):
            window_start = end_year - 2
            fixed = sum(float(r["area"]) for r in history if r["plot_id"] == plot.plot_id
                        and window_start <= int(r["year"]) <= end_year and int(r["crop_id"]) in BEAN_CROPS)
            row = {idx: 1.0 for (p, y, _, crop), idx in x_idx.items()
                   if p == plot.plot_id and window_start <= y <= end_year and crop in BEAN_CROPS}
            b.con(row, lb=max(0.0, float(plot.area_mu) - fixed))
    economic, half, waste, activation, integer, bounds, constraints = b.arrays()
    if profit_floor is not None:
        b.con({i: -v for i, v in enumerate(economic) if abs(v) > 0}, ub=-profit_floor)
        economic, half, waste, activation, integer, bounds, constraints = b.arrays()
    return Model(economic, half, waste, activation, integer, bounds, constraints, x_idx, meta, start, end)


def _attempt(model: Model, kind: str, seconds: float) -> tuple[Any, float]:
    if kind == "pure":
        objective = -(model.economic - EPSILON_ACTIVATION_YUAN * model.activation)
    elif kind == "half":
        objective = -(model.half - EPSILON_ACTIVATION_YUAN * model.activation)
    elif kind == "waste":
        objective = model.waste + EPSILON_WASTE_TIE * model.activation
    else:
        raise ValueError(kind)
    begun = time.perf_counter()
    result = milp(c=objective, integrality=model.integrality, bounds=model.bounds,
                  constraints=model.constraints,
                  options={"time_limit": seconds, "mip_rel_gap": TARGET_GAP, "presolve": True})
    return result, time.perf_counter() - begun


def solve(model: Model, kind: str) -> tuple[Any, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    selected = None
    for seconds in (INITIAL_TIME_LIMIT, RETRY_TIME_LIMIT):
        result, elapsed = _attempt(model, kind, seconds)
        gap = getattr(result, "mip_gap", None)
        attempts.append({"time_limit_seconds": seconds, "runtime_seconds": elapsed, "status": int(result.status),
                         "message": str(result.message), "mip_gap": None if gap is None else float(gap),
                         "mip_node_count": None if getattr(result, "mip_node_count", None) is None else int(result.mip_node_count),
                         "has_incumbent": result.x is not None})
        if result.x is not None:
            selected = result
        if result.x is not None and (gap is None or float(gap) <= TARGET_GAP + 1e-9):
            break
    if selected is None:
        raise RuntimeError(f"No incumbent after retry: {attempts[-1]['message']}")
    return selected, attempts


def committed(model: Model, result: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, idx in model.x_index.items():
        plot, year, slot, crop = key
        area = float(result.x[idx])
        if year == model.year_start and area > 1e-5:
            out.append({"plot_id": plot, "year": year, "slot": slot, "crop_id": crop,
                        "area": area, **model.meta[key]})
    return out


def stage_record(model: Model, result: Any, attempts: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    gap = getattr(result, "mip_gap", None)
    return {"stage": stage, "years": [model.year_start, model.year_end],
            "economic_profit_yuan": float(model.economic @ result.x),
            "half_price_profit_yuan": float(model.half @ result.x),
            "waste_jin": max(0.0, float(model.waste @ result.x)),
            "activation_penalty_yuan": float(EPSILON_ACTIVATION_YUAN * (model.activation @ result.x)),
            "selected_status": int(result.status), "selected_gap": None if gap is None else float(gap),
            "attempts": attempts, "variables": len(result.x),
            "binary_variables": int(model.integrality.sum()), "constraints": len(model.constraints.lb)}


def run_policy(land: pd.DataFrame, economics: pd.DataFrame, demand: dict[int, float],
               history_2023: list[dict[str, Any]], policy: str, eta: float | None = None) -> dict[str, Any]:
    history = [dict(row) for row in history_2023]
    plan: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
    for start in YEARS:
        end = min(2030, start + 2)
        record: dict[str, Any] = {"committed_year": start}
        if policy == "half_price":
            model = build_model(land, economics, demand, history, start, end)
            result, attempts = solve(model, "half")
            record["half_price"] = stage_record(model, result, attempts, "half_price_profit")
        else:
            pure_model = build_model(land, economics, demand, history, start, end)
            pure_result, attempts = solve(pure_model, "pure")
            record["pure_profit"] = stage_record(pure_model, pure_result, attempts, "pure_profit")
            model, result = pure_model, pure_result
            if policy == "pareto":
                pi_star = float(pure_model.economic @ pure_result.x)
                slack = max(1e-4, abs(pi_star) * 1e-9)
                floor = (1.0 - float(eta)) * pi_star - slack
                model = build_model(land, economics, demand, history, start, end, profit_floor=floor)
                result, attempts = solve(model, "waste")
                record["pareto"] = {**stage_record(model, result, attempts, "minimum_waste"),
                                    "eta": eta, "pi_star_yuan": pi_star,
                                    "profit_floor_yuan": floor, "numeric_slack_yuan": slack}
        rows = committed(model, result)
        if not rows:
            raise RuntimeError(f"No committed rows for {policy} in {start}")
        plan.extend(rows); history.extend(rows)
        record["committed_activations"] = len(rows)
        windows.append(record)
    return {"policy": policy, "eta": eta, "plan": plan, "windows": windows}
