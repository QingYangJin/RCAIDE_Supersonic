
import json, hashlib
from pathlib import Path
root = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/cases/O0F")
out=[]
for d in sorted(root.iterdir()):
    files=[p for p in d.rglob("*") if p.is_file()]
    polar=[p for p in files if p.suffix==".polar"]
    cr=[p for p in files if p.name=="case_result.json"]
    out.append({"case_id":d.name,"files":len(files),"bytes":sum(p.stat().st_size for p in files),
                "polar":len(polar),"case_result":len(cr),
                "has_solver_output": bool(polar or cr)})
print(json.dumps(out,indent=2))
print("dirs",len(out),"with_output",sum(1 for o in out if o["has_solver_output"]))
