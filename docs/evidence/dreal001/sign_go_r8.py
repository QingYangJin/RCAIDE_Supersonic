#!/usr/bin/env python
"""Lead GO record generator for R8 (D-REAL-001 P2a v2 R8, protocol D per L-09/L-10).

fail-closed: verifies signed approval, post-approval dry-run and A5 C-gate before
writing the GO record. DOES NOT start any solver.
"""
import argparse, hashlib, json, os
from datetime import datetime, timezone

RUN_ID = "DREAL001-P2A2R8-20261111-01"
BATCH_ID = "DREAL001-P2-20261111-13"
MAX_STARTS, PLANNED_STARTS = 451, 390
MAX_INTERNAL, PLANNED_INTERNAL = 3157, 2730
RESERVE = 64
CUM_STARTS, CUM_INTERNAL = 446, 3134
EXECUTOR_SHA_R7 = "da1056c0bdefaf3410f902102a51edf002ea4095c7a33fc207050b8b86e47398"
SUPERSEDES_SHA = "1a552267ab0070ee4f690815ed1de1db6d5976c1ada8356421f017bb84d72e37"
SUPERSEDES_BYTES = 69405
SUPERSEDES_RUN = "DREAL001-P2A2R7-20261111-01"


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
    ok &= chk("approval_conditions", len(appr.get("conditions") or []) >= 52, len(appr.get("conditions") or []))
    ok &= chk("approval_physical_flag", appr.get("physical_call_count") == 0, appr.get("physical_call_count"))
    _win = appr.get("window") or {}
    ok &= chk("approval_window", _win.get("start_utc") == "2026-11-11T16:30:00Z"
            and _win.get("end_utc") == "2026-11-12T04:00:00Z", _win)
    ok &= chk("approval_window_status", _win.get("status") == "APPROVED")
    ok &= chk("approval_token", appr.get("token") == "WINDOW_OK-P2AV2R8-20261111T1630Z-20261112T0400Z"
            and _win.get("token") == appr.get("token"), [appr.get("token"), _win.get("token")])
    lim = appr.get("limits") or {}
    ok &= chk("limits", (lim.get("max_geometry_builds"), lim.get("max_geometry_builds_per_design"),
                          lim.get("zero_physical_wall_cap_seconds")) == (8000, 100, 3600), lim)
    ok &= chk("approval_caps", (appr.get("max_starts"), appr.get("planned_starts"),
                                appr.get("max_internal_cases"), appr.get("planned_internal_cases"),
                                appr.get("reserve_starts")) == (MAX_STARTS, PLANNED_STARTS, MAX_INTERNAL,
                                                                PLANNED_INTERNAL, RESERVE),
              [appr.get("max_starts"), appr.get("planned_starts"), appr.get("max_internal_cases"),
               appr.get("planned_internal_cases"), appr.get("reserve_starts")])
    _a2exec = str((appr.get("approval_refs") or {}).get("a2_execution_code") or "")
    ok &= chk("approval_executor_ref_format", len(_a2exec) == 64
              and all(c in "0123456789abcdef" for c in _a2exec.lower()), _a2exec)
    ok &= chk("approval_executor_not_previous", _a2exec.lower() != EXECUTOR_SHA_R7, _a2exec)
    _sup = appr.get("supersedes") or {}
    _sup_sha = _sup.get("sha256") or _sup.get("approval_sha256") or _sup.get("sha") or ""
    ok &= chk("approval_r7_supersede", _sup_sha == SUPERSEDES_SHA, _sup_sha)
    ok &= chk("approval_r7_supersede_bytes", int(_sup.get("bytes") or 0) == SUPERSEDES_BYTES, _sup.get("bytes"))
    ok &= chk("approval_r7_supersede_run", _sup.get("run_id") == SUPERSEDES_RUN
              or _sup.get("superseded_run_id") == SUPERSEDES_RUN,
              [_sup.get("run_id"), _sup.get("superseded_run_id")])
    _add = appr.get("r8_addendum") or {}
    ok &= chk("approval_r8_addendum", _add.get("status") == "R8_PREFROZEN_REUSE_AND_DIAG_PAIR_PREREG_FIX", _add.get("status"))
    _cu = _add.get("cumulative_accounting") or {}
    ok &= chk("approval_r8_cumulative", (_cu.get("cumulative_starts"), _cu.get("cumulative_internal_cases"))
              == (CUM_STARTS, CUM_INTERNAL), [_cu.get("cumulative_starts"), _cu.get("cumulative_internal_cases")])
    _add_dump = json.dumps(_add, ensure_ascii=False)
    ok &= chk("approval_r8_prefrozen_reuse",
              "PREFROZEN" in _add_dump.upper() and "reused_prefrozen" in _add_dump,
              "prefrozen reuse binding missing")
    ok &= chk("approval_r8_diag_4_28_prereg",
              "4" in _add_dump and "28" in _add_dump and ("pair" in _add_dump.lower() or "full" in _add_dump.lower()),
              "diagnostic 4/28 prereg missing")
    _diag = _add.get("diagnostic_phase") or _add.get("diagnostics") or appr.get("diagnostics") or {}
    _diag_dump = json.dumps(_diag, ensure_ascii=False) if _diag else _add_dump
    _dhash = [c.get("design_hash") for c in (_diag.get("cases") or []) if isinstance(c, dict)]
    ok &= chk("approval_r7_diag",
              ("eb00b7ad545243e6" in _diag_dump and "dc96d2438a6dddc3" in _diag_dump)
              or (_dhash[:2] == ["eb00b7ad545243e6", "dc96d2438a6dddc3"]),
              _dhash or "diagnostic hashes not found")
    ok &= chk("approval_r8_diag_counts",
              (appr.get("diagnostic_planned_starts"), appr.get("diagnostic_planned_internal_cases"))
              == (4, 28),
              [appr.get("diagnostic_planned_starts"), appr.get("diagnostic_planned_internal_cases")])
    _all_policy = (json.dumps(appr, ensure_ascii=False) + "\n" + _add_dump).lower()
    ok &= chk("approval_r8_invalid_policy",
              ("invalid_numerical" in _all_policy or "invalid-numerical" in _all_policy
               or "invalid numerical" in _all_policy),
              "invalid-numerical tolerance policy recorded")
    ok &= chk("approval_r8_no_mesh_qc",
              _add.get("mesh_qc_gate") not in (True, "ENABLED", "enabled")
              and ("no mesh qc data gate" in _all_policy or "mesh-qc data gate not adopted" in _all_policy),
              _add.get("mesh_qc_gate"))

    dry_path = os.path.abspath(args.dry_run)
    dry_sha = sha256_file(dry_path)
    dry = json.load(open(dry_path, encoding="utf-8-sig"))
    ok &= chk("dry_dir", os.path.dirname(dry_path) == os.path.abspath(args.run_dir))
    ok &= chk("dry_status", dry.get("status") == "POST_APPROVAL_DRY_RUN_READY_NOT_RUN", dry.get("status"))
    _dt, _dp, _df = dry.get("checks_total"), dry.get("checks_passed"), dry.get("checks_failed", 0)
    ok &= chk("dry_checks", _df == 0 and isinstance(_dt, int) and _dt >= 37 and _dp == _dt, [_dt, _dp, _df])
    ok &= chk("dry_approval_sha", dry.get("approval_sha256") == appr_sha, [dry.get("approval_sha256"), appr_sha])
    ok &= chk("dry_physical0", (dry.get("physical_call_count"), dry.get("physical_solver_starts"),
                                dry.get("solver_processes"), dry.get("vspaero_processes")) == (0, 0, 0, 0),
              [dry.get("physical_call_count"), dry.get("physical_solver_starts")])
    ok &= chk("dry_no_ledger", dry.get("ledger_created") is False and dry.get("batch_summary_created") is False
              and dry.get("stop_report_created") is False)
    ok &= chk("dry_planned", (dry.get("cases_planned"), dry.get("cases_emitted")) == (PLANNED_STARTS, 0),
              [dry.get("cases_planned"), dry.get("cases_emitted")])

    pre = json.load(open(args.pre_gate_json, encoding="utf-8-sig"))
    ok &= chk("pre_gate_id", pre.get("gate_id") == "G-P2AV2R8-PRE", pre.get("gate_id"))
    ok &= chk("pre_gate_verdict", str(pre.get("verdict") or "").startswith("PASS"), pre.get("verdict"))
    ok &= chk("pre_gate_physical0", pre.get("physical_call_count") == 0, pre.get("physical_call_count"))
    pre_commit = args.pre_gate_commit
    ok &= chk("pre_gate_commit_len", len(pre_commit) == 40, pre_commit)
    ncond = len(pre.get("conditions") or [])
    ok &= chk("pre_gate_conditions52plus", ncond >= 52, ncond)
    _panch = pre.get("anchors") or {}
    ok &= chk("pre_gate_executor_binding", str(_panch.get("a2_executor_sha256") or "").lower() == _a2exec.lower(),
              [_panch.get("a2_executor_sha256"), _a2exec])
    ok &= chk("pre_gate_batch_run", _panch.get("batch_id") in (None, BATCH_ID)
              and _panch.get("run_id") in (None, RUN_ID), [_panch.get("batch_id"), _panch.get("run_id")])

    cg = json.load(open(args.c_gate_json, encoding="utf-8-sig"))
    ok &= chk("c_gate_id", cg.get("gate_id") == "C-P2AV2R8-02", cg.get("gate_id"))
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
        "go_token": "LEAD_GO_P2AV2R8_EXEC_" + stamp,
        "issued_by": "lead",
        "issued_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "physical_call_count_at_go": 0,
        "solver_started_at_go": False,
        "authorizes": ("execution of %s exactly per signed approval.json under protocol D (L-09/L-10): "
                       "2 replay preflight cases (PRE-01/PRE-02), then 2 preregistered diagnostic designs "
                       "(DIAG-01 design16 eb00b7ad545243e6, DIAG-02 design17 dc96d2438a6dddc3) evaluated as full "
                       "pairs (4 starts/28 internal), then 384 main arm slots; initial designs 15/16/17 use "
                       "prefrozen manifest byte reuse (zero rebuild); invalid numerical evaluations recorded as "
                       "INVALID_NUMERICAL and do not abort the batch; no retry; serialism 1; OMP 1; timeout 60 s; "
                       "invalid-tolerance auto-stop rules per preregistration; hard window stop "
                       "2026-11-12T04:00:00Z; execution must start before 2026-11-11T21:00:00Z else abort; "
                       "clean stop at 2026-11-12T02:30:00Z." % RUN_ID),
        "signed_approval": {
            "path": appr_path, "sha256": appr_sha, "bytes": appr_bytes,
            "approved_at_utc": appr.get("approved_at_utc"),
            "conditions_count": len(appr.get("conditions") or []),
            "executor_sha256": _a2exec,
            "supersedes_r7_approval_sha256": SUPERSEDES_SHA,
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
            "diagnostic_starts": 4, "diagnostic_internal_cases": 28,
        },
        "preflight_rule": ("PRE-01/PRE-02 must be PASS_BYTE (actual polar SHA equals approval.replay_bundles.cases "
                           "polar SHA). PASS_NUMERIC is NOT pre-authorized; any non-PASS_BYTE outcome = S1 stop, "
                           "diagnostics and main matrix NOT_RUN, no retry."),
        "diagnostic_rule": ("DIAG-01 (design16) and DIAG-02 (design17) run full-pair main-chain evaluations after the "
                            "2 preflight cases and before the 384-slot main matrix (2 starts/14 internal each; 4/28 total, "
                            "preregistered as such in R8 replacing R7's inconsistent 2/14 text); pass criterion status "
                            "SOLVED_VALID and finite non-null objective; if both fail -> main NOT_RUN, clean stop with "
                            "diagnostic evidence; diagnostics excluded from E1-E6 endpoints but charged to budget/caps; "
                            "design15 first BO seed evaluation may be INVALID_NUMERICAL (allowed cost 1 start/7 internal, "
                            "does not abort the batch)."),
        "invalid_evaluation_rule": ("Per protocol D (L-09): an evaluation whose A1 evaluator status is not SOLVED_VALID "
                                    "or whose objective is null/non-finite (NaN/Inf polar, LIFT_MATCH_FAILED, "
                                    "non-convergence) is recorded as INVALID_NUMERICAL with original status, polar SHA and "
                                    "reason, excluded from objective statistics, and does not abort the batch; genuine "
                                    "execution-layer errors (executor crash, write failure, ledger inconsistency) remain "
                                    "hard stops. No retry of invalid cases; no adaptive family selection; no design "
                                    "deletion; no mesh-QC data gate."),
        "stop_rules": [
            "preflight non-PASS_BYTE",
            "accounting mismatch or ledger gap/orphan start without repair",
            "window bounds violation",
            "hardware/process anomaly",
            "non-per-case execution-layer error (executor crash, write failure)",
            "unregistered protocol deviation",
            "invalid-tolerance auto-stop: after >=48 main evaluations invalid fraction >25%, or >=6 consecutive "
            "invalid in one arm, or cumulative invalid >64",
            "2026-11-12T04:00:00Z hard stop; 2026-11-11T19:00:00Z execution-start deadline; "
            "2026-11-12T02:30:00Z clean-stop checkpoint",
        ],
        "reporting": [
            "report preflight outcome immediately",
            "report diagnostic outcome immediately after it exists",
            "report batch completion or stop_report immediately after it exists",
            "no result release before A5 post-run independent audit",
        ],
        "disclosures_required": [
            "R1 excluded from E1-E6; charged 2 starts/14 internal",
            "R2 excluded from E1-E6; charged 2 starts/14 internal; preflight polar bytes matched but status-word bug caused false FAIL",
            "R3 excluded from E1-E6; charged 2 starts/14 internal; preflight 2/2 PASS_BYTE; arm BO stopped by DSH sandbox tmp 0o700 write denial + A1 FreezeBuilder integration gap",
            "R4 excluded from E1-E6; charged 2 starts/14 internal; preflight 2/2 PASS_BYTE; main arm BO first evaluation rejected by A1 UNIT_BOX guard (clipped x12) - fixed in R5 executor-boundary x12 domain conversion",
            "R5 excluded from E1-E6; charged 0/0; setup-stage abort before any solver spawn (DesignSpaceError import resolution); zero physical, no ledger",
            "R6 excluded from E1-E6; charged 3 starts/21 internal; preflight 2/2 PASS_BYTE; main single case design15 polar all-NaN (LIFT_MATCH_FAILED, objective null) then observe ValueError (design_hash(canonical_x12()) string misuse); R6 evidence preserved byte-identical",
            "R7 excluded from E1-E6; charged 6 starts/42 internal (preflight 2/14 PASS_BYTE + diagnostics 4/28 SOLVED_VALID; main 0 starts); S1 stop ARM_STOPPED_STOP_NOT_VALIDATED because freshly rebuilt design15 546x472 bytes (27325306...) differed from A1 static family_pair_manifest bytes (be8454bf...) - OpenVSP cross-process tessellation nondeterminism; R6 had only matched by luck; R7 evidence preserved byte-identical",
            "R8 fix per L-10: initial designs 15/16/17 reuse A1 P2AFAM prefrozen manifest bytes (SHA256+canonical verified, copied, PAIR_READY runtime record with reused_prefrozen=true, zero rebuild); non-initial designs keep FreezeBuilder (static index collision treated fail-closed); diagnostic phase keeps full-pair evaluation preregistered as 4 starts/28 internal (R7's 2/14 registration was inconsistent with implementation, disclosed); internal_solver_cases phantom default 7 removed; ACCOUNTING_INCONSISTENT assertion added; diagnostics polar SHA summary fixed; zero-physical prestart gate added",
            "A1 frozen bytes unchanged (evaluator f74a4752, freeze_api 31d78182, openvsp_model c40b11df, design_space 8f9b893c, config 8b29d1e3/10846B, bundle manifest 995bb12f); plan/prereg scientific policy unchanged",
            "A5 independent opinion on R8 prefrozen reuse, diagnostic 4/28 re-registration and any dissent must be recorded verbatim in the R8 gate and final receipt; Lead decision L-10 took responsibility for continuing after R7 S1 stop",
            "spawn exit_code/stdout_tail persisted if available without code change, else disclosed",
            "builder dry_run C10 definitional false-negative remains disclosed",
            "preflight and diagnostic cases excluded from E1-E6 endpoints",
            "single seed descriptive only; cross-family pooling not allowed (~5.83% CDi relative difference); cross-family comparisons descriptive",
            "fuel_burn_kg=null; physical validation NOT_VALIDATED; three-layer conclusions kept separate",
            "cumulative charged if R8 completes = 446 starts / 3134 internal (prior 56/404 + R8 390/2730); caps 451/3157; headroom 5 starts/23 internal; no retry allowed",
            "Lead decision L-10: R8 continues after user instruction m01474; R7 closed as S1_STOP_FROZEN_BYTES_SHA_MISMATCH with zero main starts; A5 FAIL-07 audit and any dissent recorded; R8 is a new preregistered batch, not a reuse of R7 approval; no R9 pre-authorized",
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
