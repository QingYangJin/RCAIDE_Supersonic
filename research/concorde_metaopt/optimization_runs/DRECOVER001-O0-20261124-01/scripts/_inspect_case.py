import json, pathlib
d = pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/cases/o0-d00-coarse")
print(sorted(p.name for p in d.iterdir()))
p = d/"solver_attempts.jsonl"
if p.exists():
    for line in p.read_text(encoding="utf-8").splitlines():
        o = json.loads(line)
        print("attempt keys:", list(o.keys()))
        print("status:", o.get("status"), "exit:", o.get("exit_code"), "starts:", o.get("physical_solver_starts"))
        print("wall:", o.get("wall_s"), "internal:", o.get("internal_solver_cases"))
cr = json.loads((d/"case_result.json").read_text(encoding="utf-8"))
print("process:", {k: cr["process"].get(k) for k in ("exit_code","timed_out","wall_s","status")})
print("outputs:", list(cr["outputs"].keys()) if isinstance(cr["outputs"], dict) else cr["outputs"])
print("polar:", {k: cr["polar"].get(k) for k in ("row_count","format_version")} if isinstance(cr["polar"], dict) else cr["polar"])
ev = cr["evaluation"]
print("eval status:", ev.get("status"), "objective:", ev.get("objective"))
print("accounting:", ev.get("accounting"))
