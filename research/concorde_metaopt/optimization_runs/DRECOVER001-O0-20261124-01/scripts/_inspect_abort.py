import json, pathlib
run = pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
for d in sorted((run/"cases").iterdir()):
    files = sorted(p.name for p in d.iterdir())
    print("CASE", d.name, len(files))
    print("  files:", files[:20])
    cr = d/"case_result.json"
    if cr.exists():
        obj = json.loads(cr.read_text(encoding="utf-8"))
        print("  cr keys:", list(obj.keys()))
        print("  status:", obj.get("status"), "starts:", obj.get("physical_solver_starts"))
        ev = obj.get("evaluation") or {}
        print("  eval keys:", list(ev.keys()))
        rows = ev.get("rows") or []
        print("  rows:", len(rows), rows[:2])
        print("  lift_match:", ev.get("lift_match"))
    led = d/"ledger.json"
    for cand in ("solver_ledger.json","ledger.json","ledger"):
        if (d/cand).exists():
            print("  ledger:", cand)
