
import json,sys
p=r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/final_aircraft/optimized_design.json"
d=json.load(open(p,encoding="utf-8"))
print("keys:", list(d.keys()))
print("full_12d_vector:", d.get("full_12d_vector"))
print("gen:", d.get("generation_command"))
m=json.load(open(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/final_aircraft/optimized_geometry.json",encoding="utf-8"))
print("manifest keys:", list(m.keys()))
print("manifest x12:", m.get("x12"))
plan=json.load(open(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/cases/B02/o0-d10-refine/plan.json",encoding="utf-8"))
print("plan x12:", plan["design"]["x12"])
