import json, subprocess, sys, pathlib
root = pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
case = root/"cases"/"m202-d01-support"
res = json.loads((case/"case_result.json").read_text())
started = res["attempt"]["start_ts_utc"]
started = started[:19] + "Z"
b = subprocess.run([sys.executable, str(root/"scripts"/"admit_case.py"), "--case-dir", str(case), "--admission-id", "ADM-R2-MATRIX-M202-D01-SUPPORT", "--audit-ref", "AUDIT-R2-MATRIX-M202-D01-SUPPORT", "--evaluator-id", "vspaero-3.55.0-v7.2.2-omp1", "--solver-started-utc", started], text=True, capture_output=True)
print("ADMIT", b.returncode); print(b.stdout[-3000:]); print(b.stderr[-3000:])
