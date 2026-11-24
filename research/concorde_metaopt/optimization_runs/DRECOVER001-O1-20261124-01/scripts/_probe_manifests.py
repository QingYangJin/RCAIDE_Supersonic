
import json,glob
for p in [r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/baseline_geometry.json",
          r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/sobol_best_geometry.json",
          r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/supervised_best_geometry.json",
          r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/final_aircraft/baseline_geometry.json",
          r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/final_aircraft/optimized_geometry.json"]:
    d=json.load(open(p,encoding="utf-8"))
    print("==",p.split("/")[-3], p.split("/")[-1])
    print(" keys:", list(d.keys()))
    print(" design:", json.dumps(d.get("design"))[:300])
    print(" x12:", d.get("x12"))
    print(" solver exports:", list((d.get("solver") or {}).get("exports",{}).keys()))
