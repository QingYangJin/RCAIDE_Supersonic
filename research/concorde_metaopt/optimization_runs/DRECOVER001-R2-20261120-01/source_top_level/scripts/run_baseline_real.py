import json, sys
from pathlib import Path
REPO = Path(r"D:/RCAIDE/.worktrees/drecover001-20261117")
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.dreal001.geometry import solver_runner as sr
case = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases/baseline-coarse")
r = sr.run_case(case/"plan.json", case/"approval.json", "real-baseline-coarse-01", dry_run=False, timeout_s=1200)
print(json.dumps(r, indent=2, default=str)[:12000])
