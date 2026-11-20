import argparse, json, sys
from pathlib import Path
REPO = Path(r"D:/RCAIDE/.worktrees/drecover001-20261117")
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.dreal001.geometry import solver_runner as sr
ap = argparse.ArgumentParser()
ap.add_argument("--plan", required=True)
ap.add_argument("--approval", required=True)
ap.add_argument("--attempt-id", required=True)
ap.add_argument("--timeout", type=float, default=1200)
a = ap.parse_args()
r = sr.run_case(a.plan, a.approval, a.attempt_id, dry_run=False, timeout_s=a.timeout)
print(json.dumps(r, indent=2, default=str)[:16000])
