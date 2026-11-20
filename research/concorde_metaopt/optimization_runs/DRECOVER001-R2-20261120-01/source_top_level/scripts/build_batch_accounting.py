import json, pathlib, hashlib, math
from datetime import datetime, timezone
root=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
cases=root/"cases"
L=1333704.4

def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def polar_rows(p):
    lines=p.read_text(errors="replace").splitlines(); hi=None; header=None
    for i,l in enumerate(lines):
        q=l.split()
        if q[:4]==["Beta","Mach","AoA","Re/1e6"]: hi=i; header=q; break
    if hi is None: return []
    out=[]
    for l in lines[hi+1:]:
        q=l.split()
        if len(q)!=len(header): continue
        try: vals=[float(x) for x in q]
        except ValueError: continue
        out.append(dict(zip(header,vals)))
    return out

def deck_fields(p):
    d={}
    for l in p.read_text(errors="replace").splitlines():
        if "=" in l:
            k,v=l.split("=",1); d[k.strip()]=v.strip()
    return d

admitted=[]; nulls=[]; starts=[]
for p in sorted(cases.iterdir()):
    lp=p/"solver_attempts.jsonl"
    if not lp.exists(): continue
    rows=[json.loads(l) for l in lp.read_text().splitlines() if l.strip()]
    st=[r for r in rows if r.get("event")=="start"]; en=[r for r in rows if r.get("event")=="end"]
    starts.append({"case_id":p.name,"start_events":len(st),"end_events":len(en),
                   "attempt_ids":[r.get("attempt_id") for r in st],
                   "start_ts_utc":[r.get("start_ts_utc") for r in st]})
    cert=p/"admission_certificate.json"
    if cert.exists():
        c=json.loads(cert.read_text())
        admitted.append({"case_id":p.name,"task_id":c["task_id"],"design":c["design"],
                         "design_sha256":c["design_sha256"],"partition":c["partition"],
                         "admission_id":c["admission_id"],"di_n":c["di_n"],"cl":c["cl"],
                         "cdi":c["cdi"],"alpha_deg":c["alpha_deg"],"raw_sha256":c["raw_sha256"],
                         "evidence_scope":c["evidence_scope"]})
        continue
    resf=p/"case_result.json"
    if not resf.exists():
        nulls.append({"case_id":p.name,"task_id":None,"design":None,"partition":None,
                      "attempt_id":st[0].get("attempt_id") if st else None,
                      "start_ts_utc":st[0].get("start_ts_utc") if st else None,
                      "solver_success":None,"reason":"PROCESS_KILLED_BY_OUTER_TIMEOUT_NO_RESULT",
                      "best_lift_rel_error":None,"label":None,"reusable":False,
                      "note":"counted physical start; no end event; do not rerun under A5 14-start cap"})
        continue
    res=json.loads(resf.read_text()); base=res["attempt"]["basename"]
    deck=deck_fields(p/(base+".vspaero")); q=0.5*float(deck["Rho"])*float(deck["Vinf"])**2
    sref=float(deck["Sref"]); rows2=polar_rows(p/(base+".polar"))
    errs=[abs(q*sref*r["CLtot"]-L)/L for r in rows2]
    best=min(errs) if errs else None
    if p.name=="baseline-coarse":
        reason="POLAR_HAS_INVALID_ROWS"
    else:
        reason="NO_ACTUAL_ROW_WITHIN_LIFT_TOLERANCE"
    nulls.append({"case_id":p.name,"task_id":res["attempt"].get("task_id"),
                  "design":res["attempt"].get("x12"),"partition":None,
                  "attempt_id":res["attempt"].get("attempt_id"),
                  "start_ts_utc":res["attempt"].get("start_ts_utc"),
                  "solver_success":bool(res.get("process",{}).get("exit_code")==0),
                  "reason":reason,"best_lift_rel_error":best,"label":None,"reusable":False,
                  "note":"solver completed but no actual polar row meets 1e-3 lift tolerance; null label retained, not an admission"})

accounting={"schema":"drecover001.r2_batch_accounting.v1",
 "run_id":"DRECOVER001-R2-20261120-01","authorization_id":"AUTH-DRECOVER001-R2-20261120-01",
 "batch_id":"DRECOVER001-R2-20261120-01-B01",
 "physical_solver_starts_actual":sum(x["start_events"] for x in starts),
 "physical_solver_starts_completed":sum(x["end_events"] for x in starts),
 "retries_actual":0,"parallelism":1,"solver":"vspaero-3.55.0-v7.2.2-omp1",
 "planned_reserved_starts":24,"remaining_starts":24-sum(x["start_events"] for x in starts),
 "internal_solver_cases_actual_completed":23+13*15,
 "internal_solver_cases_note":"pilot 23 (baseline coarse 7 + refine 13 + admit 3) + 13 completed matrix cases x 15; interrupted m240-d01 internal cases unknown and not counted",
 "admitted_labels":admitted,
 "admitted_dataset_usable_designs":[
   {"task_id":"concorde-fixed-cruise-dreal001-real-v1","design":"d00","partition":"support","source":"baseline-admit-01","note":"baseline-refine-01 repeats d00 and is not a second design"},
   {"task_id":"concorde-fixed-cruise-dreal001-real-v1","design":"d01","partition":"support","source":"m202-d01-support"}],
 "null_labels":nulls,"starts":starts}
(root/"batch_accounting.json").write_text(json.dumps(accounting,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
(root/"null_labels.json").write_text(json.dumps({"schema":"drecover001.r2_null_labels.v1","run_id":accounting["run_id"],"null_labels":nulls},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print(json.dumps({"starts":accounting["physical_solver_starts_actual"],"completed":accounting["physical_solver_starts_completed"],"internal":accounting["internal_solver_cases_actual_completed"],"admitted":len(admitted),"nulls":len(nulls),"batch_accounting_sha256":sha(root/"batch_accounting.json"),"null_labels_sha256":sha(root/"null_labels.json")},indent=2))
