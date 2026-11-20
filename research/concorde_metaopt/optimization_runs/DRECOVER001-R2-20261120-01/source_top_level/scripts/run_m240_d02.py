import sys, json, time
from pathlib import Path
REPO=Path(r"D:/RCAIDE/.worktrees/drecover001-20261117")
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
sys.path.insert(0,str(REPO))
from research.concorde_metaopt.dreal001.geometry import solver_runner as sr
p=RUN/"cases/m240-d02-query"
attempt="real-matrix-m240-d02-query-01"
if (p/"case_result.json").exists():
    print("EXISTING", (p/"case_result.json").read_text()[:1000]); raise SystemExit(0)
t0=time.time()
r=sr.run_case(str(p/"plan.json"),str(p/"approval.json"),attempt,dry_run=False,timeout_s=1200)
wall=time.time()-t0
proc=r.get("process") or {}
row={"case_id":"m240-d02-query","attempt_id":attempt,"status":r.get("status"),"exit_code":proc.get("exit_code"),
     "wall_s":round(wall,3),"physical_solver_starts":r.get("physical_solver_starts"),
     "internal_solver_cases":(r.get("internal") or {}).get("count"),
     "outputs":r.get("outputs"),"evaluation":r.get("evaluation"),"refusal_reason":r.get("refusal_reason")}
print(json.dumps(row,indent=2,default=str)[:8000])
(RUN/"matrix_m240_d02_result.json").write_text(json.dumps(row,indent=2,default=str),encoding="utf-8")
