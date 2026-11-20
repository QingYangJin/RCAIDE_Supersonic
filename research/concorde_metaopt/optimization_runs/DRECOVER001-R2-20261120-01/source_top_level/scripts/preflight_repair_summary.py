import json,sys,pathlib
REPO=pathlib.Path(r"D:/RCAIDE/.worktrees/drecover001-20261117"); sys.path.insert(0,str(REPO))
from research.concorde_metaopt.dreal001.geometry import solver_runner as sr
root=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
auth=json.loads((root/"repair_authorization.json").read_text())
ok=0
for c in auth["cases"]:
    cd=root/"cases"/c["case_id"]
    try:
        sr.preflight(cd/"plan.json",cd/"approval.json","preflight-repair-"+c["case_id"]); ok+=1; print("OK",c["case_id"])
    except Exception as e:
        print("FAIL",c["case_id"],type(e).__name__,e)
print("passed",ok,"of",len(auth["cases"]))
