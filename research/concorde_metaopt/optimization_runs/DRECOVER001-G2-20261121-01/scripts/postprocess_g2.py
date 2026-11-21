import csv, hashlib, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01")
CASES = RUN / "cases"
AUDIT_SCRIPT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py")
ADMIT_SCRIPT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01/scripts/admit_g1_case.py")
PY = sys.executable

def sha(p):
    h = hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr

m1 = json.loads((RUN / "g2_stage1_manifest.json").read_text(encoding="utf-8"))
m2 = json.loads((RUN / "g2_stage2_manifest.json").read_text(encoding="utf-8"))
attempted = []
for c in m1["cases"]:
    d = CASES / c["case_id"]
    if (d / "case_result.json").exists() or (d / "solver_attempts.jsonl").exists():
        attempted.append(dict(c, stage=1))
for c in m2["cases"]:
    d = CASES / c["case_id"]
    if (d / "case_result.json").exists() or (d / "solver_attempts.jsonl").exists():
        attempted.append(dict(c, stage=2))
print("attempted case dirs:", len(attempted))

rows = []; admitted = []; nulls = []; ledger_rows = []
for c in sorted(attempted, key=lambda x: (x["stage"], x["task_id"], x["design"], x["partition"])):
    case_id = c["case_id"]; d = CASES / case_id
    spec = json.loads((d / "task_spec.json").read_text(encoding="utf-8"))
    resf = d / "case_result.json"; certf = d / "admission_certificate.json"
    ledgerf = d / "solver_attempts.jsonl"
    starts_ev = []; ends = []; internal = 0
    if ledgerf.exists():
        for line in ledgerf.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            ev = json.loads(line)
            ev["case_id"] = case_id; ledger_rows.append(ev)
            if ev.get("event") == "start": starts_ev.append(ev)
            elif ev.get("event") == "end":
                ends.append(ev); internal += int(ev.get("internal_solver_cases") or 0)
    base = dict(case_id=case_id, stage=c["stage"], task_id=spec["task_id"], split=spec["split"],
                partition=spec["partition"], design=spec["design"], mach=spec["mach"],
                alpha_center_deg=spec["alpha_center_deg"], q_pa=spec["dynamic_pressure_pa"],
                sref_m2=spec["sref_m2"], cl_target=spec["cl_target"],
                physical_starts_logged=len(starts_ev), internal_cases=internal)
    if not resf.exists():
        row = dict(base, status="NO_RESULT", solver_status=None, exit_code=None,
                   lift_match_status=None, di_n=None, cl=None, cdi=None, alpha_deg=None,
                   rel_lift_error=None, wall_s=None, cert_status=None, evidence_scope=None,
                   failure_kind="NULL_SOLVER_NO_RESULT_INTERRUPTED",
                   detail="start artifacts (adb/history/stdout/lod) exist but no .polar/case_result; interrupted by outer timeout; counted as 1 physical start and not rerun")
        rows.append(row); nulls.append(row); continue
    res = json.loads(resf.read_text(encoding="utf-8"))
    ev = res.get("evaluation") or {}
    proc = res.get("process") or {}
    lm = ev.get("lift_match") or {}
    row = dict(base, status=ev.get("status") or res.get("status"),
               solver_status=res.get("status"), exit_code=proc.get("exit_code"),
               lift_match_status=ev.get("lift_match_status"),
               di_n=(ev.get("objective") or {}).get("value"), cl=ev.get("cl"),
               cdi=ev.get("cdi"), alpha_deg=ev.get("alpha_deg"),
               rel_lift_error=lm.get("rel_error"), wall_s=proc.get("wall_s"),
               cert_status=None, evidence_scope=None, failure_kind=None, detail=None,
               screening_only=c["stage"] == 1)
    # Stage 1 is screening only: never admit a label from stage 1.
    if c["stage"] == 2 and row["status"] == "SOLVED" and proc.get("exit_code") == 0:
        audit_id = "g2-audit-" + case_id
        rc, out, err = run([PY, str(AUDIT_SCRIPT), "--case-dir", str(d), "--audit-id", audit_id,
                            "--reviewer", "lead-local-script", "--reviewer-role",
                            "SEPARATE_LOCAL_REIMPLEMENTATION_NOT_HUMAN_NOT_A5",
                            "--created-utc", now(), "--verdict", "ADMIT_REAL_LABEL"])
        if rc == 0:
            started = (res.get("attempt") or {}).get("start_ts_utc") or ""
            started = started[:19] + "Z" if started else ""
            rc2, out2, err2 = run([PY, str(ADMIT_SCRIPT), "--case-dir", str(d),
                                   "--admission-id", "g2-adm-" + case_id,
                                   "--audit-ref", audit_id,
                                   "--evaluator-id", "vspaero-3.55.0-v7.2.2-omp1",
                                   "--solver-started-utc", started,
                                   "--partition", spec["partition"], "--split", spec["split"],
                                   "--task-spec", str(d / "task_spec.json")])
            if rc2 == 0 and certf.exists():
                cert = json.loads(certf.read_text(encoding="utf-8"))
                row.update(cert_status=cert.get("status"), di_n=cert.get("di_n"),
                           cl=cert.get("cl"), cdi=cert.get("cdi"),
                           alpha_deg=cert.get("alpha_deg"),
                           evidence_scope=cert.get("evidence_scope"))
                if cert.get("status") == "ok":
                    admitted.append(dict(row, admission_id=cert.get("admission_id"),
                                         design_sha256=cert.get("design_sha256"),
                                         raw_sha256=cert.get("raw_sha256"),
                                         artifact_sha256=cert.get("artifact_sha256")))
                    rows.append(row); continue
            row.update(failure_kind="ADMISSION_FAILED", detail=(err2 or out2)[-800:])
        else:
            row.update(failure_kind="AUDIT_FAILED", detail=(err or out)[-800:])
    elif c["stage"] == 2 and row["status"] == "SOLVED":
        row.update(failure_kind="SOLVER_NOT_SUCCESS", detail=str(res.get("status")))
    elif c["stage"] == 1 and row["status"] == "SOLVED":
        row["failure_kind"] = "SCREENING_ONLY_NOT_ADMITTED"
        row["detail"] = "stage 1 is exploratory screening; labels only from stage 2 raw rows"
        nulls.append(row); rows.append(row); continue
    else:
        row["failure_kind"] = row.get("failure_kind") or "NULL_SOLVER_OR_LIFT"
        row.setdefault("detail", row.get("lift_match_status"))
    rows.append(row); nulls.append(row)

def write_csv(path, items, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader()
        for item in items: w.writerow(item)

fields = ["case_id", "stage", "task_id", "split", "partition", "design", "mach",
          "alpha_center_deg", "q_pa", "sref_m2", "cl_target", "status",
          "lift_match_status", "di_n", "cl", "cdi", "alpha_deg", "rel_lift_error",
          "physical_starts_logged", "internal_cases", "wall_s", "cert_status",
          "evidence_scope", "failure_kind", "detail"]
write_csv(RUN / "all_evaluations.csv", rows, fields)
write_csv(RUN / "admitted_labels.csv", admitted, fields + ["admission_id", "design_sha256", "raw_sha256", "artifact_sha256"])
write_csv(RUN / "failed_or_null.csv", nulls, fields)
write_csv(RUN / "attempt_ledger.csv", ledger_rows,
          ["case_id", "event", "attempt_id", "task_id", "start_ts_utc", "end_ts_utc",
           "status", "exit_code", "physical_solver_starts", "internal_solver_cases",
           "wall_s", "plan_sha256", "approval_sha256", "window_token"])

logged_starts = sum(1 for r in ledger_rows if r.get("event") == "start")
logged_completed = sum(1 for r in ledger_rows if r.get("event") == "end")
# g2-m140-d03-support-s1 has a logged start event but no end event: it was killed by the
# outer 120 s timeout after the solver had started. It is counted as a charged start,
# classified NULL_SOLVER_NO_RESULT_INTERRUPTED, and is not rerun.
INTERRUPTED = 1
actual_starts = logged_starts
internal_logged = sum(int(r.get("internal_solver_cases") or 0) for r in ledger_rows if r.get("event") == "end")
# d03 was planned for 49 internal; it was killed, so its internal count is unknown. Record a
# conservative planning lower bound separately and never fold it into 'actual'.
accounting = {
    "schema": "dreal003.g2_batch_accounting.v1",
    "run_id": m1["run_id"], "authorization_id": m1["authorization_id"],
    "batch_id": "B01", "go_record": "g2_go_record_b01.json",
    "physical_solver_starts_actual": actual_starts,
    "physical_solver_starts_logged": logged_starts,
    "physical_solver_starts_interrupted_no_end": INTERRUPTED,
    "physical_solver_starts_completed": logged_completed,
    "internal_solver_cases_actual_logged": internal_logged,
    "internal_solver_cases_interrupted_case": "UNKNOWN; planned 49 not counted as actual",
    "charged_starts": actual_starts,
    "planned_reserved_starts_this_go": 24,
    "remaining_starts": 0,
    "cumulative_starts_against_g2_cap": actual_starts,
    "g2_cap": 240,
    "retries_actual": 0, "parallelism": 1,
    "successful_logged_cases": sum(1 for r in rows if r["status"] == "SOLVED"),
    "admitted_labels": len(admitted), "null_labels": len(nulls),
    "valid_label_rate_over_completed": (len(admitted) / logged_completed) if logged_completed else 0.0,
    "valid_label_rate_over_charged": (len(admitted) / actual_starts) if actual_starts else 0.0,
    "cases": rows, "admitted": admitted, "nulls": nulls,
    "interrupted_case": {
        "case_id": "g2-m140-d03-support-s1",
        "classification": "NULL_SOLVER_NO_RESULT_INTERRUPTED",
        "logged_start": True,
        "logged_end": False,
        "rerun": False,
        "evidence": "solver_attempts.jsonl has a start event only; adb/history/lod/stdout exist; no .polar and no case_result.json",
    },
    "generated_utc": now(),
    "physical_zero_before_g2": True,
}
(RUN / "batch_accounting.json").write_text(json.dumps(accounting, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
(RUN / "null_labels.json").write_text(json.dumps({"schema": "dreal003.g2_null_labels.v1", "nulls": nulls}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({
    "logged_starts": logged_starts, "actual_starts": actual_starts,
    "completed": logged_completed, "internal_logged": internal_logged,
    "admitted": len(admitted), "nulls": len(nulls),
    "valid_rate_over_completed": accounting["valid_label_rate_over_completed"],
    "batch_accounting_sha256": sha(RUN / "batch_accounting.json"),
    "admitted_labels_sha256": sha(RUN / "admitted_labels.csv"),
    "admitted_ids": [r["case_id"] for r in admitted],
}, indent=2))
