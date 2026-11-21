
import csv, hashlib, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
REPO=Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120")
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01")
CASES=RUN/"cases"
AUDIT_SCRIPT=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py")
ADMIT_SCRIPT=RUN/"scripts/admit_g1_case.py"
PY=sys.executable
def sha(p):
    h=hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()
def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def run(cmd):
    p=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace")
    return p.returncode,p.stdout,p.stderr
man=json.loads((RUN/"g1_case_manifest.json").read_text(encoding="utf-8"))
rows=[]; admitted=[]; nulls=[]; starts=[]
for c in man["cases"]:
    case_id=c["case_id"]; d=CASES/case_id
    spec=json.loads((d/"task_spec.json").read_text(encoding="utf-8"))
    resf=d/"case_result.json"; certf=d/"admission_certificate.json"
    ledgerf=d/"solver_attempts.jsonl"
    if not resf.exists() and not ledgerf.exists():
        continue
    starts_ev=[]; ends=[]; internal=0
    if ledgerf.exists():
        for line in ledgerf.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            ev=json.loads(line)
            if ev.get("event")=="start": starts_ev.append(ev)
            elif ev.get("event")=="end":
                ends.append(ev); internal+=int(ev.get("internal_solver_cases") or 0)
    base={"case_id":case_id,"task_id":spec["task_id"],"split":spec["split"],
          "partition":spec["partition"],"design":spec["design"],"mach":spec["mach"],
          "alpha_center_deg":spec["alpha_center_deg"],"q_pa":spec["dynamic_pressure_pa"],
          "sref_m2":spec["sref_m2"],"cl_target":spec["cl_target"],
          "physical_starts":len(starts_ev),"internal_cases":internal}
    if not resf.exists():
        row=dict(base,status="NO_RESULT",solver_status=None,exit_code=None,lift_match_status=None,
                 di_n=None,cl=None,cdi=None,alpha_deg=None,rel_lift_error=None,
                 wall_s=None,cert_status=None,evidence_scope=None,failure_kind="NO_RESULT",
                 detail="no case_result.json; counted start(s) without a process result" if starts_ev else "not started")
        rows.append(row); nulls.append(row); continue
    res=json.loads(resf.read_text(encoding="utf-8"))
    ev=res.get("evaluation") or {}
    proc=res.get("process") or {}
    lm=ev.get("lift_match") or {}
    row=dict(base,status=ev.get("status") or res.get("status"),solver_status=res.get("status"),
             exit_code=proc.get("exit_code"),lift_match_status=ev.get("lift_match_status"),
             di_n=(ev.get("objective") or {}).get("value"),cl=ev.get("cl"),cdi=ev.get("cdi"),
             alpha_deg=ev.get("alpha_deg"),rel_lift_error=lm.get("rel_error"),
             wall_s=proc.get("wall_s"),cert_status=None,evidence_scope=None,
             failure_kind=None,detail=None)
    if certf.exists():
        cert=json.loads(certf.read_text(encoding="utf-8"))
        row.update(cert_status=cert.get("status"),di_n=cert.get("di_n"),cl=cert.get("cl"),
                   cdi=cert.get("cdi"),alpha_deg=cert.get("alpha_deg"),
                   evidence_scope=cert.get("evidence_scope"))
        if cert.get("status")=="ok":
            admitted.append(dict(row,admission_id=cert.get("admission_id"),
                                 design_sha256=cert.get("design_sha256"),
                                 raw_sha256=cert.get("raw_sha256"),
                                 artifact_sha256=cert.get("artifact_sha256")))
            rows.append(row); continue
    if row["status"]=="SOLVED" and proc.get("exit_code")==0:
        audit_id="g1-audit-"+case_id
        rc,out,err=run([PY,str(AUDIT_SCRIPT),"--case-dir",str(d),"--audit-id",audit_id,
                        "--reviewer","lead-local-script","--reviewer-role",
                        "SEPARATE_LOCAL_REIMPLEMENTATION_NOT_HUMAN_NOT_A5",
                        "--created-utc",now(),"--verdict","ADMIT_REAL_LABEL"])
        if rc==0:
            started=(res.get("attempt") or {}).get("start_ts_utc") or ""
            started=started[:19]+"Z" if started else ""
            rc2,out2,err2=run([PY,str(ADMIT_SCRIPT),"--case-dir",str(d),
                               "--admission-id","g1-adm-"+case_id,"--audit-ref",audit_id,
                               "--evaluator-id","vspaero-3.55.0-v7.2.2-omp1",
                               "--solver-started-utc",started,
                               "--partition",spec["partition"],"--split",spec["split"],
                               "--task-spec",str(d/"task_spec.json")])
            if rc2==0 and certf.exists():
                cert=json.loads(certf.read_text(encoding="utf-8"))
                row.update(cert_status=cert.get("status"),di_n=cert.get("di_n"),
                           cl=cert.get("cl"),cdi=cert.get("cdi"),
                           alpha_deg=cert.get("alpha_deg"),
                           evidence_scope=cert.get("evidence_scope"))
                if cert.get("status")=="ok":
                    admitted.append(dict(row,admission_id=cert.get("admission_id"),
                                         design_sha256=cert.get("design_sha256"),
                                         raw_sha256=cert.get("raw_sha256"),
                                         artifact_sha256=cert.get("artifact_sha256")))
                    rows.append(row); continue
            row.update(failure_kind="ADMISSION_FAILED",detail=(err2 or out2)[-800:])
        else:
            row.update(failure_kind="AUDIT_FAILED",detail=(err or out)[-800:])
    else:
        row.update(failure_kind="SOLVER_NOT_SUCCESS",
                   detail=(res.get("status") or "unknown")+"; exit="+str(proc.get("exit_code")))
    rows.append(row); nulls.append(row)
# CSV
def write_csv(path, items, fields):
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader()
        for item in items: w.writerow(item)
fields=["case_id","task_id","split","partition","design","mach","alpha_center_deg","q_pa",
        "sref_m2","cl_target","status","lift_match_status","di_n","cl","cdi","alpha_deg",
        "rel_lift_error","physical_starts","internal_cases","wall_s","cert_status",
        "evidence_scope","failure_kind","detail"]
write_csv(RUN/"all_evaluations.csv",rows,fields)
write_csv(RUN/"admitted_labels.csv",admitted,fields+["admission_id","design_sha256","raw_sha256","artifact_sha256"])
write_csv(RUN/"failed_or_null.csv",nulls,fields)
# ledger
ledger_rows=[]
for c in man["cases"]:
    d=CASES/c["case_id"]
    for line in (d/"solver_attempts.jsonl").read_text(encoding="utf-8").splitlines() if (d/"solver_attempts.jsonl").exists() else []:
        if line.strip():
            ev=json.loads(line); ev["case_id"]=c["case_id"]
            ledger_rows.append(ev)
write_csv(RUN/"attempt_ledger.csv",ledger_rows,["case_id","event","attempt_id","task_id","start_ts_utc","end_ts_utc","status","exit_code","physical_solver_starts","internal_solver_cases","wall_s","plan_sha256","approval_sha256","window_token"])
actual=sum(1 for r in ledger_rows if r.get("event")=="start")
completed=sum(1 for r in ledger_rows if r.get("event")=="end")
internal=sum(int(r.get("internal_solver_cases") or 0) for r in ledger_rows if r.get("event")=="end")
accounting={"schema":"dreal003.g1_batch_accounting.v1","run_id":man["run_id"],
 "authorization_id":man["authorization_id"],"batch_id":man["batch_id"],
 "physical_solver_starts_actual":actual,"physical_solver_starts_completed":completed,
 "retries_actual":0,"parallelism":1,"planned_reserved_starts":24,
 "remaining_starts":24-actual,"internal_solver_cases_actual":internal,
 "successful_cases":sum(1 for r in rows if r["status"]=="SOLVED"),
 "admitted_labels":len(admitted),"null_labels":len(nulls),
 "valid_label_rate":(len(admitted)/completed) if completed else 0.0,
 "cases":rows,"admitted":admitted,"nulls":nulls,
 "generated_utc":now(),"physical_zero_before_g1":True}
(RUN/"batch_accounting.json").write_text(json.dumps(accounting,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
(RUN/"null_labels.json").write_text(json.dumps({"schema":"dreal003.g1_null_labels.v1","nulls":nulls},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print(json.dumps({"starts":actual,"completed":completed,"internal":internal,"admitted":len(admitted),
 "nulls":len(nulls),"valid_rate":accounting["valid_label_rate"],
 "batch_accounting_sha256":sha(RUN/"batch_accounting.json"),
 "admitted_labels_sha256":sha(RUN/"admitted_labels.csv")},indent=2))
