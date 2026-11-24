import json, hashlib
from pathlib import Path
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
root = RUN/"cases"/"O0F"
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
for name in ["o0-final-baseline-r1-final","o0-final-baseline-wake16-final"]:
    d = root/name
    plan = json.loads((d/"plan.json").read_text(encoding="utf-8"))
    print("=== PLAN", name)
    print(json.dumps(plan, ensure_ascii=False, indent=1)[:3000])
    txt = (d/"case_result.json").read_text(encoding="utf-8", errors="replace")
    cr = json.loads(txt.replace("Infinity","1e999").replace("-Infinity","-1e999").replace("NaN","null"))
    ev = cr["evaluation"]
    print("--- EV subset", name)
    for k in ("cache_hit","cache_key","solver_config_sha256","tessellation","geometry_sha256","backend","status","evidence_tier","lift_match_status","alpha_list_deg","accounting","outputs","raw_artifacts"):
        print(k, "=", json.dumps(ev.get(k), ensure_ascii=False)[:600])
    print("--- files")
    for f in sorted(d.rglob("*")):
        if f.is_file():
            print("   ", f.relative_to(d), f.stat().st_size)
