
a=r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/geometry/sobol_best_solver.vsp3"
b=r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/ARM_SOBOL_BO/o1-d06-refine/o1-d06-refine.vsp3"
la=open(a,encoding="utf-8",errors="replace").read().splitlines()
lb=open(b,encoding="utf-8",errors="replace").read().splitlines()
diff=[(i,x,y) for i,(x,y) in enumerate(zip(la,lb)) if x!=y]
kinds={}
for i,x,y in diff:
    xs=x.strip()
    key=xs.split(">")[0]+">" if xs.startswith("<") and ">" in xs else "TEXT"
    kinds[key]=kinds.get(key,0)+1
for k,v in sorted(kinds.items(), key=lambda t:-t[1])[:25]:
    print(v,k)
print("--- samples ---")
shown=set()
for i,x,y in diff:
    xs=x.strip()
    key=xs.split(">")[0]+">" if xs.startswith("<") and ">" in xs else "TEXT"
    if key in shown: continue
    shown.add(key)
    print(key, "| A:",xs[:100], "| B:",y.strip()[:100])
    if len(shown)>14: break
