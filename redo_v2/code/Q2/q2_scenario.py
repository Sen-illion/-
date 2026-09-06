from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "workspace" / "data_clean"
YEARS = list(range(2024, 2031))


def _bounds(kind: str, crop: int) -> tuple[float, float, float]:
    if kind == "sales":
        return (0.05, 0.10, 0.075) if crop in (6, 7) else (-0.05, 0.05, 0.0)
    if kind == "yield":
        return -0.10, 0.10, 0.0
    if kind == "cost":
        return 0.05, 0.05, 0.05
    if kind == "price":
        if crop in (38, 39, 40, 41):
            return (-0.05, -0.01, -0.03)
        if crop in range(17, 38):
            return (0.0, 0.10, 0.05)
        return (0.0, 0.0, 0.0)
    raise ValueError(kind)


def generate_scenarios(crops: pd.DataFrame, n: int, seed: int, distribution: str = "triangular") -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    crop_ids = [int(x) for x in crops.crop_id]
    shocks: list[dict[str, Any]] = []
    for w in range(n):
        row: dict[str, Any] = {"scenario_id": w}
        for crop in crop_ids:
            for year in YEARS:
                for kind in ("sales", "yield", "cost", "price"):
                    lo, hi, mode = _bounds(kind, crop)
                    if lo == hi:
                        val = lo
                    elif distribution == "triangular":
                        val = float(rng.triangular(lo, mode, hi))
                    else:
                        val = float(rng.uniform(lo, hi))
                    row[f"{kind}_shock_{crop}_{year}"] = val
        shocks.append(row)
    return {"seed": seed, "distribution": distribution, "years": YEARS, "rows": shocks}


def feature_matrix(scenarios: dict[str, Any]) -> tuple[np.ndarray, list[str]]:
    rows = scenarios["rows"]
    keys = sorted(k for k in rows[0] if k != "scenario_id")
    arr = np.asarray([[float(r[k]) for k in keys] for r in rows], dtype=float)
    mu, sd = arr.mean(axis=0), arr.std(axis=0)
    sd[sd < 1e-12] = 1.0
    return (arr - mu) / sd, keys


def _medoids(X: np.ndarray, k: int, seed: int) -> tuple[np.ndarray, np.ndarray, float]:
    n = len(X)
    if k >= n:
        idx = np.arange(n)
        return idx, idx.copy(), 0.0
    rng = np.random.default_rng(seed)
    med = np.linspace(0, n - 1, k, dtype=int)
    med = np.unique(med)
    while len(med) < k:
        med = np.unique(np.r_[med, rng.integers(0, n)])
    D = cdist(X, X)
    for _ in range(12):
        labels = D[:, med].argmin(axis=1)
        new = med.copy()
        for j in range(k):
            members = np.where(labels == j)[0]
            if len(members):
                new[j] = members[np.argmin(D[np.ix_(members, members)].sum(axis=1))]
        if np.array_equal(new, med):
            break
        med = new
    labels = D[:, med].argmin(axis=1)
    cost = float(D[np.arange(n), med[labels]].sum())
    return med, labels, cost


def reduce_kmedoids(scenarios: dict[str, Any], k: int, seed: int, tail_reference: np.ndarray | None = None, tail_share: float = 0.0) -> dict[str, Any]:
    X, keys = feature_matrix(scenarios)
    n = len(X)
    if tail_reference is None or tail_share <= 0:
        med, labels, cost = _medoids(X, min(k, n), seed)
    else:
        tail_n = max(1, int(round(k * tail_share)))
        normal_n = max(1, k - tail_n)
        order = np.argsort(tail_reference)
        tail = order[: max(1, int(np.ceil(0.10 * n)))]
        normal = np.setdiff1d(np.arange(n), tail)
        tm, tl, tc = _medoids(X[tail], min(tail_n, len(tail)), seed)
        nm, nl, nc = _medoids(X[normal], min(normal_n, len(normal)), seed + 1)
        med = np.r_[tail[tm], normal[nm]]
        D = cdist(X, X[med])
        labels = D.argmin(axis=1)
        cost = float(D[np.arange(n), labels].sum())
    counts = np.bincount(labels, minlength=len(med))
    weights = counts / float(n)
    return {"medoid_indices": med.tolist(), "labels": labels.tolist(), "weights": weights.tolist(), "cost": cost, "feature_keys": keys}


def scenario_from_row(row: dict[str, Any], land: pd.DataFrame, economics: pd.DataFrame, demand: dict[int, float]) -> dict[str, Any]:
    econ = {(int(r.crop_id), r.land_type, r.season): r for r in economics.itertuples(index=False)}
    out: list[dict[str, Any]] = []
    yields, costs, prices, sales = {}, {}, {}, {}
    for r in land.itertuples(index=False):
        for slot, crop_ids, eland, eseason in __import__("q1_common").crop_slots(r.land_type):
            for crop in crop_ids:
                rec = econ[(crop, eland, eseason)]
                base_y = float(rec.yield_jin_per_mu); base_c = float(rec.cost_yuan_per_mu)
                base_p = (float(rec.price_low_yuan_per_jin) + float(rec.price_high_yuan_per_jin)) / 2
                level_y, level_c, level_p = base_y, base_c, base_p
                for year in YEARS:
                    level_y *= 1 + row[f"yield_shock_{crop}_{year}"]
                    level_c *= 1 + row[f"cost_shock_{crop}_{year}"]
                    level_p *= 1 + row[f"price_shock_{crop}_{year}"]
                    yields[(r.plot_id, year, slot, crop)] = level_y
                    costs[(r.plot_id, year, slot, crop)] = level_c
                    prices[(r.plot_id, year, slot, crop)] = level_p
    for crop in range(1, 42):
        for year in YEARS:
            growth = 1.0
            for yy in YEARS[: year - 2023]: growth *= 1 + row[f"sales_shock_{crop}_{yy}"]
            sales[(crop, year)] = float(demand[crop]) * growth
    return {"yields": yields, "costs": costs, "prices": prices, "sales": sales}


def scenario_from_row_for_plan(row: dict[str, Any], plan: list[dict[str, Any]], economics: pd.DataFrame, demand: dict[int, float]) -> dict[str, Any]:
    econ = {(int(r.crop_id), r.land_type, r.season): r for r in economics.itertuples(index=False)}
    yields, costs, prices, sales = {}, {}, {}, {}
    needed={(r["plot_id"],int(r["year"]),r["slot"],int(r["crop_id"])) for r in plan}
    for r in plan:
        key=(r["plot_id"],int(r["year"]),r["slot"],int(r["crop_id"]))
        crop=int(r["crop_id"]); year=int(r["year"]); land_type=r["land_type"]
        econ_land= "普通大棚" if land_type=="智慧大棚" and r["slot"]=="第一季" else land_type
        season=r["slot"]; rec=econ[(crop,econ_land,season)]
        y=float(rec.yield_jin_per_mu); c=float(rec.cost_yuan_per_mu); p=(float(rec.price_low_yuan_per_jin)+float(rec.price_high_yuan_per_jin))/2
        for yy in YEARS:
            if yy<=year:
                y*=1+row[f"yield_shock_{crop}_{yy}"]; c*=1+row[f"cost_shock_{crop}_{yy}"]; p*=1+row[f"price_shock_{crop}_{yy}"]
        yields[key]=y; costs[key]=c; prices[key]=p
    crops={int(r["crop_id"]) for r in plan}
    for crop in crops:
        for year in YEARS:
            growth=1.0
            for yy in YEARS[:year-2023]: growth*=1+row[f"sales_shock_{crop}_{yy}"]
            sales[(crop,year)]=float(demand[crop])*growth
    return {"yields":yields,"costs":costs,"prices":prices,"sales":sales}


def scenario_arrays(scenarios: dict[str, Any], medoid_indices: list[int], land: pd.DataFrame, economics: pd.DataFrame, demand: dict[int, float]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx in medoid_indices:
        row = scenarios["rows"][idx]
        out.append(scenario_from_row(row, land, economics, demand))
    return out
