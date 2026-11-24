
import json
from pathlib import Path
p=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/cases/B02/o0-d10-refine/plan.json")
plan=json.load(open(p,encoding="utf-8"))
print("case x12:", plan["design"]["x12"])
m=json.load(open(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/final_aircraft/optimized_geometry.json",encoding="utf-8"))
print("manifest x12:", m["x12"])
for i,(a,b) in enumerate(zip(plan["design"]["x12"], m["x12"])):
    print(i, repr(a), repr(b), "d=", a-b)
print("---- result record best x12")
res=json.load(open(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/o0_result_B02.json",encoding="utf-8"))
def find(o, key="x12"):
    if isinstance(o,dict):
        for k,v in o.items():
            if k==key and isinstance(v,list) and len(v)==12: print("found x12 at", key, v)
            find(v,key)
    elif isinstance(o,list):
        for v in o[:50]: find(v,key)
find(res)
