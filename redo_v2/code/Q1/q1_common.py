from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "workspace" / "data_clean"
YEARS = list(range(2024, 2031))
DRY_TYPES = {"平旱地", "梯田", "山坡地"}
BEAN_CROPS = {1, 2, 3, 4, 5, 17, 18, 19}
ALPHA = 0.10
TOL = 1e-6


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    land = pd.read_csv(DATA / "land.csv")
    crops = pd.read_csv(DATA / "crops.csv")
    planting = pd.read_csv(DATA / "planting_2023.csv")
    economics = pd.read_csv(DATA / "economics_2023.csv")
    if land["plot_id"].duplicated().any() or crops["crop_id"].duplicated().any():
        raise ValueError("Duplicate land or crop primary key")
    if planting[["plot_id", "crop_id", "season"]].duplicated().any():
        raise ValueError("Duplicate 2023 planting composite key")
    if economics[["crop_id", "land_type", "season"]].duplicated().any():
        raise ValueError("Duplicate economics composite key")
    if (land["area_mu"] <= 0).any() or (planting["area_mu"] <= 0).any():
        raise ValueError("Nonpositive area")
    if (economics["yield_jin_per_mu"] <= 0).any() or (economics["cost_yuan_per_mu"] < 0).any():
        raise ValueError("Invalid yield or cost")
    if not set(planting["plot_id"]).issubset(set(land["plot_id"])):
        raise ValueError("Unknown plot reference")
    if not set(planting["crop_id"]).issubset(set(crops["crop_id"])):
        raise ValueError("Unknown crop reference")
    return land, crops, planting, economics


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
    out: dict[tuple[int, str, str], dict[str, float]] = {}
    for row in economics.itertuples(index=False):
        out[(int(row.crop_id), row.land_type, row.season)] = {
            "yield": float(row.yield_jin_per_mu),
            "cost": float(row.cost_yuan_per_mu),
            "price": (float(row.price_low_yuan_per_jin) + float(row.price_high_yuan_per_jin)) / 2.0,
        }
    return out


def slot_map(land: pd.DataFrame, economics: pd.DataFrame) -> dict[tuple[str, str, int], dict[str, float]]:
    econ = economics_map(economics)
    out: dict[tuple[str, str, int], dict[str, float]] = {}
    for plot in land.itertuples(index=False):
        for slot, crop_ids, econ_land, econ_season in crop_slots(plot.land_type):
            for crop_id in crop_ids:
                key = (crop_id, econ_land, econ_season)
                if key not in econ:
                    raise ValueError(f"Missing economics for {plot.plot_id}/{slot}/{crop_id}: {key}")
                out[(plot.plot_id, slot, crop_id)] = econ[key]
    return out


def planting_with_land(planting: pd.DataFrame, land: pd.DataFrame) -> pd.DataFrame:
    return planting.merge(
        land[["plot_id", "land_type", "area_mu"]].rename(columns={"area_mu": "plot_area_mu"}),
        on="plot_id",
        validate="many_to_one",
    )


def observed_econ_key(crop_id: int, land_type: str, season: str) -> tuple[int, str, str]:
    if land_type == "智慧大棚" and season == "第一季":
        return crop_id, "普通大棚", "第一季"
    return crop_id, land_type, season


def expected_sales(planting: pd.DataFrame, land: pd.DataFrame, economics: pd.DataFrame) -> dict[int, float]:
    econ = economics_map(economics)
    merged = planting_with_land(planting, land)
    totals = {int(crop): 0.0 for crop in range(1, 42)}
    for row in merged.itertuples(index=False):
        params = econ[observed_econ_key(int(row.crop_id), row.land_type, row.season)]
        totals[int(row.crop_id)] += float(row.area_mu) * params["yield"]
    return totals


def initial_history(planting: pd.DataFrame, land: pd.DataFrame) -> list[dict[str, Any]]:
    merged = planting_with_land(planting, land)
    return [
        {
            "plot_id": row.plot_id,
            "year": 2023,
            "slot": row.season,
            "crop_id": int(row.crop_id),
            "area": float(row.area_mu),
        }
        for row in merged.itertuples(index=False)
    ]


def enrich_plan(
    rows: list[dict[str, Any]], land: pd.DataFrame, economics: pd.DataFrame
) -> list[dict[str, Any]]:
    plots = {row.plot_id: row for row in land.itertuples(index=False)}
    params = slot_map(land, economics)
    out: list[dict[str, Any]] = []
    for item in rows:
        if float(item["area"]) <= TOL:
            continue
        plot = plots[item["plot_id"]]
        p = params[(item["plot_id"], item["slot"], int(item["crop_id"]))]
        out.append(
            {
                **item,
                "land_type": plot.land_type,
                "yield_jin_per_mu": p["yield"],
                "cost_yuan_per_mu": p["cost"],
                "price_yuan_per_jin": p["price"],
            }
        )
    return out


def evaluate_plan(plan: list[dict[str, Any]], demand: dict[int, float], salvage: float) -> dict[str, float | int]:
    origins: dict[tuple[int, int], list[dict[str, float]]] = {}
    total_area = total_cost = total_production = 0.0
    area_by_crop: dict[int, float] = {}
    for row in plan:
        area = float(row["area"])
        qty = area * float(row["yield_jin_per_mu"])
        total_area += area
        total_cost += area * float(row["cost_yuan_per_mu"])
        total_production += qty
        crop = int(row["crop_id"])
        area_by_crop[crop] = area_by_crop.get(crop, 0.0) + area
        origins.setdefault((int(row["year"]), crop), []).append(
            {"qty": qty, "price": float(row["price_yuan_per_jin"])}
        )
    revenue = normal_sold = 0.0
    for (_, crop), items in origins.items():
        remaining = float(demand[crop])
        for item in sorted(items, key=lambda value: value["price"], reverse=True):
            normal = min(item["qty"], max(remaining, 0.0))
            excess = item["qty"] - normal
            revenue += item["price"] * normal + salvage * item["price"] * excess
            normal_sold += normal
            remaining -= normal
    excess = max(0.0, total_production - normal_sold)
    masses = sorted(area_by_crop.values(), reverse=True)
    shares = [value / total_area for value in masses] if total_area > 0 else []
    return {
        "profit_yuan": revenue - total_cost,
        "revenue_yuan": revenue,
        "cost_yuan": total_cost,
        "production_jin": total_production,
        "normal_sales_jin": normal_sold,
        "excess_jin": excess,
        "waste_jin": excess if salvage == 0 else 0.0,
        "waste_rate": excess / total_production if salvage == 0 and total_production > 0 else 0.0,
        "activation_count": len(plan),
        "average_area_per_activation_mu": total_area / len(plan) if plan else 0.0,
        "minimum_positive_area_mu": min((float(row["area"]) for row in plan), default=0.0),
        "unique_crop_count": len(area_by_crop),
        "top5_area_mass": sum(masses[:5]) / total_area if total_area else 0.0,
        "area_hhi": sum(value * value for value in shares),
        "total_planted_area_mu": total_area,
    }


def validate_plan(
    plan: list[dict[str, Any]], history_2023: list[dict[str, Any]], land: pd.DataFrame, alpha: float = ALPHA
) -> dict[str, Any]:
    plots = {row.plot_id: row for row in land.itertuples(index=False)}
    legal = {
        (plot.plot_id, slot, crop)
        for plot in land.itertuples(index=False)
        for slot, crops, _, _ in crop_slots(plot.land_type)
        for crop in crops
    }
    details: list[dict[str, Any]] = []

    def violation(kind: str, amount: float, key: str) -> None:
        details.append({"type": kind, "amount": float(amount), "key": key})

    capacity: dict[tuple[str, int, str], float] = {}
    active: set[tuple[str, int, str, int]] = set()
    for row in plan:
        plot_id, year, slot, crop = row["plot_id"], int(row["year"]), row["slot"], int(row["crop_id"])
        area = float(row["area"])
        plot = plots[plot_id]
        if (plot_id, slot, crop) not in legal:
            violation("suitability", area, f"{plot_id}/{year}/{slot}/{crop}")
        if area + TOL < alpha * float(plot.area_mu):
            violation("minimum_area", alpha * float(plot.area_mu) - area, f"{plot_id}/{year}/{slot}/{crop}")
        capacity[(plot_id, year, slot)] = capacity.get((plot_id, year, slot), 0.0) + area
        active.add((plot_id, year, slot, crop))
    for (plot_id, year, slot), area in capacity.items():
        excess = area - float(plots[plot_id].area_mu)
        if excess > TOL:
            violation("capacity", excess, f"{plot_id}/{year}/{slot}")
    for plot in land.itertuples(index=False):
        if plot.land_type == "水浇地":
            for year in YEARS:
                rice = capacity.get((plot.plot_id, year, "单季"), 0.0)
                veg = capacity.get((plot.plot_id, year, "第一季"), 0.0) + capacity.get((plot.plot_id, year, "第二季"), 0.0)
                if rice > TOL and veg > TOL:
                    violation("irrigated_mode", min(rice, veg), f"{plot.plot_id}/{year}")
    history_active = {
        (row["plot_id"], int(row["year"]), row["slot"], int(row["crop_id"]))
        for row in history_2023
        if float(row["area"]) > TOL
    }
    combined_active = active | history_active
    for plot in land.itertuples(index=False):
        if plot.land_type in DRY_TYPES:
            for year in range(2023, 2030):
                for crop in range(1, 16):
                    if ((plot.plot_id, year, "单季", crop) in combined_active and
                            (plot.plot_id, year + 1, "单季", crop) in combined_active):
                        violation("adjacent_cycle_rotation", 1.0, f"{plot.plot_id}/{year}-{year + 1}/单季/{crop}")
        elif plot.land_type == "水浇地":
            for year in range(2023, 2030):
                if ((plot.plot_id, year, "单季", 16) in combined_active and
                        (plot.plot_id, year + 1, "单季", 16) in combined_active):
                    violation("adjacent_cycle_rotation", 1.0, f"{plot.plot_id}/{year}-{year + 1}/单季/16")
        elif plot.land_type == "智慧大棚":
            for year in YEARS:
                for crop in range(17, 35):
                    if ((plot.plot_id, year, "第一季", crop) in combined_active and
                            (plot.plot_id, year, "第二季", crop) in combined_active):
                        violation("adjacent_cycle_rotation", 1.0, f"{plot.plot_id}/{year}/第一季-第二季/{crop}")
                    if year < 2030 and ((plot.plot_id, year, "第二季", crop) in combined_active and
                                        (plot.plot_id, year + 1, "第一季", crop) in combined_active):
                        violation("adjacent_cycle_rotation", 1.0, f"{plot.plot_id}/{year}-{year + 1}/第二季-第一季/{crop}")
    all_rows = history_2023 + plan
    for plot in land.itertuples(index=False):
        for end_year in range(2025, 2031):
            bean_area = sum(
                float(row["area"])
                for row in all_rows
                if row["plot_id"] == plot.plot_id
                and end_year - 2 <= int(row["year"]) <= end_year
                and int(row["crop_id"]) in BEAN_CROPS
            )
            deficit = float(plot.area_mu) - bean_area
            if deficit > TOL:
                violation("bean_area_coverage", deficit, f"{plot.plot_id}/{end_year}")
    by_type: dict[str, int] = {}
    for item in details:
        by_type[item["type"]] = by_type.get(item["type"], 0) + 1
    return {
        "violation_count": len(details),
        "max_violation": max((item["amount"] for item in details), default=0.0),
        "counts_by_type": by_type,
        "details": details[:200],
    }


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def plan_frame(plan: list[dict[str, Any]], crops: pd.DataFrame) -> pd.DataFrame:
    names = crops[["crop_id", "crop_name", "crop_type"]].copy()
    frame = pd.DataFrame(plan)
    if frame.empty:
        return frame
    frame = frame.merge(names, on="crop_id", how="left", validate="many_to_one")
    columns = [
        "plot_id", "land_type", "year", "slot", "crop_id", "crop_name", "crop_type", "area",
        "yield_jin_per_mu", "cost_yuan_per_mu", "price_yuan_per_jin",
    ]
    return frame[columns].sort_values(["year", "plot_id", "slot", "crop_id"]).reset_index(drop=True)
