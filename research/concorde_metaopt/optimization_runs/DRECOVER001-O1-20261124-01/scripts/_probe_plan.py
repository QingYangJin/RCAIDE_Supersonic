
import json
p=r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/ARM_SOBOL_BO/o1-d06-refine/plan.json"
d=json.load(open(p,encoding="utf-8"))
print(json.dumps(d, ensure_ascii=False, indent=1)[:4000])
