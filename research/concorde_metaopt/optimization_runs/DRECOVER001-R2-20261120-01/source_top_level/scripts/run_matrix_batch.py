import json, sys, time
from pathlib import Path
REPO=Path(r"D:/RCAIDE/.worktrees/drecover001-20261117")
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
sys.path.insert(0,str(REPO))
from research.concorde_metaopt.dreal001.geometry import solver_runner as sr
cases=sorted([p for p in (RUN/"cases").iterdir() if p.name.startswith(("m160-","m180-","m220-","m240-","m202-")) and (p/"plan.json").exists()])
print("CASE_COUNT",len(cases),[p.name for p in cases],flush=True)
log=[]
prev_failed=False; consecutive_failures=0
for p in cases:
    case=p.name
    existing=p/"case_result.json"
    if existing.exists():
        try: old=json.loads(existing.read_text(encoding="utf-8"))
        except Exception: old={}
        if old.get("status")=="SOLVED" or old.get("physical_solver_starts")==1:
            print("SKIP_EXISTING",case,old.get("status"),flush=True)
            log.append({"case_id":case,"status":"SKIPPED_EXISTING","existing_status":old.get("status")})
            continue
    attempt="real-matrix-"+case+"-01"
    t0=time.time()
    try:
        r=sr.run_case(str(p/"plan.json"),str(p/"approval.json"),attempt,dry_run=False,timeout_s=1200)
    except Exception as e:
        r={"status":"EXCEPTION","error":type(e).__name__+": "+str(e)[:1000],"physical_solver_starts":0}
    wall=time.time()-t0
    proc=r.get("process") or {}
    pol=r.get("polar") or {}
    row={"case_id":case,"attempt_id":attempt,"status":r.get("status"),"exit_code":proc.get("exit_code"),
         "wall_s":round(wall,3),"physical_solver_starts":r.get("physical_solver_starts"),
         "internal_solver_cases":(r.get("internal") or {}).get("count"),
         "polar_sha256":(r.get("outputs") or {}).get("polar_sha256") or (r.get("outputs") or {}).get("polar"),
         "result_path":str(p/"case_result.json"),"error":r.get("error"),
         "eval_status":r.get("evaluation",{}).get("status") if isinstance(r.get("evaluation"),dict) else None}
    log.append(row)
    (RUN/"matrix_run_progress.json").write_text(json.dumps(log,indent=2),encoding="utf-8")
    print("RAN",json.dumps(row,ensure_ascii=False),flush=True)
    if row["status"]=="SOLVED":
        consecutive_failures=0
    else:
        consecutive_failures+=1
        if row["status"]=="REFUSED" or consecutive_failures>=2:
            print("STOP_CONDITION",row["status"],consecutive_failures,flush=True)
            break
print("DONE",json.dumps({"ran":len([x for x in log if x.get('physical_solver_starts')==1]),"solved":len([x for x in log if x['status']=='SOLVED']),"failed":len([x for x in log if x['status'] not in ('SOLVED','SKIPPED_EXISTING')])}),flush=True)
