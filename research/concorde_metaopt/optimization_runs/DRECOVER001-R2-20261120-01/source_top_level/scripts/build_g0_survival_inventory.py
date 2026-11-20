import json, hashlib
from pathlib import Path
from datetime import datetime, timezone
root=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
cases=root/"cases"
rows=[]
for d in sorted([p for p in cases.iterdir() if p.is_dir()]):
    def has(name): return (d/name).exists()
    rows.append({"case_id":d.name,
                 "case_result":has("case_result.json"),
                 "polar":has("polar.txt") or any(d.glob("*.polar")),
                 "vspgeom":any(d.glob("*.vspgeom")),
                 "vspaero":any(d.glob("*.vspaero")),
                 "history":any(d.glob("*.history")),
                 "certificate":has("admission_certificate.json")})
allfiles=[p for p in root.rglob("*") if p.is_file()]
out={
 "schema":"dreal003.g0_survival_inventory.v1",
 "generated_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
 "run_root":str(root),
 "run_id":"DRECOVER001-R2-20261120-01",
 "physical_solver_starts_actual":24,
 "internal_solver_cases_actual":645,
 "completed":23,
 "interrupted":1,
 "retries":0,
 "parallel":1,
 "certificates":10,
 "deduplicated_usable_labels":9,
 "null_labels":14,
 "case_dirs":len(rows),
 "file_count":len(allfiles),
 "total_bytes":sum(p.stat().st_size for p in allfiles),
 "top_level_json":[{"name":p.name,"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(root.glob("*.json"))],
 "cases":rows,
 "interrupted_cases":[r["case_id"] for r in rows if not r["case_result"] or not r["polar"]],
 "missing_certificate_cases":[r["case_id"] for r in rows if not r["certificate"]],
 "note":"Local inventory only; no file has been uploaded to GitHub yet. m240-d01-support has partial raw files but no case_result/polar/certificate."
}
outp=root/"g0_survival_inventory.json"
outp.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print(json.dumps({k:out[k] for k in ["case_dirs","file_count","total_bytes","completed","interrupted","certificates","interrupted_cases","missing_certificate_cases","generated_utc"]},ensure_ascii=False,indent=2))
print("out",outp,"sha256",hashlib.sha256(outp.read_bytes()).hexdigest())
