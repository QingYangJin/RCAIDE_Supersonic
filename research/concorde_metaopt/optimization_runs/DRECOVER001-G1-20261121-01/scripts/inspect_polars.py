
import json
from pathlib import Path
R=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01/cases")
for d in sorted(R.iterdir()):
    f=d/"case_result.json"
    if not f.exists(): continue
    r=json.loads(f.read_text(encoding="utf-8")); ev=r.get("evaluation") or {}
    lm=ev.get("lift_match") or {}
    pts=lm.get("points") or []
    print(d.name, "target",lm.get("cl_target"),"min",lm.get("cl_min"),"max",lm.get("cl_max"),"n",len(pts), "alphas", (pts[0][0],pts[-1][0]) if pts else None)
