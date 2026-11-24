
import json,glob,os
p=r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01/dataset/a0_dataset.json"
d=json.load(open(p,encoding='utf-8'))
print({k:(v if not isinstance(v,(list,dict)) else type(v).__name__) for k,v in d.items()})
print("rows",d["rows"],"certs",d["certificates"],"starts",d["physical_solver_starts_actual"])
print("aliases",d["task_aliases"])
print("tasks:")
for t in d["tasks"]: print(" ",t["task_id"],t["split"],t["mach"],t["dynamic_pressure_pa"],t["physics_sha256"][:12])
ck=r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01/training/checkpoints"
fs=sorted(glob.glob(ck+"/*.npz"))
print("checkpoints",len(fs))
for f in fs:
    if "_k3_" in f and "_seed7" in f: print(" ",os.path.basename(f),os.path.getsize(f))
nj=r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01/training/a0_normalizer.json"
n=json.load(open(nj))
print("norm keys",list(n.keys()))
print("x_scale",n["x_scale"])
print("mean",n["y_mean"],"scale",n["y_scale"])
g=json.load(open(r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01/training/a0_grid_search.json"))
print("grid keys",list(g.keys()))
