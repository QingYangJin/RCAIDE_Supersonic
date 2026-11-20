import json
from pathlib import Path
root=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
cases=root/"cases"
rows=[]
for d in sorted([p for p in cases.iterdir() if p.is_dir()]):
    def has(name): return (d/name).exists()
    rows.append({"case":d.name,"result":has("case_result.json"),
                 "polar":has("polar.txt") or any(d.glob("*.polar")),
                 "vspgeom":any(d.glob("*.vspgeom")),
                 "vspaero":any(d.glob("*.vspaero")),
                 "history":any(d.glob("*.history")),
                 "cert":has("admission_certificate.json")})
print("case_dirs",len(rows))
for r in rows: print(json.dumps(r,ensure_ascii=False))
print("top_json",[(p.name,p.stat().st_size) for p in sorted(root.glob("*.json"))])
print("certs",len(list(cases.glob("*/admission_certificate.json"))))
