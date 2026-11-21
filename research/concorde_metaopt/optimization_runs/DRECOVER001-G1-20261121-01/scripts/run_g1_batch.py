
import argparse, hashlib, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
REPO=Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120")
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01")
sys.path.insert(0,str(REPO))
from research.concorde_metaopt.dreal001.geometry import solver_runner as sr
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,required=True)
    ap.add_argument("--label",required=True)
    a=ap.parse_args()
    man=json.loads((RUN/"g1_case_manifest.json").read_text(encoding="utf-8"))
    pre=json.loads((RUN/"g1_preregistration.json").read_text(encoding="utf-8"))
    verdict=json.loads((RUN/"a5_review/verdict.json").read_text(encoding="utf-8"))
    dossier_sha=sha(REPO/"docs/evidence/dreal003/g1/g1_a5_dossier_compact.md")
    if a.limit<1 or a.limit>8: raise SystemExit("per mini-batch limit must be 1..8")
    if verdict.get("verdict")!="G1_APPROVE":
        raise SystemExit("A5 verdict is not G1_APPROVE: %r"%(verdict.get("verdict"),))
    if verdict.get("dossier_sha256")!=dossier_sha:
        raise SystemExit("A5 dossier sha mismatch: %s vs %s"%(verdict.get("dossier_sha256"),dossier_sha))
    logpath=RUN/"g1_batch_runs.json"
    log=json.loads(logpath.read_text(encoding="utf-8")) if logpath.exists() else {"schema":"dreal003.g1_batch_runs.v1","runs":[]}
    cases=man["cases"]
    selected=[c for c in cases if not (RUN/"cases"/c["case_id"]/"case_result.json").exists() and not (RUN/"cases"/c["case_id"]/"solver_attempts.jsonl").exists()]
    if len(selected)<a.limit:
        print("ONLY_AVAILABLE",len(selected)); a_limit=len(selected)
    else:
        a_limit=a.limit
    consecutive=0
    started=0
    for c in selected[:a_limit]:
        case_dir=RUN/"cases"/c["case_id"]
        res=case_dir/"case_result.json"
        if res.exists() or (case_dir/"solver_attempts.jsonl").exists():
            print("SKIP_EXISTING",c["case_id"]); continue
        attempt="g1-"+c["case_id"]+"-01"
        t0=time.time()
        try:
            r=sr.run_case(str(case_dir/"plan.json"),str(case_dir/"approval.json"),attempt,dry_run=False,timeout_s=1200)
        except Exception as e:
            r={"status":"EXCEPTION","error":type(e).__name__+": "+str(e)[:1000],"physical_solver_starts":0}
        wall=time.time()-t0
        proc=r.get("process") or {}
        row={"label":a.label,"case_id":c["case_id"],"attempt_id":attempt,"status":r.get("status"),
             "exit_code":proc.get("exit_code"),"timed_out":proc.get("timed_out"),
             "wall_s":round(wall,3),"physical_solver_starts":r.get("physical_solver_starts"),
             "internal_solver_cases":(r.get("internal") or {}).get("count"),
             "lift_match":r.get("lift_match"),"error":r.get("error"),
             "case_result":str(res) if res.exists() else None,
             "recorded_utc":now()}
        log["runs"].append(row); logpath.write_text(json.dumps(log,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print("RAN",json.dumps(row,ensure_ascii=False),flush=True)
        if row["status"]=="SOLVED" and row["physical_solver_starts"]==1:
            consecutive=0; started+=1
        else:
            consecutive+=1
            if row["status"]=="REFUSED" or row["status"]=="EXCEPTION" or consecutive>=2:
                print("STOP_CONDITION",row["status"],consecutive,flush=True); break
    print("DONE",json.dumps({"started":started,"selected":a_limit,"total_runs":len(log["runs"]),"consecutive":consecutive}),flush=True)
if __name__=="__main__": raise SystemExit(main())
