from __future__ import annotations

from typing import Any

import pandas as pd

from q1_common import BEAN_CROPS, DRY_TYPES, YEARS, crop_slots, initial_history, slot_map


def marginal_profit(crop: int, area: float, params: dict[str, float], residual: dict[int, float], salvage: float) -> float:
    qty = area * params["yield"]
    normal = min(qty, max(0.0, residual[crop]))
    return params["price"] * normal + salvage * params["price"] * (qty - normal) - params["cost"] * area


def choose_crop(plot_id: str, slot: str, crops: list[int], area: float,
                params: dict[tuple[str, str, int], dict[str, float]], residual: dict[int, float],
                salvage: float, forbidden: set[int], require_bean: bool = False,
                also_forbidden: set[int] | None = None) -> tuple[int, float] | None:
    blocked = forbidden | (also_forbidden or set())
    candidates = [crop for crop in crops if crop not in blocked and (not require_bean or crop in BEAN_CROPS)]
    if not candidates:
        return None
    ranked = sorted(
        ((crop, marginal_profit(crop, area, params[(plot_id, slot, crop)], residual, salvage)) for crop in candidates),
        key=lambda item: (-item[1], item[0]),
    )
    return ranked[0]


def make_row(plot: Any, year: int, slot: str, crop: int,
             params: dict[tuple[str, str, int], dict[str, float]]) -> dict[str, Any]:
    p = params[(plot.plot_id, slot, crop)]
    return {"plot_id": plot.plot_id, "year": year, "slot": slot, "crop_id": crop,
            "area": float(plot.area_mu), "land_type": plot.land_type,
            "yield_jin_per_mu": p["yield"], "cost_yuan_per_mu": p["cost"],
            "price_yuan_per_jin": p["price"]}


def consume(rows: list[dict[str, Any]], residual: dict[int, float]) -> None:
    for row in rows:
        crop = int(row["crop_id"])
        qty = float(row["area"]) * float(row["yield_jin_per_mu"])
        residual[crop] = max(0.0, residual[crop] - qty)


def bean_years(land: pd.DataFrame, history: list[dict[str, Any]]) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    for plot in land.itertuples(index=False):
        observed = sum(float(row["area"]) for row in history
                       if row["plot_id"] == plot.plot_id and int(row["crop_id"]) in BEAN_CROPS)
        result[plot.plot_id] = {2026, 2029} if observed + 1e-6 >= float(plot.area_mu) else {2025, 2028}
    return result


def run_baseline(land: pd.DataFrame, economics: pd.DataFrame, demand: dict[int, float],
                 planting_2023: pd.DataFrame, salvage: float) -> dict[str, Any]:
    params = slot_map(land, economics)
    history = initial_history(planting_2023, land)
    scheduled_beans = bean_years(land, history)
    plan: list[dict[str, Any]] = []
    warnings: list[str] = []
    for year in YEARS:
        residual = {crop: float(value) for crop, value in demand.items()}
        for plot in land.sort_values("plot_id").itertuples(index=False):
            prior_single = {int(row["crop_id"]) for row in history + plan
                            if row["plot_id"] == plot.plot_id and int(row["year"]) == year - 1
                            and row["slot"] == "单季"}
            prior_second = {int(row["crop_id"]) for row in history + plan
                            if row["plot_id"] == plot.plot_id and int(row["year"]) == year - 1
                            and row["slot"] == "第二季"}
            required = year in scheduled_beans[plot.plot_id]
            slots = {slot: crops for slot, crops, _, _ in crop_slots(plot.land_type)}
            rows: list[dict[str, Any]] = []
            if plot.land_type in DRY_TYPES:
                pick = choose_crop(plot.plot_id, "单季", slots["单季"], float(plot.area_mu),
                                   params, residual, salvage, prior_single, require_bean=required)
                if pick is None or (pick[1] <= 0 and not required):
                    if required:
                        raise RuntimeError(f"No legal bean for {plot.plot_id}/{year}")
                else:
                    rows.append(make_row(plot, year, "单季", pick[0], params))
            elif plot.land_type == "水浇地":
                if required:
                    first = choose_crop(plot.plot_id, "第一季", slots["第一季"], float(plot.area_mu),
                                        params, residual, salvage, set(), require_bean=True)
                    if first is None:
                        raise RuntimeError(f"No legal irrigated bean for {plot.plot_id}/{year}")
                    rows.append(make_row(plot, year, "第一季", first[0], params))
                    second = choose_crop(plot.plot_id, "第二季", slots["第二季"], float(plot.area_mu),
                                         params, residual, salvage, set())
                    if second is not None and second[1] > 0:
                        rows.append(make_row(plot, year, "第二季", second[0], params))
                else:
                    rice = choose_crop(plot.plot_id, "单季", slots["单季"], float(plot.area_mu),
                                       params, residual, salvage, prior_single)
                    first = choose_crop(plot.plot_id, "第一季", slots["第一季"], float(plot.area_mu),
                                        params, residual, salvage, set())
                    second = choose_crop(plot.plot_id, "第二季", slots["第二季"], float(plot.area_mu),
                                         params, residual, salvage, set())
                    rice_score = rice[1] if rice is not None else float("-inf")
                    veg_score = sum(item[1] for item in (first, second) if item is not None and item[1] > 0)
                    if rice is not None and rice_score > max(0.0, veg_score):
                        rows.append(make_row(plot, year, "单季", rice[0], params))
                    else:
                        if first is not None and first[1] > 0:
                            rows.append(make_row(plot, year, "第一季", first[0], params))
                        if second is not None and second[1] > 0:
                            rows.append(make_row(plot, year, "第二季", second[0], params))
            else:
                first_forbidden = prior_second if plot.land_type == "智慧大棚" else set()
                first = choose_crop(plot.plot_id, "第一季", slots["第一季"], float(plot.area_mu),
                                    params, residual, salvage, first_forbidden, require_bean=required)
                if first is None and required:
                    raise RuntimeError(f"No legal greenhouse bean for {plot.plot_id}/{year}")
                if first is not None and (first[1] > 0 or required):
                    rows.append(make_row(plot, year, "第一季", first[0], params))
                block = {first[0]} if first is not None and plot.land_type == "智慧大棚" else set()
                second = choose_crop(plot.plot_id, "第二季", slots["第二季"], float(plot.area_mu),
                                     params, residual, salvage, set(), also_forbidden=block)
                if second is not None and second[1] > 0:
                    rows.append(make_row(plot, year, "第二季", second[0], params))
            consume(rows, residual)
            plan.extend(rows)
        if any(value > 0 for value in residual.values()):
            warnings.append(f"{year}: baseline leaves some normal-price demand unused")
    return {"policy": "b1_zero_price" if salvage == 0 else "b1_half_price",
            "salvage": salvage, "plan": plan, "bean_years": {k: sorted(v) for k, v in scheduled_beans.items()},
            "warnings": warnings}
