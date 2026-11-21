
import hashlib,json
from pathlib import Path
R=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01")
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
man=json.loads((R/"g1_case_manifest.json").read_text(encoding="utf-8"))
started=[]; bad=[]
for c in man["cases"]:
    d=R/"cases"/c["case_id"]
    if (d/"solver_attempts.jsonl").exists() or (d/"case_result.json").exists():
        started.append(c["case_id"]); continue
    if not (d/"plan.json").exists(): bad.append((c["case_id"],"missing plan")); continue
    if sha(d/"plan.json")!=c["plan_sha256"]: bad.append((c["case_id"],"plan sha"))
    if sha(d/"task_spec.json")!=c["task_spec_sha256"]: bad.append((c["case_id"],"spec sha"))
    if sha(d/(c["case_id"]+".vspgeom"))!=c["vspgeom_sha256"]: bad.append((c["case_id"],"geom sha"))
    spec=json.loads((d/"task_spec.json").read_text(encoding="utf-8"))
    if len(spec["alpha_grid_deg"])!=17: bad.append((c["case_id"],"alpha count"))
    if not (spec["alpha_center_deg"]-0.24-1e-9 <= min(spec["alpha_grid_deg"]) and max(spec["alpha_grid_deg"]) <= spec["alpha_center_deg"]+0.24+1e-9): bad.append((c["case_id"],"alpha span"))
print(json.dumps({"started":started,"unstarted":24-len(started),"bad":bad},indent=2))
