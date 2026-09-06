from __future__ import annotations

import json, os, sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code" / "Q1"))
sys.path.insert(0, str(ROOT / "code" / "Q2"))

from q1_common import load_inputs, expected_sales, initial_history
from q1_model import build_model, _attempt
from q2_scenario import generate_scenarios, reduce_kmedoids, scenario_arrays
from q2_main import solve_policy, evaluate_scen, weighted_cvar

TIME_LIMIT = float(os.getenv("Q2_DIAG_TIME_LIMIT", "600"))
SEED = 2026
OUT = ROOT / "results" / "Q2" / "experiments" / "bottleneck_diagnostic"

def record_q1(land, econ, demand, hist):
    model = build_model(land, econ, demand, hist, 2024, 2030)
    t = time.perf_counter(); res, elapsed = _attempt(model, "pure", TIME_LIMIT)
    return {
        "id":"M0", "description":"Q1 deterministic seven-year MILP", "K":0, "cvar":False,
        "continuous_variables":int((model.integrality==0).sum()), "binary_integer_variables":int(model.integrality.sum()),
        "constraints":len(model.constraints.lb), "presolve_variables":None, "presolve_constraints":None,
        "incumbent":res.x is not None, "best_bound":getattr(res,"mip_dual_bound",None),
        "mip_gap":getattr(res,"mip_gap",None), "node_count":getattr(res,"mip_node_count",None),
        "solve_time_seconds":elapsed, "status":int(res.status), "message":str(res.message),
        "scenario_indexed_binary_variables":0, "note":"SciPy milp does not expose presolve counts in result object"
    }

def record_q2(name, K, cvar, land, econ, demand, hist, raw):
    red = reduce_kmedoids(raw, K, SEED)
    scens = scenario_arrays(raw, red["medoid_indices"], land, econ, demand)
    for s,w in zip(scens, red["weights"]): s["weight"] = w
    kappa = None
    if cvar:
        # Use a broad, finite risk budget from the reference deterministic plan;
        # this keeps the diagnostic focused on CVaR structure, not fallback logic.
        ref = __import__("q1_baseline").run_baseline(land, econ, demand, __import__("q1_common").load_inputs()[2], 0.5)["plan"]
        vals = np.array([evaluate_scen(ref, s, "half") for s in scens])
        kappa = -weighted_cvar(vals, red["weights"])
    t = time.perf_counter(); plan, info = solve_policy(land, econ, demand, hist, scens, "half", kappa, include_cvar=cvar); elapsed=time.perf_counter()-t
    # Rebuild only for exact structural counts.
    from q2_main import build
    b, xidx, meta, profit, weights = build(land, econ, demand, hist, scens, "half", kappa, include_cvar=cvar)
    obj, inte, bounds, cons = b.arrays()
    return {
        "id":name, "description":f"Q2 seven-year shared-decision MILP K={K} {'with' if cvar else 'without'} CVaR", "K":K, "cvar":cvar,
        "continuous_variables":int((inte==0).sum()), "binary_integer_variables":int(inte.sum()),
        "constraints":len(cons.lb), "presolve_variables":None, "presolve_constraints":None,
        "incumbent":bool(info.get("incumbent_found",False)), "best_bound":None,
        "mip_gap":info.get("mip_gap"), "node_count":None, "solve_time_seconds":elapsed,
        "status":info.get("status"), "message":info.get("message"),
        "scenario_indexed_binary_variables":0,
        "x_y_planting_variables":int(sum(1 for key in xidx if key[0] is not None) * 2),
        "explicit_surplus_variables":int(K*41*7), "big_m_area_upper_bound":"plot area for x/y; u bounded by scenario demand; e bounded by legal maximum production",
        "note":"SciPy milp wrapper does not expose HiGHS presolve/node/best-bound fields"
    }

def main():
    land, crops, planting, econ = load_inputs(); demand=expected_sales(planting,land,econ); hist=initial_history(planting,land)
    raw=generate_scenarios(crops, max(5, int(os.getenv("Q2_DIAG_N_RAW","1000"))), SEED, "triangular")
    rows=[]
    specs=[("M1",1,False),("M2",1,True),("M3",5,False),("M4",5,True)]
    if not os.getenv("Q2_DIAG_ONLY"): rows.append(record_q1(land,econ,demand,hist))
    if os.getenv("Q2_DIAG_ONLY"):
        specs=[x for x in specs if x[0]==os.getenv("Q2_DIAG_ONLY")]
    for name,K,cvar in specs:
        rows.append(record_q2(name,K,cvar,land,econ,demand,hist,raw))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"diagnostic_summary.json").write_text(json.dumps({"time_limit_seconds":TIME_LIMIT,"models":rows,"status":"complete"},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(rows,ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
