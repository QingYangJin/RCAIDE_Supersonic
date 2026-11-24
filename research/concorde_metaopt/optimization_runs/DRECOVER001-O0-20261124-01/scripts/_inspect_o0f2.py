import json, hashlib
from pathlib import Path
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
root = RUN/"cases"/"O0F"
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
for d in sorted(root.iterdir()):
    if not d.is_dir():
        continue
    files = [f for f in d.rglob("*") if f.is_file()]
    info = {"dir": d.name, "n_files": len(files),
            "bytes": sum(f.stat().st_size for f in files),
            "polar": [p.name for p in d.glob("*.polar")]}
    plan_p = d/"plan.json"
    cr_p = d/"case_result.json"
    if plan_p.is_file():
        plan = json.loads(plan_p.read_text(encoding="utf-8"))
        info["plan_sha256"] = sha(plan_p)
        for k in ("case_id","batch_id","n_wake_nodes","alpha_points","expected_internal_cases","physical_solver_starts_max","stage","tag","design_id","alpha_center_deg","cl_target"):
            if k in plan: info["plan."+k] = plan[k]
        info["plan_keys"] = sorted(plan.keys())
    if cr_p.is_file():
        info["case_result_sha256"] = sha(cr_p)
        txt = cr_p.read_text(encoding="utf-8", errors="replace")
        cr = json.loads(txt.replace("Infinity","1e999").replace("-Infinity","-1e999").replace("NaN","null"))
        info["cr_keys"] = sorted(cr.keys())
        for k in ("status","exit_code","wall_s","physical_solver_starts","internal_solver_cases","polar_rows","attempt_id"):
            if k in cr: info["cr."+k] = cr[k]
        ev = cr.get("evaluation") or {}
        info["cr.evaluation_keys"] = sorted(ev.keys())
        rows = ev.get("rows") or []
        info["cr.n_rows"] = len(rows)
        if rows:
            info["cr.row0"] = rows[0]
            info["cr.rowlast"] = rows[-1]
    print(json.dumps(info, ensure_ascii=False))
