import json, pathlib, numpy as np
root=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases")
L=1333704.4
cases=["m160-d00-support","m160-d02-query","m180-d00-support","m180-d02-query","m202-d02-query","m240-d00-support","m240-d02-query"]
for name in cases:
    p=root/name; res=json.loads((p/"case_result.json").read_text()); base=res["attempt"]["basename"]
    txt=(p/(base+".polar")).read_text().splitlines(); hi=None
    for i,l in enumerate(txt):
        q=l.split()
        if q[:4]==["Beta","Mach","AoA","Re/1e6"]: hi=i; header=q; break
    rows=[]
    for l in txt[hi+1:]:
        q=l.split()
        if len(q)!=len(header): continue
        try: vals=[float(x) for x in q]
        except ValueError: continue
        rows.append(dict(zip(header,vals)))
    d={}
    for l in (p/(base+".vspaero")).read_text().splitlines():
        if "=" in l:
            k,v=l.split("=",1); d[k.strip()]=v.strip()
    q=0.5*float(d["Rho"])*float(d["Vinf"])**2; sref=float(d["Sref"]); ct=L/(q*sref)
    a=np.array([r["AoA"] for r in rows]); cl=np.array([r["CLtot"] for r in rows])
    # linear local slope from last 2, and quadratic fit
    slope=(cl[-1]-cl[-2])/(a[-1]-a[-2])
    lin=a[-1]+(ct-cl[-1])/slope
    coef=np.polyfit(a,cl,2)
    roots=np.roots([coef[0],coef[1],coef[2]-ct]); real=[float(r.real) for r in roots if abs(r.imag)<1e-9]
    quad=min(real,key=lambda x:abs(x-a.mean())) if real else float("nan")
    print("%-22s a0=%.4f cl0=%.6f ct=%.6f slope=%.6f lin=%.4f quad=%.4f d=%.4f" % (name,a[-1],cl[-1],ct,slope,lin,quad,quad-lin))
