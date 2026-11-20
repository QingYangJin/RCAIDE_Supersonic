import json, subprocess, sys, pathlib, datetime
root = pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
case = root/"cases"/"m202-d01-support"
created = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
audit_id = "AUDIT-R2-MATRIX-M202-D01-SUPPORT"
adm_id = "ADM-R2-MATRIX-M202-D01-SUPPORT"
a = subprocess.run([sys.executable, str(root/"scripts"/"audit_real_case.py"), "--case-dir", str(case), "--audit-id", audit_id, "--reviewer", "local-audit-script-v1", "--reviewer-role", "SEPARATE_LOCAL_REIMPLEMENTATION_NOT_HUMAN_NOT_A5", "--created-utc", created], text=True, capture_output=True)
print("AUDIT", a.returncode); print(a.stdout[-2000:]); print(a.stderr[-2000:])
if a.returncode == 0:
    res = json.loads((case/"case_result.json").read_text())
    b = subprocess.run([sys.executable, str(root/"scripts"/"admit_case.py"), "--case-dir", str(case), "--admission-id", adm_id, "--audit-ref", audit_id, "--evaluator-id", "vspaero-3.55.0-v7.2.2-omp1", "--solver-started-utc", res["attempt"]["start_ts_utc"]], text=True, capture_output=True)
    print("ADMIT", b.returncode); print(b.stdout[-3000:]); print(b.stderr[-2000:])
