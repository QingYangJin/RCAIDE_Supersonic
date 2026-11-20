import json, subprocess, sys, pathlib
root=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
auth=json.loads((root/"repair_authorization.json").read_text())
for c in auth["cases"]:
    cmd=[sys.executable,str(root/"scripts"/"build_task_case.py"),
         "--case-id",c["case_id"],"--basename",c["case_id"].replace("-","_"),
         "--mach",str(c["mach"]),"--split",c["split"],"--partition",c["partition"],
         "--task-id",c["task_id"],"--design",c["design"],
         "--alpha-center",str(c["alpha_center"]),"--alpha-points","61","--alpha-step","0.005",
         "--max-starts","1","--batch-id",auth["batch_id"],
         "--window-token",auth["window"]["token"],"--window-end",auth["window"]["end_utc"],
         "--purpose","B01R repair for "+c["case_id"]+" (A5 PASS 2026-11-20T07:25:10Z)"]
    r=subprocess.run(cmd,text=True,capture_output=True)
    print("BUILD",c["case_id"],r.returncode)
    if r.returncode!=0:
        print(r.stdout[-2000:]); print(r.stderr[-3000:]); break
    out=json.loads(r.stdout)
    print("  plan",out["plan_sha256"],"geom",out["geometry_sha256"],"alpha0",out["alphas"][0],"alphaN",out["alphas"][-1])
