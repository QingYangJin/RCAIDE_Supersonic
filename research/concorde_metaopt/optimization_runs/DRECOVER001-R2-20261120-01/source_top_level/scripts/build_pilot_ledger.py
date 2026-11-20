import json, re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
AUTH = json.loads((ROOT/"authorization.json").read_text(encoding="utf-8"))
L_REF = 1333704.4
RHO = 0.1153178340089936
V_BASE = 596.0373972278921

def polar_rows(case_dir):
    polar = next(case_dir.glob("*.polar"), None)
    if not polar: return 0
    lines = polar.read_text(encoding="utf-8", errors="replace").splitlines()
    rows = 0
    for line in lines:
        s=line.strip()
        if s and (s[0].isdigit() or s[0] in "+-."):
            rows += 1
    return rows

events=[]; cases=[]
for case_dir in sorted(p for p in (ROOT/"cases").iterdir() if p.is_dir()):
    ledger = case_dir/"solver_attempts.jsonl"
    if not ledger.is_file(): continue
    evs=[json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    starts=[e for e in evs if e.get("event")=="start"]
    ends=[e for e in evs if e.get("event")=="end"]
    if not starts: continue
    spec_p = case_dir/"task_spec.json"
    spec = json.loads(spec_p.read_text(encoding="utf-8")) if spec_p.is_file() else {}
    cases.append({"case_id":case_dir.name,
      "task_id":starts[0].get("task_id"), "design":spec.get("design"),
      "split":spec.get("split"), "partition":spec.get("partition"),
      "starts":len(starts), "retries":max(0,len(starts)-1),
      "attempt_ids":[e.get("attempt_id") for e in starts],
      "start_ts_utc":[e.get("start_ts_utc") for e in starts],
      "end_ts_utc":[e.get("end_ts_utc") for e in ends],
      "exit_codes":[e.get("exit_code") for e in ends],
      "statuses":[e.get("status") for e in ends],
      "polar_rows":polar_rows(case_dir),
      "admitted": (case_dir/"admission_certificate.json").is_file()})
for c in cases: events += []  # no-op
starts_total = sum(c["starts"] for c in cases)
internal_total = sum(c["polar_rows"] for c in cases)
auth_budget = AUTH["budgets"]
result = {"schema":"drecover001.r2_pilot_ledger.v1",
 "generated_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
 "authorization_id":AUTH["authorization_id"], "run_id":AUTH["run_id"], "batch_id":AUTH["batch_id"],
 "owner_message_ref":AUTH["owner_message_ref"],
 "budget":{"physical_solver_starts_max":auth_budget["physical_solver_starts_max"],
           "max_internal_cases_per_start":auth_budget["max_internal_cases_per_start"],
           "timeout_s":auth_budget["timeout_s"], "retries":auth_budget["retries"]},
 "pilot":{"cases":cases,"physical_solver_starts_actual":starts_total,
          "internal_solver_cases_actual":internal_total,
          "retries_actual":sum(c["retries"] for c in cases),
          "billable_starts_actual":starts_total,
          "charged_starts":starts_total,
          "remaining_starts":auth_budget["physical_solver_starts_max"]-starts_total},
 "disclosure":{"pilot_started_before_a5_review":True,
   "pilot_ratification":"A5 verdict pending in this file; do not start additional cases until disposition and conditions are recorded",
   "evidence_scope":"LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED",
   "same_machine_backup":True,
   "off_machine_backup":False,
   "owner_waiver":"WAIVER-OFFMACHINE-BACKUP-20261118"},
 "note":"Counted from per-case solver_attempts.jsonl start events and polar data rows; internal rows are solver-internal alpha cases, not physical starts."}
out=ROOT/"pilot_ledger.json"
out.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps({k:result[k] for k in ("pilot","disclosure")}, indent=2)[:6000])
