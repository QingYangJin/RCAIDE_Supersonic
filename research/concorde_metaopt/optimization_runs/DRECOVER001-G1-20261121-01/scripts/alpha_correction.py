
import json
from pathlib import Path
R=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01/cases")
for d in sorted(R.iterdir()):
    f=d/"case_result.json"
    if not f.exists(): continue
    r=json.loads(f.read_text(encoding="utf-8")); lm=(r.get("evaluation") or {}).get("lift_match") or {}
    pts=lm["points"]; x=[p[0] for p in pts]; y=[p[1] for p in pts]
    n=len(x); mx=sum(x)/n; my=sum(y)/n
    s=sum((a-mx)*(b-my) for a,b in zip(x,y))/sum((a-mx)**2 for a in x)
    a0=my-s*mx; at=(lm["cl_target"]-a0)/s
    print(d.name,"slope %.6f"%s,"alpha_t %.4f"%at,"grid0 %.4f"%x[0],"delta %.4f"%(at-x[0]))
