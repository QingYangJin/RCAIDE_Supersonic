import json, pathlib, re, math
root=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
auth=json.loads((root/"repair_authorization.json").read_text())
L=1333704.4
def rows(path):
    lines=path.read_text(errors="ignore").splitlines(); h=None
    for i,l in enumerate(lines):
        p=l.split()
        if p[:4]==["Beta","Mach","AoA","Re/1e6"]: h=p; start=i+1; break
    out=[]
    for l in lines[start:]:
        p=l.split()
        if len(p)!=len(h): continue
        try: v=[float(x) for x in p]
        except: continue
        out.append(dict(zip(h,v)))
    return out
for c in auth["cases"]:
    cd=root/"cases"/c["case_id"]; base=json.loads((cd/"case_result.json").read_text())["attempt"]["basename"]
    deck={}
    for l in (cd/(base+".vspaero")).read_text().splitlines():
        m=re.fullmatch(r"\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*?)\s*",l)
        if m: deck[m.group(1)]=m.group(2)
    q=0.5*float(deck["Rho"])*float(deck["Vinf"])**2; sref=float(deck["Sref"]); ct=L/(q*sref)
    rs=rows(cd/(base+".polar"))
    best=min((abs(q*sref*r["CLtot"]-L)/L,r["AoA"],r["CLtot"],r["CDi"]) for r in rs)
    print(c["case_id"],"q",round(q,6),"clt",round(ct,8),"rows",len(rs),"best",best)
