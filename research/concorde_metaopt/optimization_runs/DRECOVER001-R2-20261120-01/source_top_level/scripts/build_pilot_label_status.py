import json
from pathlib import Path
ROOT=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
rows=[]
for d in sorted((ROOT/"cases").iterdir()):
    if not d.is_dir(): continue
    cert=d/"admission_certificate.json"
    led=d/"solver_attempts.jsonl"
    if not led.is_file(): continue
    evs=[json.loads(l) for l in led.read_text(encoding="utf-8").splitlines() if l.strip()]
    ends=[e for e in evs if e.get("event")=="end"]
    status=ends[-1].get("status") if ends else "UNKNOWN"
    if cert.is_file():
        c=json.loads(cert.read_text(encoding="utf-8"))
        rows.append({"case_id":d.name,"solver_status":status,"label_status":"ADMITTED",
          "certificate":str(cert),"admission_id":c["admission_id"],"task_id":c["task_id"],
          "partition":c["partition"],"alpha_deg":c["alpha_deg"],"cl":c["cl"],"cdi":c["cdi"],
          "di_n":c["di_n"],"q_pa":c["q_pa"],"raw_sha256":c["raw_sha256"],
          "evidence_scope":c["evidence_scope"]})
    else:
        rows.append({"case_id":d.name,"solver_status":status,"label_status":"NULL_LABEL",
          "objective":None,"reason": "solver status %s; no admission certificate generated" % status,
          "certificate":None})
out={"schema":"drecover001.r2_pilot_label_status.v1","physical_solver_starts":3,
     "evidence_scope_default":"LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED",
     "cases":rows,
     "note":"Only cases with an admission certificate contribute labels; failed or unadmitted pilot cases remain null."}
(ROOT/"pilot_label_status.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
print(json.dumps(out,indent=2)[:6000])
