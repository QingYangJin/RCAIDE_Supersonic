import argparse, hashlib, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
REPO=Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120")
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01")
sys.path.insert(0,str(REPO))
from research.concorde_metaopt.dreal001.geometry import solver_runner as sr
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stage",type=int,required=True,choices=[1,2])
    ap.add_argument("--limit",type=int,required=True)
    ap.add_argument("--label",required=True)
    a=ap.parse_args()
    dossier=REPO/"docs/evidence/dreal003/g2/g2_a5_dossier.md"
    verdict=json.loads((RUN/"a5_review/verdict.json").read_text(encoding="utf-8"))
    if verdict.get("verdict")!="G2_APPROVE": raise SystemExit("A5 verdict is not G2_APPROVE: %r"%verdict.get("verdict"))
    if verdict.get("dossier_sha256")!=sha(dossier): raise SystemExit("A5 dossier sha mismatch")
    pre_sha=sha(RUN/"g2_preregistration.json")
    go=json.loads((RUN/"g2_go_record_b01.json").read_text(encoding="utf-8"))
    if go["a5_verdict_sha256"]!=sha(RUN/"a5_review/verdict.json"): raise SystemExit("GO/A5 verdict mismatch")
    if go["a5_dossier_sha256"]!=sha(dossier): raise SystemExit("GO/dossier mismatch")
    if go["preregistration_sha256"]!=pre_sha: raise SystemExit("GO/preregistration drift: rebuilt prereg after GO")
    logpath=RUN/"g2_batch_runs.json"
    log=json.loads(logpath.read_text(encoding="utf-8")) if logpath.exists() else {"schema":"dreal003.g2_batch_runs.v1","batches":{},"runs":[]}
    b=log["batches"].setdefault(a.label,{"started_utc":now(),"wall_stop_s":3300,"case_timeout_s":600,"starts":0})
    elapsed=time.time()-datetime.strptime(b["started_utc"],"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    if b["starts"]+a.limit>24: raise SystemExit("B01 cap exceeded: %d + %d > 24"%(b["starts"],a.limit))
    if elapsed+600>3300: raise SystemExit("WALL_STOP_BEFORE_BATCH: elapsed %.1fs leaves no room for a 600s case"%elapsed)
    if a.stage==1:
        man=json.loads((RUN/"g2_stage1_manifest.json").read_text(encoding="utf-8"))
    else:
        man=json.loads((RUN/"g2_stage2_manifest.json").read_text(encoding="utf-8"))
    cases=man["cases"]
    selected=[c for c in cases if not (RUN/c["case_dir"].split("cases\\")[-1]/"case_result.json").exists() and not (RUN/c["case_dir"].split("cases\\")[-1]/"solver_attempts.jsonl").exists()] if False else [c for c in cases if not (Path(c["case_dir"])/"case_result.json").exists() and not (Path(c["case_dir"])/"solver_attempts.jsonl").exists()]
    if len(selected)<a.limit:
        print("ONLY_AVAILABLE",len(selected)); a_limit=len(selected)
    else: a_limit=a.limit
    consecutive=0; started=0
    for c in selected[:a_limit]:
        elapsed=time.time()-datetime.strptime(b["started_utc"],"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        if elapsed+600>3300:
            print("WALL_STOP",round(elapsed,1),flush=True); break
        case_dir=Path(c["case_dir"]); res=case_dir/"case_result.json"
        if res.exists() or (case_dir/"solver_attempts.jsonl").exists():
            print("SKIP_EXISTING",c["case_id"]); continue
        timeout=min(600.0,max(1.0,3300.0-elapsed))
        attempt="g2-"+c["case_id"]+"-01"
        t0=time.time()
        try:
            r=sr.run_case(str(case_dir/"plan.json"),str(case_dir/"approval.json"),attempt,dry_run=False,timeout_s=timeout)
        except Exception as e:
            r={"status":"EXCEPTION","error":type(e).__name__+": "+str(e)[:1000],"physical_solver_starts":0}
        wall=time.time()-t0
        proc=r.get("process") or {}
        row={"label":a.label,"stage":a.stage,"case_id":c["case_id"],"attempt_id":attempt,"status":r.get("status"),
             "exit_code":proc.get("exit_code"),"timed_out":proc.get("timed_out"),
             "wall_s":round(wall,3),"case_timeout_s":round(timeout,1),
             "physical_solver_starts":r.get("physical_solver_starts"),
             "internal_solver_cases":(r.get("internal") or {}).get("count"),
             "lift_match":r.get("lift_match"),"error":r.get("error"),
             "case_result":str(res) if res.exists() else None,
             "recorded_utc":now()}
        log["runs"].append(row); b["starts"]+=1; b["elapsed_s"]=round(elapsed,1)
        logpath.write_text(json.dumps(log,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print("RAN",json.dumps(row,ensure_ascii=False),flush=True)
        if row["status"]=="SOLVED" and row["physical_solver_starts"]==1:
            consecutive=0; started+=1
        else:
            consecutive+=1
            if row["status"]=="REFUSED" or row["status"]=="EXCEPTION" or consecutive>=2:
                print("STOP_CONDITION",row["status"],consecutive,flush=True); break
    print("DONE",json.dumps({"started":started,"batch_starts":b["starts"],"total_runs":len(log["runs"]),"consecutive":consecutive,"elapsed_s":round(elapsed,1)}),flush=True)
if __name__=="__main__": raise SystemExit(main())
