"""Summarise the A0 ablation into a single markdown table for the receipt."""
import csv, json
from pathlib import Path
A0 = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01")
rows = list(csv.DictReader(open(A0/"tables/a0_arm_metrics.csv", encoding="utf-8")))
agg = {}
for r in rows:
    key = (r["arm"], int(r["k"]), r["split"])
    agg.setdefault(key, []).append(float(r["mae_n"]))
arms = ["RANDOM_INIT","POOLED_PRETRAIN_12D","COND_SUPERVISED_16D","FOMAML_12D","COND_FOMAML_16D"]
print("| 臂 | K=0 val | K=0 test | K=1 val | K=1 test | K=3 val | K=3 test |")
print("| --- | --- | --- | --- | --- | --- | --- |")
for a in arms:
    cells = []
    for k in (0,1,3):
        for s in ("val","test"):
            v = agg.get((a,k,s), [None])
            cells.append("%.0f" % (sum(v)/len(v)) if v and v[0] is not None else "-")
    print("| %s | %s |" % (a, " | ".join(cells)))
