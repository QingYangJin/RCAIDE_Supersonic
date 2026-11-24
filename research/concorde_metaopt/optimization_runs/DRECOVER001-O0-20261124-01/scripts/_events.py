import json, pathlib
p = pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/cases/o0-d00-coarse/solver_attempts.jsonl")
for line in p.read_text(encoding="utf-8").splitlines():
    o = json.loads(line)
    print(repr(o.get("event")), o.get("status"), o.get("physical_solver_starts"), o.get("internal_solver_cases"), o.get("exit_code"))
