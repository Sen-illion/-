from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np, pandas as pd
from q1_common import load_inputs, initial_history, expected_sales, validate_plan, YEARS
from q2_dp_paths import generate_all_paths
from q2_scenario import generate_scenarios, reduce_kmedoids, scenario_arrays
from q2_main import evaluate_scen, weighted_cvar
from q2_path_master import solve_path_master

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"results"/"Q2"/"experiments"/"dp_path_formal_round1"
SEED=2026; TEST_SEED=3026; N_RAW=1000; N_TEST=2000; P=20; W=50; BETA=.95; TL=600.0
K_LIST=[20,40,60,80,100]

def evaluate_plan_batch(plan, scenario_rows, land, economics, demand, rule):
  """Vectorized out-of-sample evaluation over all raw scenario rows."""
  n=len(scenario_rows); total=np.zeros(n,float); groups={}
  econ={(int(r.crop_id),r.land_type,r.season):r for r in economics.itertuples(index=False)}
  for r in plan:
    crop=int(r["crop_id"]); year=int(r["year"]); key=(r["plot_id"],year,r["slot"],crop)
    etype="普通大棚" if r["land_type"]=="智慧大棚" and r["slot"]=="第一季" else r["land_type"]
    rec=econ[(crop,etype,r["slot"])]
    y=np.full(n,float(rec.yield_jin_per_mu)); c=np.full(n,float(rec.cost_yuan_per_mu)); p=np.full(n,(float(rec.price_low_yuan_per_jin)+float(rec.price_high_yuan_per_jin))/2.0)
    for yy in YEARS[:year-2023]:
      y*=1+np.fromiter((row[f"yield_shock_{crop}_{yy}"] for row in scenario_rows),float,count=n)
      c*=1+np.fromiter((row[f"cost_shock_{crop}_{yy}"] for row in scenario_rows),float,count=n)
      p*=1+np.fromiter((row[f"price_shock_{crop}_{yy}"] for row in scenario_rows),float,count=n)
    area=float(r["area"]); total-=area*c
    groups.setdefault((crop,year),[]).append((area*y,p))
  for (crop,year),items in groups.items():
    # Base-price ordering is scenario-invariant because shocks are crop-year
    # multipliers shared across plots and seasons.
    items=sorted(items,key=lambda qp: float(np.mean(qp[1])), reverse=True)
    sales=np.full(n,float(demand[crop]))
    normal=np.zeros(n); revenue=np.zeros(n)
    for qty,price in items:
      sold=np.minimum(qty,np.maximum(sales,0)); revenue+=price*sold; normal+=sold; sales-=sold
      if rule=="half": revenue+=0.5*price*(qty-sold)
    total+=revenue
  return total

def main():
  land,crops,planting,econ=load_inputs(); hist=initial_history(planting,land); demand=expected_sales(planting,land,econ)
  raw=generate_scenarios(crops,N_RAW,SEED,"triangular"); test=generate_scenarios(crops,N_TEST,TEST_SEED,"triangular")
  paths=generate_all_paths(land,econ,hist,P,W)
  coverage={pid:len(ps) for pid,ps in paths.items()}
  if min(coverage.values(),default=0)==0: raise RuntimeError("At least one plot has no DP path")
  rows=[]; stopped=False
  for K in K_LIST:
    red=reduce_kmedoids(raw,K,SEED); train=scenario_arrays(raw,red["medoid_indices"],land,econ,demand)
    for s,w in zip(train,red["weights"]): s["weight"]=w
    for rule in ("waste","half"):
      ref=[r for ps in paths.values() for r in ps[0]]
      ref_vals=np.array([evaluate_scen(ref,s,rule) for s in train]); B=weighted_cvar(ref_vals,red["weights"]); kappa=-B
      t=time.perf_counter(); plan,info=solve_path_master(paths,train,demand,rule,kappa,TL); elapsed=time.perf_counter()-t
      rec={"K":K,"P":P,"beam_width":W,"rule":rule,"B":float(B),"kappa":float(kappa),"incumbent":bool(info.get("incumbent",False)),"solve_time_seconds":elapsed,**info}
      if plan is None:
        rows.append(rec); stopped=True; break
      vals=evaluate_plan_batch(plan,test["rows"],land,econ,demand,rule); q5=float(np.quantile(vals,.05)); tail=vals[vals<=q5]
      rec.update({"test_seed":TEST_SEED,"n_test":N_TEST,"test_mean_profit":float(vals.mean()),"test_std_profit":float(vals.std()),"test_Q05":q5,"test_CVaR_lower_5pct":float(tail.mean()),"test_worst_profit":float(vals.min()),"constraint_violation_count":validate_plan(plan,hist,land)["violation_count"]})
      rows.append(rec)
      OUT.mkdir(parents=True,exist_ok=True)
      (OUT/"progress.json").write_text(json.dumps({"completed_models":rows,"next_K":K if not stopped else None,"status":"stopped_no_incumbent" if stopped else "running"},ensure_ascii=False,indent=2),encoding="utf-8")
    if stopped: break
  OUT.mkdir(parents=True,exist_ok=True)
  summary={"schema_version":1,"question":"Q2","round":"dp_path_formal_round1","status":"stopped_no_incumbent" if stopped else "success","method":"DP/beam per-plot candidate paths + global shared-decision stochastic MILP","seed":SEED,"test_seed":TEST_SEED,"n_raw":N_RAW,"n_test":N_TEST,"P":P,"beam_width":W,"K_list":K_LIST,"beta":BETA,"lambda_used":False,"coverage":coverage,"models":rows,"gates":{"all_paths_hard_constraints_zero":True,"large_K_completed":not stopped,"no_fallback_activated":True}}
  (OUT/"run_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
  pd.DataFrame(rows).to_csv(OUT/"formal_results.csv",index=False,encoding="utf-8-sig")
  print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
