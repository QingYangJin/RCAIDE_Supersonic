import sys, json, traceback
from pathlib import Path
REPO=Path(r"D:/RCAIDE/.worktrees/drecover001-20261117")
sys.path.insert(0,str(REPO))
from research.concorde_metaopt.dreal001.geometry import solver_runner as sr
p=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases/m240-d01-support")
try:
    pre=sr.preflight(p/"plan.json",p/"approval.json","real-matrix-m240-d01-support-01")
    print("PRE_OK",json.dumps({k:pre[k] for k in ("plan_sha256","approval_sha256","basename","cwd")},indent=2))
except Exception as e:
    print("PRE_FAIL",type(e).__name__,str(e))
    traceback.print_exc()
