from __future__ import annotations

import time
from pathlib import Path
from typing import Any
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from q1_common import YEARS, validate_plan


class Builder:
    def __init__(self): self.lb=[]; self.ub=[]; self.int=[]; self.obj=[]; self.rows=[]; self.rlb=[]; self.rub=[]
    def var(self, lb, ub, integer=0, obj=0.0):
        i=len(self.lb); self.lb.append(float(lb)); self.ub.append(float(ub)); self.int.append(int(integer)); self.obj.append(float(obj)); return i
    def con(self, row, lb=-np.inf, ub=np.inf):
        self.rows.append({i:v for i,v in row.items() if abs(v)>1e-12}); self.rlb.append(lb); self.rub.append(ub)
    def arrays(self):
        rr=[]; cc=[]; vv=[]
        for r,row in enumerate(self.rows):
            for c,v in row.items(): rr.append(r); cc.append(c); vv.append(v)
        A=coo_matrix((vv,(rr,cc)),shape=(len(self.rows),len(self.lb))).tocsr()
        return np.asarray(self.obj),np.asarray(self.int,dtype=int),Bounds(self.lb,self.ub),LinearConstraint(A,self.rlb,self.rub)


def _contrib(path, sc):
    q={}; cost=0.0
    for r in path:
        key=(r["plot_id"],int(r["year"]),r["slot"],int(r["crop_id"]))
        area=float(r["area"]); c=int(r["crop_id"]); y=int(r["year"])
        q[(c,y)] = q.get((c,y),0.0) + area*sc["yields"][key]
        cost += area*sc["costs"][key]
    return q,cost


def build_path_master(paths, scenarios, demand, rule="half", kappa=None, beta=0.95):
    b=Builder(); zidx={}; uidx={}; pidx=[]; contributions=[]
    for plot_id, plist in paths.items():
        for j,_ in enumerate(plist): zidx[(plot_id,j)]=b.var(0,1,1)
        b.con({zidx[(plot_id,j)]:1 for j in range(len(plist))},lb=1,ub=1)
    for k,sc in enumerate(scenarios):
        cqs=[]; costs=[]
        for plist in paths.values():
            for path in plist: cqs.append(_contrib(path,sc)[0]); costs.append(_contrib(path,sc)[1])
        contributions.append((cqs,costs))
        u={}
        for c in range(1,42):
            for y in YEARS:
                idx=b.var(0,max(float(sc["sales"][(c,y)]),1.0)); u[(c,y)]=idx; uidx[(k,c,y)]=idx
                row={idx:1}
                pos=0
                for plot_id,plist in paths.items():
                    for j,_ in enumerate(plist):
                        row[zidx[(plot_id,j)]]=row.get(zidx[(plot_id,j)],0)-cqs[pos].get((c,y),0.0); pos+=1
                b.con(row,ub=0)
                b.con({idx:1},ub=float(sc["sales"][(c,y)]))
        pr=b.var(-1e9,1e9); row={pr:1}; pos=0
        for plot_id,plist in paths.items():
            for j,_ in enumerate(plist):
                qmap=cqs[pos]; cost=costs[pos];
                row[zidx[(plot_id,j)]]=row.get(zidx[(plot_id,j)],0)+cost
                pos+=1
        for (c,y),ui in u.items():
            price=next((v for (pp,yy,s,cc),v in sc["prices"].items() if yy==y and cc==c),0.0)
            row[ui]=row.get(ui,0)-price
            if rule=="half":
                # Revenue = 0.5*p*total production + 0.5*p*normal sales.
                pos=0
                for plot_id,plist in paths.items():
                    for j,_ in enumerate(plist):
                        row[zidx[(plot_id,j)]]=row.get(zidx[(plot_id,j)],0)-0.5*price*cqs[pos].get((c,y),0.0); pos+=1
                row[ui]=row.get(ui,0)+0.5*price
        b.con(row,lb=0,ub=0); pidx.append(pr)
    if kappa is not None:
        eta=b.var(-1e9,1e9); xis=[]
        for pr in pidx:
            xi=b.var(0,1e9); xis.append(xi); b.con({xi:1,pr:1,eta:1},lb=0)
        weights=[float(s.get("weight",1/len(scenarios))) for s in scenarios]
        b.con({eta:1,**{xi:weights[i]/(1-beta) for i,xi in enumerate(xis)}},ub=kappa)
    else: eta=None
    for i,pr in enumerate(pidx): b.obj[pr]=float(scenarios[i].get("weight",1/len(scenarios)))
    return b,zidx,pidx,uidx


def solve_path_master(paths, scenarios, demand, rule="half", kappa=None, time_limit=600.0):
    b,zidx,pidx,uidx=build_path_master(paths,scenarios,demand,rule,kappa); obj,inte,bounds,cons=b.arrays(); t=time.perf_counter()
    try: res=milp(-obj,integrality=inte,bounds=bounds,constraints=cons,options={"time_limit":time_limit,"mip_rel_gap":0.05,"presolve":True})
    except MemoryError as exc: return None,{"incumbent":False,"message":f"MemoryError: {exc or 'bad allocation'}","solve_time_seconds":time.perf_counter()-t,"variables":len(obj),"binary_variables":int(inte.sum()),"constraints":len(cons.lb)}
    info={"incumbent":res.x is not None,"status":int(res.status),"message":str(res.message),"solve_time_seconds":time.perf_counter()-t,"variables":len(obj),"continuous_variables":int((inte==0).sum()),"binary_integer_variables":int(inte.sum()),"constraints":len(cons.lb),"mip_gap":getattr(res,"mip_gap",None),"best_bound":getattr(res,"mip_dual_bound",None),"node_count":getattr(res,"mip_node_count",None)}
    if res.x is None:return None,info
    chosen = {}
    for plot_id, plist in paths.items():
        scores = [res.x[zidx[(plot_id, j)]] for j in range(len(plist))]
        chosen[plot_id] = plist[int(np.argmax(scores))]
    plan=[r for plist in chosen.values() for r in plist]
    return plan,info
