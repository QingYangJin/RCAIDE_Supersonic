
import json
p=r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/ARM_SOBOL_BO/o1-d06-refine/case_result.json"
d=json.load(open(p,encoding="utf-8"))
print(list(d.keys()))
for k in ("geometry","design","design_hash","x12","geometry_sha256","outputs","admission"):
    if k in d:
        v=d[k]
        s=json.dumps(v,ensure_ascii=False)
        print("==",k,"==",s[:900])
