import json,pathlib
p=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases/m160-d00-support-r1")
print([x.name for x in p.iterdir()][:30])
plan=json.loads((p/"plan.json").read_text()); app=json.loads((p/"approval.json").read_text()); spec=json.loads((p/"task_spec.json").read_text())
print(plan["batch_id"],plan["budget"],app["window"],spec["alpha_grid_deg"][:2],spec["alpha_grid_deg"][-2:],len(spec["alpha_grid_deg"]))
print("plan_sha",app["plan_sha256"])
