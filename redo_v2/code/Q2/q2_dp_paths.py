from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from q1_common import ALPHA, BEAN_CROPS, YEARS, crop_slots, economics_map, validate_plan


@dataclass(frozen=True)
class PlotState:
    prev2: tuple[tuple[str, int], ...]
    prev1: tuple[tuple[str, int], ...]
    bean2: float
    bean1: float
    mode: str


def _history_state(plot_id: str, land_type: str, history: list[dict[str, Any]], area: float) -> PlotState:
    def year_rows(y: int) -> tuple[tuple[str, int], ...]:
        return tuple(sorted((r["slot"], int(r["crop_id"])) for r in history
                            if r["plot_id"] == plot_id and int(r["year"]) == y and float(r["area"]) > 1e-8))
    def bean(y: int) -> float:
        return sum(float(r["area"]) for r in history if r["plot_id"] == plot_id and int(r["year"]) == y and int(r["crop_id"]) in BEAN_CROPS)
    irrigated = len(crop_slots(land_type)) == 3
    mode = "rice" if irrigated and any(r["plot_id"] == plot_id and int(r["crop_id"]) == 16 for r in history) else "vegetable" if irrigated else "fixed"
    return PlotState(year_rows(2022), year_rows(2023), bean(2022), bean(2023), mode)


def _action_options(plot: Any, state: PlotState, year: int, econ: dict[tuple[int, str, str], dict[str, float]], width: int) -> list[list[dict[str, Any]]]:
    area = float(plot.area_mu)
    slots = crop_slots(plot.land_type)
    options: list[list[dict[str, Any]]] = []
    # Include a small deterministic crop pool plus seeded alternatives. Empty
    # actions are legal and are retained only when they can still meet beans.
    for slot, crops, eland, eseason in slots:
        legal = [c for c in crops if (c, eland, eseason) in econ]
        if state.prev1 and any(prev_slot == slot and prev_crop in legal for prev_slot, prev_crop in state.prev1):
            legal = [c for c in legal if (slot, c) not in state.prev1]
        if not legal:
            continue
        seed = int(hashlib.sha256(f"{plot.plot_id}|{year}|{slot}".encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        picks = list(dict.fromkeys([min(legal), max(legal), *rng.choice(legal, size=min(len(legal), 4), replace=False).tolist()]))[:width]
        for c in picks:
            options.append([{ "plot_id": plot.plot_id, "year": year, "slot": slot, "crop_id": int(c), "area": area }])
    if len(slots) == 3:
        rice = [a for a in options if a and a[0]["slot"] == "单季" and a[0]["crop_id"] == 16]
        veg = [a for a in options if a and a[0]["slot"] in ("第一季", "第二季")]
        paired=[]
        first=[a for a in veg if a[0]["slot"]=="第一季"]
        second=[a for a in veg if a[0]["slot"]=="第二季"]
        for a in first[:width]:
            for b in second[:width]:
                if a[0]["crop_id"] != b[0]["crop_id"]: paired.append(a+b)
        options = rice[:width] + paired[:width]
    return options[: max(width, 1)]


def generate_plot_paths(plot: Any, history: list[dict[str, Any]], economics: pd.DataFrame, paths_per_plot: int = 10, beam_width: int = 50) -> list[list[dict[str, Any]]]:
    econ = economics_map(economics)
    initial = _history_state(plot.plot_id, plot.land_type, history, float(plot.area_mu))
    beam: list[tuple[PlotState, list[dict[str, Any]], float]] = [(initial, [], 0.0)]
    for year in YEARS:
        nxt: list[tuple[PlotState, list[dict[str, Any]], float]] = []
        for state, path, score in beam:
            for action in _action_options(plot, state, year, econ, max(4, paths_per_plot)):
                bean_area = sum(float(r["area"]) for r in action if int(r["crop_id"]) in BEAN_CROPS)
                current = state.bean2 + state.bean1 + bean_area
                # At the end of each three-year window, enforce area coverage.
                if year >= 2025 and (state.bean2 + state.bean1 + bean_area) + 1e-8 < float(plot.area_mu):
                    continue
                keys = tuple(sorted((r["slot"], int(r["crop_id"])) for r in action))
                new_state = PlotState(state.prev1, keys, state.bean1, bean_area, state.mode)
                nxt.append((new_state, path + action, score + bean_area))
        if not nxt:
            return []
        # Keep diverse states and highest bean coverage/score representatives.
        grouped: dict[tuple[Any, ...], tuple[PlotState, list[dict[str, Any]], float]] = {}
        for item in nxt:
            key=(item[0].prev1, item[0].prev2, round(item[0].bean1,6), round(item[0].bean2,6), item[0].mode)
            if key not in grouped or item[2] > grouped[key][2]: grouped[key]=item
        beam=sorted(grouped.values(), key=lambda x: (-x[2], str(x[0])))[:beam_width]
    legal=[]
    for _, path, _ in beam:
        enriched=[]
        for r in path:
            p=None
            for _, crop_ids, eland, eseason in crop_slots(plot.land_type):
                if int(r["crop_id"]) in crop_ids and _ == r["slot"]:
                    p=econ[(int(r["crop_id"]),eland,eseason)]; break
            if p is None: continue
            enriched.append({**r,"land_type":plot.land_type,"yield_jin_per_mu":p["yield"],"cost_yuan_per_mu":p["cost"],"price_yuan_per_jin":p["price"]})
        if validate_plan(enriched, history, pd.DataFrame([plot])).get("violation_count", 1) == 0:
            legal.append(enriched)
    return legal[:paths_per_plot]


def generate_all_paths(land: pd.DataFrame, economics: pd.DataFrame, history: list[dict[str, Any]], paths_per_plot: int = 10, beam_width: int = 50) -> dict[str, list[list[dict[str, Any]]]]:
    out={}
    for plot in land.itertuples(index=False):
        out[plot.plot_id]=generate_plot_paths(plot, history, economics, paths_per_plot, beam_width)
    return out
