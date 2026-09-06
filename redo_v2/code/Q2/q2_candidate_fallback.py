from __future__ import annotations
import json, os, sys
from pathlib import Path
import numpy as np, pandas as pd
from q1_common import ROOT, load_inputs, expected_sales, initial_history, validate_plan, save_json
from q2_scenario import generate_scenarios, scenario_arrays
from q2_main import evaluate_scen

N_RAW=int(os.getenv("Q2_N_RAW","1000")); N_TEST=int(os.getenv("Q2_N_TEST","2000")); SEED=int(os.getenv("Q2_SEED","2026"))
OUT=ROOT/"results"/"Q2"/"experiments"/"candidate_path_fallback_round1"; TABLES=OUT/"tables"; METRICS=OUT/"metrics"

def metrics(v):
    q5=float(np.quantile(v,0.05)); return {"mean_profit":float(v.mean()),"std_profit":float(v.std()),"q05_profit":q5,"bottom_10pct_mean":float(np.sort(v)[:max(1,int(.1*len(v)))].mean()),"cvar_95_profit":float(v[v<=q5].mean()),"worst_profit":float(v.min())}

def main():
    TABLES.mkdir(parents=True,exist_ok=True); METRICS.mkdir(parents=True,exist_ok=True)
    land,crops,planting,econ=load_inputs(); demand=expected_sales(planting,land,econ); hist=initial_history(planting,land)
    raw=generate_scenarios(crops,N_RAW,SEED,"triangular"); test=generate_scenarios(crops,N_TEST,SEED+1000,"triangular")
    raw_a=scenario_arrays(raw,list(range(N_RAW)),land,econ,demand); test_a=scenario_arrays(test,list(range(N_TEST)),land,econ,demand)
    base=ROOT/"results"/"Q1"/"experiments"/"full_horizon_round1"/"tables"
    wanted=os.getenv("Q2_CANDIDATES", "full_eta_01_plan,full_half_price_plan").split(",")
    files=[base/f"{name}.csv" for name in wanted if (base/f"{name}.csv").exists()]; rows=[]; chosen={}
    for f in files:
      plan=pd.read_csv(f).to_dict("records"); val=validate_plan(plan,hist,land)
      if val["violation_count"]: continue
      for rule in ("waste","half"):
        rv=np.array([evaluate_scen(plan,s,rule) for s in raw_a]); tv=np.array([evaluate_scen(plan,s,rule) for s in test_a]); m=metrics(tv); rm=metrics(rv)
        rec={"candidate":f.stem,"rule":rule,**m,"raw_mean_profit":rm["mean_profit"],"raw_cvar_95_profit":rm["cvar_95_profit"],"constraint_violations":0}; rows.append(rec)
    frame=pd.DataFrame(rows); frame.to_csv(TABLES/"candidate_policy_evaluation.csv",index=False,encoding="utf-8-sig")
    for rule in ("waste","half"):
      sub=frame[frame.rule==rule].copy(); threshold=float(sub.cvar_95_profit.max())*.99; eligible=sub[sub.cvar_95_profit>=threshold]; best=eligible.sort_values("mean_profit",ascending=False).iloc[0]; chosen[rule]=best.to_dict()
      src=base/f"{best['candidate']}.csv"; pd.read_csv(src).to_excel(OUT/f"result2_{rule}.xlsx",index=False)
    summary={"schema_version":1,"question":"Q2","method":"Q2-F1 candidate path coordination fallback","status":"success","n_raw":N_RAW,"n_test":N_TEST,"seed":SEED,"annual_rate_sampling":"independent","level_evolution":"recursive_cumulative","chosen":chosen,"candidate_count":len(files)}
    save_json(OUT/"run_summary.json",summary); print(json.dumps({"status":"success","chosen":{k:v["candidate"] for k,v in chosen.items()}},ensure_ascii=False))
if __name__=="__main__": main()
