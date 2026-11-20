import json, subprocess, sys, pathlib, datetime
root=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
auth=json.loads((root/"repair_authorization.json").read_text())
now=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
for c in auth["cases"]:
    cid=c["case_id"]; cd=root/"cases"/cid
    upper=cid.upper().replace("-","_")
    audit_id="AUDIT-R2-B01R-"+upper
    r=subprocess.run([sys.executable,str(root/"scripts/audit_real_case.py"),"--case-dir",str(cd),
        "--audit-id",audit_id,"--reviewer","local-audit-script-v1",
        "--reviewer-role","SEPARATE_LOCAL_REIMPLEMENTATION_NOT_HUMAN_NOT_A5",
        "--created-utc",now],text=True,capture_output=True)
    print("AUDIT",cid,r.returncode)
    if r.returncode!=0:
        print(r.stdout[-1000:]); print(r.stderr[-2000:]); continue
    ao=json.loads(r.stdout); print("  row",ao["matched_lift_row"])
    result=json.loads((cd/"case_result.json").read_text())
    started=result["attempt"]["start_ts_utc"][:19]+"Z"
    adm_id="ADM-R2-B01R-"+upper
    r2=subprocess.run([sys.executable,str(root/"scripts/admit_case.py"),"--case-dir",str(cd),
        "--admission-id",adm_id,"--audit-ref",audit_id,
        "--evaluator-id","vspaero-3.55.0-v7.2.2-omp1","--solver-started-utc",started],
        text=True,capture_output=True)
    print("ADMIT",cid,r2.returncode)
    if r2.returncode!=0:
        print(r2.stdout[-1500:]); print(r2.stderr[-3000:])
    else:
        o=json.loads(r2.stdout); print("  ",{k:o[k] for k in ("status","di_n","cl","cdi","alpha_deg","raw_sha256")})
