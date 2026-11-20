import json, pathlib, math
root=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases")
for p in sorted(root.iterdir()):
    if not (p/"case_result.json").exists() or p.name.startswith("baseline"): continue
    res=json.loads((p/"case_result.json").read_text())
    base=res["attempt"]["basename"]
    pol=p/(base+".polar"); deck=p/(base+".vspaero")
    if not pol.exists(): print(p.name,"NO_POLAR"); continue
    text=pol.read_text(errors="replace").splitlines()
    hi=None
    for i,l in enumerate(text):
        q=l.split()
        if q[:4]==["Beta","Mach","AoA","Re/1e6"]: hi=i; header=q; break
    rows=[]
    for l in text[hi+1:]:
        q=l.split()
        if len(q)!=len(header): continue
        try: vals=[float(x) for x in q]
        except ValueError: continue
        rows.append(dict(zip(header,vals)))
    d={}
    for l in deck.read_text().splitlines():
        if "=" in l:
            k,v=l.split("=",1); d[k.strip()]=v.strip()
    q=0.5*float(d["Rho"])*float(d["Vinf"])**2; sref=float(d["Sref"]); L=1333704.4
    best=min((abs(q*sref*r["CLtot"]-L)/L,r["AoA"],r["CLtot"],r["CDi"]) for r in rows)
    print("%-24s rows=%2d q=%10.2f cl_t=%.5f best_err=%.6f alpha=%.4f cl=%.6f cdi=%.8f" % (p.name,len(rows),q,L/(q*sref),best[0],best[1],best[2],best[3]))
