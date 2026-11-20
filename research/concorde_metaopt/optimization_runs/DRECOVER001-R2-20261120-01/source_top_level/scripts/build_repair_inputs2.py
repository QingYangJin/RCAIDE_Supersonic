import json, subprocess, sys, pathlib
root=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
auth=json.loads((root/"repair_authorization.json").read_text())
for c in auth["cases"][1:]:
    cd=root/"cases"/c["case_id"]
    if (cd/"plan.json").exists():
        print("SKIP",c["case_id"]); continue
    cmd=[sys.executable,str(root/"scripts"/"build_task_case.py"),
         "--case-id",c["case_id"],"--basename",c["case_id"].replace("-","_"),
         "--mach",str(c["mach"]),"--split",c["split"],"--partition",c["partition"],
         "--task-id",c["task_id"],"--design",c["design"],
         "--alpha-center",str(c["alpha_center"]),"--alpha-points","61","--alpha-step","0.005",
         "--max-starts","1","--batch-id",auth["batch_id"],
         "--window-token",auth["window"]["token"],"--window-end",auth["window"]["end_utc"],
         "--purpose","B01R repair for "+c["case_id"]+" (A5 PASS 2026-11-20T07:25:10Z)"]
    r=subprocess.run(cmd,text=True,capture_output=True)
    print("BUILD",c["case_id"],r.returncode,"plan",(cd/"plan.json").exists())
    if r.returncode!=0 or not (cd/"plan.json").exists():
        print(r.stdout[-1500:]); print(r.stderr[-3000:]); break
    plan=json.loads((cd/"plan.json").read_text()); spec=json.loads((cd/"task_spec.json").read_text())
    print("  batch",plan["batch_id"],"alphas",len(spec["alpha_grid_deg"]),spec["alpha_grid_deg"][0],spec["alpha_grid_deg"][-1])
