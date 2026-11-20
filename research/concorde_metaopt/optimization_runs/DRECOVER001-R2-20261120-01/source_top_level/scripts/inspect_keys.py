import json,pathlib
root=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
r=json.loads((root/"cases/m160-d00-support-r1/case_result.json").read_text())
print(json.dumps(r.get("attempt"),indent=2)[:2000])
print("top keys",list(r.keys()))
b=json.loads((root/"cases/baseline-admit-01/admission_manifest.json").read_text())
print("evaluator",b["evaluator_id"],"started",b["solver_started_utc"])
