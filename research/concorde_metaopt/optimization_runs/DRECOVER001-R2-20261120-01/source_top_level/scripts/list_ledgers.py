import json, pathlib
root=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases")
for p in sorted(root.iterdir()):
    lp=p/"solver_attempts.jsonl"
    if not lp.exists(): continue
    rows=[json.loads(l) for l in lp.read_text().splitlines() if l.strip()]
    starts=[r for r in rows if r.get("event")=="start"]; ends=[r for r in rows if r.get("event")=="end"]
    print(p.name, "start",len(starts),"end",len(ends), "result",(p/"case_result.json").exists(), "cert",(p/"admission_certificate.json").exists())
    if not ends:
        print("  last", rows[-1].get("event"), rows[-1].get("ts_utc"))
