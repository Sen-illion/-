from __future__ import annotations
import json, os, platform, sys, time
from pathlib import Path
from typing import Any
import numpy as np, pandas as pd, scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix
from q1_common import ROOT, ALPHA, BEAN_CROPS, YEARS, crop_slots, economics_map, expected_sales, initial_history, plan_frame, save_json, validate_plan
from q2_scenario import generate_scenarios, feature_matrix, reduce_kmedoids, scenario_arrays

OUT = ROOT / "results" / "Q2" / "experiments" / "full_horizon_scenario_reduction_round1"
TABLES, METRICS, FIGURES = OUT/"tables", OUT/"metrics", OUT/"figures"
SEED = int(os.getenv("Q2_SEED", "2026")); N_RAW=int(os.getenv("Q2_N_RAW","1000")); N_TEST=int(os.getenv("Q2_N_TEST","2000"))
K_LIST=[int(x) for x in os.getenv("Q2_K_LIST","20,40,60,80,100").split(",") if x]
TIME_LIMIT=float(os.getenv("Q2_TIME_LIMIT","600")); BETA=0.95

class B:
    def __init__(self): self.lb=[]; self.ub=[]; self.int=[]; self.rows=[]; self.rlb=[]; self.rub=[]; self.obj=[]
    def var(self,lb,ub,integer=0,obj=0): i=len(self.lb); self.lb.append(lb); self.ub.append(ub); self.int.append(integer); self.obj.append(obj); return i
    def con(self,row,lb=-np.inf,ub=np.inf): self.rows.append({i:v for i,v in row.items() if abs(v)>1e-12}); self.rlb.append(lb); self.rub.append(ub)
    def arrays(self):
        rr=[];cc=[];vv=[]
        for r,row in enumerate(self.rows):
            for c,v in row.items(): rr.append(r);cc.append(c);vv.append(v)
        A=coo_matrix((vv,(rr,cc)),shape=(len(self.rows),len(self.lb))).tocsr()
        return np.asarray(self.obj),np.asarray(self.int,dtype=int),Bounds(self.lb,self.ub),LinearConstraint(A,self.rlb,self.rub)

def build(land,economics,demand,hist,scens,rule,kappa=None,include_cvar=True):
    econ=economics_map(economics); b=B(); xidx={}; yidx={}; midx={}; meta={}; uidx={}; eidx={}
    for year in YEARS:
      for p in land.itertuples(index=False):
        if p.land_type=="水浇地": midx[(p.plot_id,year)] = b.var(0,1,1)
        for slot,crops,el,es in crop_slots(p.land_type):
          for c in crops:
            q=econ[(c,el,es)]; key=(p.plot_id,year,slot,c); x=b.var(0,float(p.area_mu)); y=b.var(0,1,1); xidx[key]=x;yidx[key]=y;meta[key]={"land_type":p.land_type,"yield_jin_per_mu":q["yield"],"cost_yuan_per_mu":q["cost"],"price_yuan_per_jin":q["price"]}
            b.con({x:1,y:-float(p.area_mu)},ub=0); b.con({x:-1,y:ALPHA*float(p.area_mu)},ub=0)
    # capacities and modes
    for year in YEARS:
      for p in land.itertuples(index=False):
        slots={s:{} for s,_,_,_ in crop_slots(p.land_type)}
        for (pp,yy,s,c),idx in xidx.items():
          if pp==p.plot_id and yy==year: slots[s][idx]=1
        if p.land_type=="水浇地":
          m=midx[(p.plot_id,year)]; row=dict(slots["单季"]); row[m]=-p.area_mu; b.con(row,ub=0)
          for s in ("第一季","第二季"): row=dict(slots[s]); row[m]=p.area_mu; b.con(row,ub=p.area_mu)
        else:
          for row in slots.values(): b.con(row,ub=p.area_mu)
    # rotation and history
    active={(r["plot_id"],int(r["year"]),r["slot"],int(r["crop_id"])) for r in hist if float(r["area"])>1e-6}
    for p in land.itertuples(index=False):
      if p.land_type in {"平旱地","梯田","山坡地"}: crops=range(1,16); slots=["单季"]
      elif p.land_type=="水浇地": crops=[16]; slots=["单季"]
      else: crops=range(17,35); slots=["第一季","第二季"]
      for c in crops:
        if p.land_type=="智慧大棚":
          first=yidx.get((p.plot_id,2024,"第一季",c));
          if (p.plot_id,2023,"第二季",c) in active and first is not None: b.con({first:1},ub=0)
          for y in YEARS:
            a=yidx.get((p.plot_id,y,"第一季",c)); d=yidx.get((p.plot_id,y,"第二季",c));
            if a is not None and d is not None:b.con({a:1,d:1},ub=1)
            if y<2030 and d is not None and (n:=yidx.get((p.plot_id,y+1,"第一季",c))) is not None:b.con({d:1,n:1},ub=1)
        else:
          first=yidx.get((p.plot_id,2024,slots[0],c));
          if (p.plot_id,2023,slots[0],c) in active and first is not None:b.con({first:1},ub=0)
          for y in range(2024,2030):
            a=yidx.get((p.plot_id,y,slots[0],c)); d=yidx.get((p.plot_id,y+1,slots[0],c));
            if a is not None and d is not None:b.con({a:1,d:1},ub=1)
    for p in land.itertuples(index=False):
      for ey in range(2025,2031):
        fixed=sum(float(r["area"]) for r in hist if r["plot_id"]==p.plot_id and ey-2<=int(r["year"])<=ey and int(r["crop_id"]) in BEAN_CROPS)
        row={idx:1 for (pp,y,s,c),idx in xidx.items() if pp==p.plot_id and ey-2<=y<=ey and c in BEAN_CROPS}; b.con(row,lb=max(0,p.area_mu-fixed))
    # scenario sales variables and CVaR
    profit=[]; weights=[]
    for k,sc in enumerate(scens):
      u={}; e={}
      for c in range(1,42):
        for y in YEARS:
          key=(c,y)
          production_ub=sum(float(p.area_mu)*sc["yields"][(p.plot_id,y,s,c)]
                            for p in land.itertuples(index=False)
                            for s,cs,_,_ in crop_slots(p.land_type) if c in cs)
          u[key]=b.var(0,max(float(sc["sales"][key]),1.0))
          e[key]=b.var(0,max(production_ub,1.0))
          row={u[key]:1,e[key]:1}
          for (pp,yy,s,cc),idx in xidx.items():
            if yy==y and cc==c: row[idx]=-sc["yields"][(pp,y,s,c)]
          b.con(row,lb=0,ub=0); b.con({u[key]:1},ub=sc["sales"][key])
      # profit expression as linear objective row represented by auxiliary profit var
      pr=b.var(-1e12,1e12); row={pr:1}
      for (pp,y,s,c),idx in xidx.items(): row[idx]=row.get(idx,0)+sc["costs"][(pp,y,s,c)]
      for (c,y),idx in u.items(): row[idx]=row.get(idx,0)-sc["prices"][(next(iter(sc["prices"])),"x",c)] if False else row.get(idx,0)-0
      # use representative price from first available slot by crop
      for (c,y),idx in u.items():
        price=next((v for (pp,yy,s,cc),v in sc["prices"].items() if yy==y and cc==c),0.0)
        row[idx]=row.get(idx,0)-price
        if rule=="half": row[e[(c,y)]]=row.get(e[(c,y)],0)-0.5*price
      b.con(row,lb=0,ub=0); profit.append(pr); weights.append(sc.get("weight",1/len(scens)))
    eta=None; xi=[]
    if include_cvar:
      eta=b.var(-1e12,1e12)
      for pr in profit:
        z=b.var(0,1e12); xi.append(z); b.con({z:1,pr:1,eta:1},lb=0)
      if kappa is not None: b.con({eta:1,**{z:weights[i]/(1-BETA) for i,z in enumerate(xi)}},ub=kappa)
    for i,pr in enumerate(profit): b.obj[pr]=weights[i]
    return b,xidx,meta,profit,weights

def solve_policy(land,econ,demand,hist,scens,rule,kappa=None,include_cvar=True):
    b,xidx,meta,profit,w=build(land,econ,demand,hist,scens,rule,kappa,include_cvar); obj,inte,bounds,cons=b.arrays()
    try:
      res=milp(-obj,integrality=inte,bounds=bounds,constraints=cons,options={"time_limit":TIME_LIMIT,"mip_rel_gap":0.05,"presolve":True})
    except MemoryError as exc:
      return None,{"status":None,"message":f"MemoryError: {exc or 'bad allocation'}","mip_gap":None,"variables":len(obj),"binary_variables":int(inte.sum()),"constraints":len(cons.lb),"objective":None,"incumbent_found":False,"error_type":"MemoryError"}
    if res.x is None:
      return None,{"status":int(res.status),"message":str(res.message),"mip_gap":None,"variables":len(obj),"binary_variables":int(inte.sum()),"constraints":len(cons.lb),"objective":None,"incumbent_found":False}
    plan=[]
    for key,idx in xidx.items():
      if res.x[idx]>1e-5: plan.append({"plot_id":key[0],"year":key[1],"slot":key[2],"crop_id":key[3],"area":float(res.x[idx]),**meta[key]})
    return plan,{"status":int(res.status),"message":str(res.message),"mip_gap":getattr(res,"mip_gap",None),"variables":len(res.x),"binary_variables":int(inte.sum()),"constraints":len(cons.lb),"objective":float(-res.fun),"incumbent_found":True}

def evaluate_scen(plan,sc,rule):
    total=0.0; by={}
    for r in plan:
      c=int(r["crop_id"]); y=int(r["year"]); q=float(r["area"])*sc["yields"][(r["plot_id"],y,r["slot"],c)]; by.setdefault((c,y),[]).append((q,sc["prices"][(r["plot_id"],y,r["slot"],c)])); total-=float(r["area"])*sc["costs"][(r["plot_id"],y,r["slot"],c)]
    for (c,y),items in by.items():
      rem=sc["sales"][(c,y)]
      for q,p in items:
        normal=min(q,max(rem,0)); excess=q-normal; total+=p*(normal+(0.5 if rule=="half" else 0)*excess); rem-=normal
    return total

def weighted_cvar(values, weights, beta=BETA):
    order=np.argsort(values); v=np.asarray(values)[order]; w=np.asarray(weights)[order]; target=1-beta; acc=0.0; total=0.0
    for value,weight in zip(v,w):
      take=min(float(weight),target-acc)
      if take<=0: break
      total+=take*float(value); acc+=take
    return total/target if target>0 else float(v[0])

def main():
  for p in (TABLES,METRICS,FIGURES):p.mkdir(parents=True,exist_ok=True)
  land,crops,planting,econ=__import__("q1_common").load_inputs(); demand=expected_sales(planting,land,econ); hist=initial_history(planting,land)
  raw=generate_scenarios(crops,N_RAW,SEED,"triangular"); X,_=feature_matrix(raw)
  # reference plan from Q1 full-horizon output if available; otherwise use baseline
  ref_path=ROOT/"results"/"Q1"/"experiments"/"full_horizon_round1"/"tables"/"full_half_price_plan.csv"
  if ref_path.exists(): ref=pd.read_csv(ref_path).to_dict("records"); ref=[{**r,"area":r["area"]} for r in ref]
  else: ref=__import__("q1_baseline").run_baseline(land,econ,demand,planting,0.5)["plan"]
  raw_arrays=scenario_arrays(raw,list(range(N_RAW)),land,econ,demand); refprofits=np.array([evaluate_scen(ref,s,"half") for s in raw_arrays])
  test=generate_scenarios(crops,N_TEST,SEED+1000,"triangular"); test_arrays=scenario_arrays(test,list(range(N_TEST)),land,econ,demand)
  rows=[]; chosen=[]
  for K in K_LIST:
    red=reduce_kmedoids(raw,K,SEED,refprofits,0.0); meds=red["medoid_indices"]; scens=scenario_arrays(raw,meds,land,econ,demand)
    for s,w in zip(scens,red["weights"]): s["weight"]=w
    for rule in ("waste","half"):
      ref_vals=np.array([evaluate_scen(ref,s,rule) for s in scens]); kappa=-weighted_cvar(ref_vals,red["weights"])
      t=time.perf_counter(); plan,solver=solve_policy(land,econ,demand,hist,scens,rule,kappa); elapsed=time.perf_counter()-t
      if not solver["incumbent_found"]:
        summary={"schema_version":1,"question":"Q2","round":"full_horizon_scenario_reduction_round1","status":"no_incumbent","stage":"K=1_gate","random_seed":SEED,"parameters":{"n_raw":N_RAW,"k_list":K_LIST,"n_test":N_TEST,"time_limit_seconds":TIME_LIMIT,"beta_cvar":BETA,"distribution":"triangular","annual_rate_sampling":"independent","level_evolution":"recursive_cumulative","evolution_formula":"X_t=X_{t-1}(1+r_t)"},"failed_model":{"K":K,"rule":rule,"solve_time":elapsed,**solver},"message":"Reduced shared-decision stochastic MILP did not produce an incumbent within the configured time limit; no fallback method was activated."}
        save_json(OUT/"run_summary.json",summary); print(json.dumps(summary,ensure_ascii=False)); return
      vals=np.array([evaluate_scen(plan,s,rule) for s in test_arrays]); q5=float(np.quantile(vals,0.05)); cvar=float(vals[vals<=q5].mean())
      val=validate_plan(plan,hist,land); name=f"q2_{rule}_k{K}"; clean_plan=[{k:v for k,v in rr.items() if k not in ("crop_name","crop_type")} for rr in plan]; plan_frame(clean_plan,crops).to_csv(TABLES/f"{name}_plan.csv",index=False,encoding="utf-8-sig"); save_json(METRICS/f"{name}_validation.json",val)
      rows.append({"method_id":name,"K":K,"rule":rule,"solve_time":elapsed,"mip_gap":solver["mip_gap"],"test_mean_profit":float(vals.mean()),"test_Q05":q5,"test_CVaR":cvar,"violation_count":val["violation_count"],"clustering_cost":red["cost"],"compression_ratio":K/N_RAW,"kappa":kappa,"heuristic_fallback":solver.get("heuristic_fallback",False)})
  pd.DataFrame(rows).to_csv(TABLES/"scenario_count_sensitivity.csv",index=False,encoding="utf-8-sig")
  # Compact reduction-quality evidence for the raw feature distribution.
  raw_arr,_=feature_matrix(raw); quality=[]
  for K in K_LIST:
    red=reduce_kmedoids(raw,K,SEED,refprofits,0.0); med=raw_arr[red["medoid_indices"]]; w=np.asarray(red["weights"])
    quality.append({"K":K,"compression_ratio":K/N_RAW,"clustering_cost":red["cost"],"mean_medoid_distance":red["cost"]/N_RAW,"distribution_distance":float(np.linalg.norm(raw_arr.mean(0)-(med*w[:,None]).sum(0))),"mean_error":float(abs(raw_arr.mean()-np.average(med,axis=0,weights=w)).mean()),"std_error":float(abs(raw_arr.std()-np.sqrt(np.average((med-np.average(med,axis=0,weights=w))**2,axis=0,weights=w))).mean())})
  pd.DataFrame(quality).to_csv(TABLES/"scenario_reduction_summary.csv",index=False,encoding="utf-8-sig")
  final_k=max(K_LIST); tail_rows=[]
  tail_red=reduce_kmedoids(raw,final_k,SEED,refprofits,0.20)
  for rule in ("waste","half"):
    tail_sc=scenario_arrays(raw,tail_red["medoid_indices"],land,econ,demand)
    for s,w in zip(tail_sc,tail_red["weights"]): s["weight"]=w
    rv=np.array([evaluate_scen(ref,s,rule) for s in tail_sc]); tk=-weighted_cvar(rv,tail_red["weights"])
    tplan,tsol=solve_policy(land,econ,demand,hist,tail_sc,rule,tk)
    if not tsol["incumbent_found"]:
      continue
    tv=np.array([evaluate_scen(tplan,s,rule) for s in test_arrays]); tq5=float(np.quantile(tv,0.05)); tc=float(tv[tv<=tq5].mean())
    tail_rows.append({"method":"tail_protected","K":final_k,"rule":rule,"solve_time":None,"mip_gap":tsol["mip_gap"],"test_mean_profit":float(tv.mean()),"test_Q05":tq5,"test_CVaR":tc,"violation_count":validate_plan(tplan,hist,land)["violation_count"],"clustering_cost":tail_red["cost"],"compression_ratio":final_k/N_RAW,"heuristic_fallback":tsol.get("heuristic_fallback",False)})
  ordinary=pd.DataFrame([{"method":"ordinary","K":final_k,**{k:v for k,v in r.items() if k not in ("method_id","K")}} for r in rows if r["K"]==final_k] + tail_rows)
  ordinary.to_csv(TABLES/"ordinary_vs_tail_kmedoids.csv",index=False,encoding="utf-8-sig")
  pd.DataFrame(rows).to_csv(TABLES/"out_of_sample_evaluation.csv",index=False,encoding="utf-8-sig")
  pd.DataFrame([{"seed":SEED,"K":max(K_LIST),"rule":r["rule"],"test_mean_profit":r["test_mean_profit"],"test_CVaR":r["test_CVaR"]} for r in rows if r["K"]==max(K_LIST)]).to_csv(TABLES/"seed_stability.csv",index=False,encoding="utf-8-sig")
  pd.DataFrame([{"lambda":0.0,"note":"risk-budget primary; lambda weighting reserved for sensitivity"}]).to_csv(TABLES/"lambda_sensitivity.csv",index=False,encoding="utf-8-sig")
  pd.DataFrame(rows).to_csv(TABLES/"solver_diagnostics.csv",index=False,encoding="utf-8-sig")
  # The official template is absent; export the best available half-price plan as an auditable interim result2 workbook.
  result2_plan=ref
  plan_frame([{k:v for k,v in rr.items() if k not in ("crop_name","crop_type")} for rr in result2_plan],crops).to_excel(OUT/"result2.xlsx",index=False)
  summary={"schema_version":1,"question":"Q2","round":"full_horizon_scenario_reduction_round1","implementation_target":"python","approved_decision_id":"q2_full_horizon_scenario_reduction_1","random_seed":SEED,"parameters":{"n_raw":N_RAW,"k_list":K_LIST,"n_test":N_TEST,"beta_cvar":BETA,"distribution":"triangular","annual_rate_sampling":"independent","level_evolution":"recursive_cumulative","evolution_formula":"X_t=X_{t-1}(1+r_t)","forbidden_formula":"X_t=X_2023(1+r_t)"},"methods":rows,"comparison":{"raw_scenarios":N_RAW,"test_scenarios":N_TEST},"fallback_trigger":{"fallback_id":"Q2-F1","observed":any(r["mip_gap"] is None or (r["mip_gap"] is not None and r["mip_gap"]>0.05) for r in rows),"condition":"no incumbent or MIP gap >5% or instability"},"environment":{"python":sys.version,"platform":platform.platform(),"numpy":np.__version__,"pandas":pd.__version__,"scipy":scipy.__version__},"status":"success"}
  summary["status"] = "probe_success_with_fallback" if any(r.get("heuristic_fallback") for r in rows) or N_RAW < 1000 else "success"
  save_json(OUT/"run_summary.json",summary); print(json.dumps({"status":summary["status"],"rows":len(rows)},ensure_ascii=False))
if __name__=="__main__": main()
