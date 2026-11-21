#!/usr/bin/env python
"""Lead GO record generator for R10 (D-REAL-001 P2a v2 R10, protocol D per L-09/L-10/L-11/L-12).

fail-closed: verifies signed approval, post-approval dry-run and A5 pre/C gates before
writing the GO record. DOES NOT start any solver.
"""
import argparse, hashlib, json, os
from datetime import datetime, timezone

RUN_ID = "DREAL001-P2A2R10-20261111-01"
BATCH_ID = "DREAL001-P2-20261111-15"
MAX_STARTS, PLANNED_STARTS = 451, 386
MAX_INTERNAL, PLANNED_INTERNAL = 3157, 2702
RESERVE = 64
CUM_STARTS, CUM_INTERNAL = 448, 3148
EXECUTOR_SHA_PREV = "c2bdfb6825d156b71713ad57b9c982ebc06ec5a08bbfadf4324839ce8625af54"
SUPERSEDES_SHA = "b502b484e50c71707e484c758b5baaf0409c423c4838094c8300c36202bdd991"
SUPERSEDES_BYTES = 76257
SUPERSEDES_RUN = "DREAL001-P2A2R9-20261111-01"
DIAG_HASHES = ("eb00b7ad545243e6", "dc96d2438a6dddc3")


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
    ap.add_argument("--pre-conditions-file", default=None)
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
    ok &= chk("approval_window", _win.get("start_utc") == "2026-11-11T18:30:00Z"
            and _win.get("end_utc") == "2026-11-12T04:00:00Z", _win)
    ok &= chk("approval_window_status", _win.get("status") == "APPROVED")
    ok &= chk("approval_token", appr.get("token") == "WINDOW_OK-P2AV2R10-20261111T1830Z-20261112T0400Z"
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
    ok &= chk("approval_executor_not_previous", _a2exec.lower() != EXECUTOR_SHA_PREV, _a2exec)
    _sup = appr.get("supersedes") or {}
    _sup_sha = _sup.get("sha256") or _sup.get("approval_sha256") or _sup.get("sha") or ""
    ok &= chk("approval_r9_supersede", _sup_sha == SUPERSEDES_SHA, _sup_sha)
    ok &= chk("approval_r9_supersede_bytes", int(_sup.get("bytes") or 0) == SUPERSEDES_BYTES, _sup.get("bytes"))
    ok &= chk("approval_r9_supersede_run", _sup.get("run_id") == SUPERSEDES_RUN
              or _sup.get("superseded_run_id") == SUPERSEDES_RUN,
              [_sup.get("run_id"), _sup.get("superseded_run_id")])
    _add = appr.get("r10_addendum") or {}
    ok &= chk("approval_r10_addendum", _add.get("status") == "R10_INTERNAL_ACCOUNTING_FIX", _add.get("status"))
    _cu = _add.get("cumulative_accounting") or {}
    ok &= chk("approval_r10_cumulative", (_cu.get("cumulative_starts"), _cu.get("cumulative_internal_cases"))
              == (CUM_STARTS, CUM_INTERNAL), [_cu.get("cumulative_starts"), _cu.get("cumulative_internal_cases")])
    _add_dump = json.dumps(_add, ensure_ascii=False)
    ok &= chk("approval_prefrozen_reuse",
              "PREFROZEN" in _add_dump.upper() and "reused_prefrozen" in _add_dump,
              "prefrozen reuse binding missing")
    _diag = appr.get("diagnostics") or {}
    _diag_dump = json.dumps(_diag, ensure_ascii=False) if _diag else ""
    ok &= chk("approval_diagnostics_not_in_matrix",
              _diag.get("in_r10_matrix") is False and _diag.get("diagnostics_not_rerun") is True,
              [_diag.get("in_r10_matrix"), _diag.get("diagnostics_not_rerun")])
    ok &= chk("approval_diag_counts_zero",
              (appr.get("diagnostic_planned_starts"), appr.get("diagnostic_planned_internal_cases")) == (0, 0),
              [appr.get("diagnostic_planned_starts"), appr.get("diagnostic_planned_internal_cases")])
    ok &= chk("approval_diag_cases_empty", (_diag.get("cases") or []) == [], _diag.get("cases"))
    ok &= chk("approval_r9_diag_evidence_cited",
              all(h in _diag_dump for h in DIAG_HASHES), "R9 diagnostic hashes missing")
    _r9 = _add.get("r9_reference") or {}
    ok &= chk("approval_r9_reference_sha", (_r9.get("superseded_approval_sha256") or "") == SUPERSEDES_SHA,
              _r9.get("superseded_approval_sha256"))
    ok &= chk("approval_r9_reference_stop", "STOP" in str(_r9.get("status") or "").upper(), _r9.get("status"))
    ok &= chk("approval_r9_reference_excluded", _r9.get("excluded_from_endpoints") is True
              and _r9.get("artifacts_preserved") is True)
    _chg = str(_add.get("r10_change") or "")
    _all_policy = (json.dumps(appr, ensure_ascii=False) + "\n" + _add_dump).lower()
    ok &= chk("approval_internal_policy",
              ("INTERNAL_CASES_PER_START" in _chg or "internal_cases_per_start" in _chg.lower())
              and "7" in _chg and ("conservation" in _chg.lower() or "sum(internal)" in _chg.lower())
              and "ACCOUNTING_INCONSISTENT" in _chg,
              "internal=7xstarts conservation policy missing")
    ok &= chk("approval_diagnostics_not_rerun",
              "does not re-run the diagnostic phase" in _chg.lower()
              or "diagnostics-not-in-r10-matrix" in _all_policy,
              "diagnostics-not-in-matrix statement missing")
    ok &= chk("approval_r10_invalid_policy",
              ("invalid_numerical" in _all_policy or "invalid-numerical" in _all_policy
               or "invalid numerical" in _all_policy),
              "invalid-numerical tolerance policy recorded")
    ok &= chk("approval_r10_no_mesh_qc",
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
    ok &= chk("dry_internal", dry.get("planned_internal_cases") in (None, PLANNED_INTERNAL),
              dry.get("planned_internal_cases"))

    pre = json.load(open(args.pre_gate_json, encoding="utf-8-sig"))
    ok &= chk("pre_gate_id", pre.get("gate_id") == "G-P2AV2R10-PRE", pre.get("gate_id"))
    ok &= chk("pre_gate_verdict", str(pre.get("verdict") or "").startswith("PASS"), pre.get("verdict"))
    ok &= chk("pre_gate_physical0", pre.get("physical_call_count") == 0, pre.get("physical_call_count"))
    pre_commit = args.pre_gate_commit
    ok &= chk("pre_gate_commit_len", len(pre_commit) == 40, pre_commit)
    ncond = len(pre.get("conditions") or [])
    if ncond == 0:
        ncond = int(pre.get("conditions_total") or 0)
    if ncond == 0 and args.pre_conditions_file:
        _pc = json.load(open(args.pre_conditions_file, encoding="utf-8-sig"))
        ncond = len(_pc.get("conditions") or _pc)
    ok &= chk("pre_gate_conditions52plus", ncond >= 52, ncond)
    _panch = pre.get("anchors") or {}
    _p_exec = _panch.get("executor") if isinstance(_panch.get("executor"), dict) else None
    _p_exec_sha = str((_p_exec or {}).get("sha256") or _panch.get("a2_executor_sha256") or "")
    ok &= chk("pre_gate_executor_binding", _p_exec_sha.lower() == _a2exec.lower(), [_p_exec_sha, _a2exec])
    _pkg = str(_panch.get("package_commit") or _panch.get("a2_package_commit") or "")
    _apkg = str((appr.get("approval_refs") or {}).get("a2_package_commit") or "")
    ok &= chk("pre_gate_package_binding", _pkg.lower() == _apkg.lower(), [_pkg, _apkg])
    ok &= chk("pre_gate_batch_run", pre.get("batch_id") in (None, BATCH_ID)
              and pre.get("run_id") in (None, RUN_ID), [pre.get("batch_id"), pre.get("run_id")])

    cg = json.load(open(args.c_gate_json, encoding="utf-8-sig"))
    ok &= chk("c_gate_id", cg.get("gate_id") == "C-P2AV2R10-02", cg.get("gate_id"))
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
        "go_token": "LEAD_GO_P2AV2R10_EXEC_" + stamp,
        "issued_by": "lead",
        "issued_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "physical_call_count_at_go": 0,
        "solver_started_at_go": False,
        "authorizes": ("execution of %s exactly per signed approval.json under protocol D "
                       "(L-09/L-10/L-11/L-12): 2 replay preflight cases (PRE-01/PRE-02), then the diagnostic phase "
                       "is NOT part of the R10 matrix (executor must write a DIAGNOSTICS_NOT_IN_MATRIX record with "
                       "starts=0/internal=0 and must NOT spawn any diagnostic solver case; R9 diagnostic evidence is "
                       "cited and excluded from endpoints), then 384 main arm slots; initial designs 15/16/17 use "
                       "prefrozen manifest byte reuse (zero rebuild, flat family rows accepted); internal accounting "
                       "is internal_cases=7 x physical_starts per phase with sum conservation fail-closed; invalid "
                       "numerical evaluations recorded as INVALID_NUMERICAL and do not abort the batch; no retry; "
                       "serialism 1; OMP 1; timeout 60 s; invalid-tolerance auto-stop rules per preregistration; hard "
                       "window stop 2026-11-12T04:00:00Z; execution must start before 2026-11-11T21:00:00Z else "
                       "abort; clean stop at 2026-11-12T02:30:00Z." % RUN_ID),
        "signed_approval": {
            "path": appr_path, "sha256": appr_sha, "bytes": appr_bytes,
            "approved_at_utc": appr.get("approved_at_utc"),
            "conditions_count": len(appr.get("conditions") or []),
            "executor_sha256": _a2exec,
            "supersedes_r9_approval_sha256": SUPERSEDES_SHA,
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
            "diagnostic_starts": 0, "diagnostic_internal_cases": 0,
        },
        "preflight_rule": ("PRE-01/PRE-02 must be PASS_BYTE (actual polar SHA equals approval.replay_bundles.cases "
                           "polar SHA). PASS_NUMERIC is NOT pre-authorized; any non-PASS_BYTE outcome = S1 stop, "
                           "diagnostics/main matrix NOT_RUN, no retry."),
        "diagnostic_rule": ("R10 does not run the diagnostic phase: plan/prereg/approval declare diagnostics NOT in "
                            "the R10 matrix (0 starts / 0 internal). The executor must check the dual declaration and "
                            "write a DIAGNOSTICS_NOT_IN_MATRIX record instead of spawning DIAG-01/DIAG-02; any "
                            "diagnostic solver spawn or non-zero diagnostic counts = accounting/protocol violation "
                            "and hard stop. R9 diagnostic evidence (design 16 eb00b7ad545243e6, design 17 "
                            "dc96d2438a6dddc3) is cited for feasibility only and excluded from E1-E6."),
        "invalid_evaluation_rule": ("Per protocol D (L-09): an evaluation whose A1 evaluator status is not SOLVED_VALID "
                                    "or whose objective is null/non-finite (NaN/Inf polar, LIFT_MATCH_FAILED, "
                                    "non-convergence) is recorded as INVALID_NUMERICAL with original status, polar SHA and "
                                    "reason, excluded from objective statistics, and does not abort the batch; genuine "
                                    "execution-layer errors (executor crash, write failure, accounting/ledger "
                                    "inconsistency) remain hard stops. No retry of invalid cases; no adaptive family "
                                    "selection; no design deletion; no mesh-QC data gate."),
        "stop_rules": [
            "preflight non-PASS_BYTE",
            "accounting mismatch or ledger gap/orphan start without repair",
            "internal-accounting conservation failure (sum(internal_cases) != 7 x physical_starts per phase or total)",
            "diagnostic phase spawn or non-zero diagnostic counts (R10 matrix excludes diagnostics)",
            "window bounds violation",
            "hardware/process anomaly",
            "non-per-case execution-layer error (executor crash, write failure)",
            "unregistered protocol deviation",
            "invalid-tolerance auto-stop: after >=48 main evaluations invalid fraction >25%, or >=6 consecutive "
            "invalid in one arm, or cumulative invalid >64",
            "2026-11-12T04:00:00Z hard stop; 2026-11-11T21:00:00Z execution-start deadline; "
            "2026-11-12T02:30:00Z clean-stop checkpoint",
        ],
        "reporting": [
            "report preflight outcome immediately",
            "report the DIAGNOSTICS_NOT_IN_MATRIX skip record immediately after it exists",
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
            "R7 excluded from E1-E6; charged 6 starts/42 internal (preflight 2/14 PASS_BYTE + diagnostics 4/28 SOLVED_VALID; main 0 starts); S1 stop ARM_STOPPED_STOP_NOT_VALIDATED because freshly rebuilt design15 546x472 bytes differed from A1 static family_pair_manifest bytes - OpenVSP cross-process tessellation nondeterminism; R7 evidence preserved byte-identical",
            "R8 excluded from E1-E6; charged 0 starts/0 internal; launcher gate PASS but executor-side _prefrozen_reuse_gate raised PREFROZEN_GEOM_MISSING because flat family rows were read as nested row[frozen]; zero physical; R8 evidence preserved byte-identical",
            "R9 excluded from E1-E6; charged 6 starts/42 internal (preflight 2/14 PASS_BYTE + diagnostics 4/28 SOLVED_VALID; main 0 starts); S1 stop STOP_DIAGNOSTICS_ACCOUNTING_INCONSISTENT because internal_solver_cases was read as 0 (A1 runtime record lacks internal_evals) so the 4/28 conservation check failed closed; no retry; R9 evidence preserved byte-identical",
            "R10 fix per L-12: internal_cases = 7 x physical_starts derived from the pre-registered INTERNAL_CASES_PER_START policy constant (source tagged INTERNAL_PER_START_POLICY) for every preflight/main evaluation row, with phase-boundary and final-summary conservation checks fail-closed; polar_sha256 recorded per evaluation/pair row when available; mandatory zero-physical smoke proves the real main-path accounting chain (internal=7xstarts with physical=0); diagnostics not re-run (R9 evidence cited and excluded); all R9 remediations retained (prefrozen flat/nested reuse, observe fix, x12 domain, invalid tolerance, launcher preload/env shim, arm-failure evidence)",
            "R10 package v1 was rejected by A5 before signature for two blockers: unconditional diagnostic phase in the executor (would have exceeded caps: 452/3176 > 451/3157) and stale R9 constants in executor_dry_run.json; both were fixed in package v2 (79e8f6a) with the dual-source diagnostics-not-in-matrix gate and R10 dry-run constants (386/2702, diagnostics []/0/0); disclosure and A5 audit recorded",
            "A1 frozen bytes unchanged (evaluator f74a4752, freeze_api 31d78182, openvsp_model c40b11df, design_space 8f9b893c, config 8b29d1e3/10846B, bundle manifest 995bb12f); plan/prereg scientific policy unchanged",
            "A5 independent opinion on R9 S1 stop, the internal-accounting root cause, the R10 fix and any dissent must be recorded verbatim in the R10 gate and final receipt; Lead decision L-12 took responsibility for continuing after the R9 diagnostics-accounting stop",
            "spawn exit_code/stdout_tail persisted if available without code change, else disclosed",
            "builder dry_run C10 definitional false-negative remains disclosed",
            "preflight cases excluded from E1-E6 endpoints",
            "single seed descriptive only; cross-family pooling not allowed (~5.83% CDi relative difference); cross-family comparisons descriptive",
            "fuel_burn_kg=null; physical validation NOT_VALIDATED; three-layer conclusions kept separate",
            "cumulative charged if R10 completes = 448 starts / 3148 internal (prior 62/446 + R10 386/2702); caps 451/3157; headroom 3 starts/9 internal; no retry allowed; R10 is the final execution attempt under current caps (no R11)",
            "Lead decision L-12: R10 continues after the R9 diagnostics-accounting S1 stop (main NOT_RUN, physical 6/42); R9 permanently excluded; A5 FAIL-09 audit and any dissent recorded; R10 is a new preregistered batch, not a reuse of R9 approval; R10 is the final attempt, no R11",
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
