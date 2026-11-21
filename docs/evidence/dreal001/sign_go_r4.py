#!/usr/bin/env python
"""Lead GO record generator for R4 (D-REAL-001 P2a v2 R4).

fail-closed: verifies signed approval, post-approval dry-run and A5 C-gate before
writing the GO record. DOES NOT start any solver.
"""
import argparse, hashlib, json, os
from datetime import datetime, timezone

RUN_DIR = r"D:\RCAIDE\dnext001\wt-real-a2-optimizers\research\concorde_metaopt\dreal001\runs"
RUN_ID = "DREAL001-P2A2R4-20261111-01"
BATCH_ID = "DREAL001-P2-20261111-09"
EXPECTED_APPROVAL_SHA = "PENDING"  # filled at sign time via --approval-sha
MAX_STARTS, PLANNED_STARTS = 451, 386
MAX_INTERNAL, PLANNED_INTERNAL = 3157, 2702
RESERVE = 64
CUM_STARTS, CUM_INTERNAL = 431, 3029


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--approval", required=True)
    ap.add_argument("--dry-run", required=True)
    ap.add_argument("--pre-gate-json", required=True)
    ap.add_argument("--pre-gate-commit", required=True)
    ap.add_argument("--c-gate-json", required=True)
    ap.add_argument("--c-gate-commit", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    checks = []

    def chk(name, cond, val=None):
        checks.append((name, bool(cond), val))
        return bool(cond)

    ok = True
    appr_path = os.path.abspath(args.approval)
    appr_sha = sha256_file(appr_path)
    appr_bytes = os.path.getsize(appr_path)
    appr = json.load(open(appr_path, encoding="utf-8-sig"))
    ok &= chk("approval_path", os.path.dirname(appr_path) == os.path.abspath(args.run_dir))
    ok &= chk("approval_approved", appr.get("approved") is True)
    ok &= chk("approval_status", appr.get("status") == "APPROVED_FOR_EXECUTION_PENDING_POST_APPROVAL_DRY_RUN", appr.get("status"))
    ok &= chk("approval_batch", appr.get("batch_id") == BATCH_ID, appr.get("batch_id"))
    ok &= chk("approval_run", appr.get("run_id") == RUN_ID, appr.get("run_id"))
    ok &= chk("approval_conditions", len(appr.get("conditions") or []) == 52, len(appr.get("conditions") or []))
    ok &= chk("approval_physical_flag", appr.get("physical_call_count") == 0, appr.get("physical_call_count"))
    _win = appr.get("window") or {}
    ok &= chk("approval_window", _win.get("start_utc") == "2026-11-11T09:00:00Z"
            and _win.get("end_utc") == "2026-11-11T12:00:00Z", _win)
    ok &= chk("approval_window_status", _win.get("status") == "APPROVED")
    ok &= chk("approval_token", appr.get("token") == "WINDOW_OK-P2AV2R4-20261111T0900Z-1200Z"
            and _win.get("token") == appr.get("token"), [appr.get("token"), _win.get("token")])
    lim = appr.get("limits") or {}
    ok &= chk("limits", (lim.get("max_geometry_builds"), lim.get("max_geometry_builds_per_design"),
                          lim.get("zero_physical_wall_cap_seconds")) == (8000, 100, 3600), lim)
    ok &= chk("approval_caps", (appr.get("max_starts"), appr.get("planned_starts"),
                                appr.get("max_internal_cases"), appr.get("planned_internal_cases"),
                                appr.get("reserve_starts")) == (451, 386, 3157, 2702, 64),
              [appr.get("max_starts"), appr.get("planned_starts"), appr.get("max_internal_cases"),
               appr.get("planned_internal_cases"), appr.get("reserve_starts")])

    dry_path = os.path.abspath(args.dry_run)
    dry_sha = sha256_file(dry_path)
    dry = json.load(open(dry_path, encoding="utf-8-sig"))
    ok &= chk("dry_dir", os.path.dirname(dry_path) == os.path.abspath(args.run_dir))
    ok &= chk("dry_status", dry.get("status") == "POST_APPROVAL_DRY_RUN_READY_NOT_RUN", dry.get("status"))
    ok &= chk("dry_checks", (dry.get("checks_total"), dry.get("checks_passed"), dry.get("checks_failed", 0)) == (37, 37, 0),
              [dry.get("checks_total"), dry.get("checks_passed"), dry.get("checks_failed")])
    ok &= chk("dry_approval_sha", dry.get("approval_sha256") == appr_sha, [dry.get("approval_sha256"), appr_sha])
    ok &= chk("dry_physical0", (dry.get("physical_call_count"), dry.get("physical_solver_starts"),
                                dry.get("solver_processes"), dry.get("vspaero_processes")) == (0, 0, 0, 0),
              [dry.get("physical_call_count"), dry.get("physical_solver_starts")])
    ok &= chk("dry_no_ledger", dry.get("ledger_created") is False and dry.get("batch_summary_created") is False
              and dry.get("stop_report_created") is False)
    ok &= chk("dry_planned", (dry.get("cases_planned"), dry.get("cases_emitted")) == (386, 0),
              [dry.get("cases_planned"), dry.get("cases_emitted")])

    pre = json.load(open(args.pre_gate_json, encoding="utf-8-sig"))
    ok &= chk("pre_gate_id", pre.get("gate_id") == "G-P2AV2R4-PRE", pre.get("gate_id"))
    ok &= chk("pre_gate_verdict", str(pre.get("verdict") or "").startswith("PASS"), pre.get("verdict"))
    ok &= chk("pre_gate_physical0", pre.get("physical_call_count") == 0, pre.get("physical_call_count"))
    pre_commit = args.pre_gate_commit
    ok &= chk("pre_gate_commit_len", len(pre_commit) == 40, pre_commit)
    ncond = len(pre.get("conditions") or [])
    ok &= chk("pre_gate_conditions52", ncond == 52, ncond)

    cg = json.load(open(args.c_gate_json, encoding="utf-8-sig"))
    ok &= chk("c_gate_id", cg.get("gate_id") == "C-P2AV2R4-02", cg.get("gate_id"))
    ok &= chk("c_gate_verdict", cg.get("verdict") == "PASS", cg.get("verdict"))
    ok &= chk("c_gate_physical0", cg.get("physical_call_count") == 0, cg.get("physical_call_count"))
    ok &= chk("c_gate_commit", len(args.c_gate_commit) == 40 and cg.get("commit") in (None, args.c_gate_commit),
              [cg.get("commit"), args.c_gate_commit])

    rd = os.path.abspath(args.run_dir)
    preexec = sorted(os.listdir(rd))
    ok &= chk("run_dir_no_cases", "cases" not in preexec and "solver_attempts.jsonl" not in preexec
              and "batch_summary.json" not in preexec and "stop_report.json" not in preexec
              and "evaluations" not in preexec, preexec)

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    rec = {
        "schema": "dreal001.lead_go.v1",
        "go_token": "LEAD_GO_P2AV2R4_EXEC_" + stamp,
        "issued_by": "lead",
        "issued_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "physical_call_count_at_go": 0,
        "solver_started_at_go": False,
        "authorizes": ("execution of %s exactly per signed approval.json: 2 replay preflight cases "
                       "(PRE-01/PRE-02), then 384 main arm slots; no retry; serialism 1; OMP 1; timeout 60 s; "
                       "hard window stop 2026-11-11T12:00:00Z; clean stop at 11:30Z if not finished." % RUN_ID),
        "signed_approval": {
            "path": appr_path, "sha256": appr_sha, "bytes": appr_bytes,
            "approved_at_utc": appr.get("approved_at_utc"),
            "conditions_count": len(appr.get("conditions") or []),
        },
        "post_approval_dry_run": {
            "path": dry_path, "sha256": dry_sha,
            "status": dry.get("status"), "checks": "%s/%s PASS" % (dry.get("checks_passed"), dry.get("checks_total")),
        },
        "a5_gates": {
            "pre_gate": {"id": pre.get("gate_id"), "verdict": pre.get("verdict"), "commit": pre_commit,
                          "json_sha256": sha256_file(os.path.abspath(args.pre_gate_json))},
            "c_gate": {"id": cg.get("gate_id"), "verdict": cg.get("verdict"), "commit": args.c_gate_commit,
                        "json_sha256": sha256_file(os.path.abspath(args.c_gate_json))},
        },
        "limits": {
            "max_starts": MAX_STARTS, "planned_starts": PLANNED_STARTS,
            "max_internal_cases": MAX_INTERNAL, "planned_internal_cases": PLANNED_INTERNAL,
            "reserve_starts": RESERVE, "max_refine_starts": 0,
            "cumulative_starts": CUM_STARTS, "cumulative_internal_cases": CUM_INTERNAL,
        },
        "preflight_rule": ("PRE-01/PRE-02 must be PASS_BYTE (actual polar SHA equals approval.replay_bundles.cases "
                           "polar SHA). PASS_NUMERIC is NOT pre-authorized; any non-PASS_BYTE outcome = S1 stop, "
                           "main matrix NOT_RUN, no retry."),
        "stop_rules": [
            "NaN/Inf or non-SOLVED", "preflight non-PASS_BYTE", "accounting mismatch",
            "ledger gap/orphan start without repair", "window bounds violation",
            "hardware/process anomaly", "any deviation from signed conditions",
            "12:00:00Z hard stop; 11:30Z clean-stop checkpoint",
        ],
        "reporting": [
            "report preflight outcome immediately",
            "report batch completion or stop_report immediately after it exists",
            "no result release before A5 post-run independent audit",
        ],
        "disclosures_required": [
            "R1 excluded from E1-E6; charged 2 starts/14 internal count toward cumulative 431/3029",
            "R2 excluded from E1-E6; charged 2 starts/14 internal; preflight polar bytes matched but status-word bug caused false FAIL",
            "R3 excluded from E1-E6; charged 2 starts/14 internal; preflight 2/2 real SOLVED_VALID with byte-matching polar; arm BO stopped by DSH sandbox tmp 0o700 write denial + A1 FreezeBuilder integration gap (PYTHONPATH/openvsp_root); fixed by R4 launcher-level shims only",
            "R4 launcher-level env/compat shims disclosed and audited by A5 (ACL-safe mkdtemp, PYTHONPATH injection, openvsp_root injection); executor/A1/plan bytes unchanged",
            "spawn exit_code/stdout_tail persisted if available without code change, else disclosed",
            "builder dry_run C10 definitional false-negative remains disclosed",
            "preflight exclusion (PRE cases not in E1-E6 endpoints)",
            "single seed descriptive only; cross-family pooling not allowed (~5.83% CDi relative difference); cross-family comparisons descriptive",
            "fuel_burn_kg=null; physical validation NOT_VALIDATED; three-layer conclusions kept separate",
        ],
    }
    fails = [c for c in checks if not c[1]]
    print(json.dumps({"checks": len(checks), "failed": len(fails),
                      "fail_detail": [(n, v) for n, _, v in fails]}, ensure_ascii=False))
    if fails:
        print("GO_NOT_ISSUED_REFUSED")
        raise SystemExit(2)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("GO_RECORD_WRITTEN", args.out, sha256_file(args.out), os.path.getsize(args.out), rec["go_token"])


if __name__ == "__main__":
    main()
