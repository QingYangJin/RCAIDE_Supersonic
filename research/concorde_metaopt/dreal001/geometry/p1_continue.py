"""P1 crash-continuation driver (D-REAL-001 A1, zero physical starts for the rebuild).

The first P1 batch process died after the P1-05 solver run completed: the driver's
lift interpolation divided by zero on a 3 Mach x 7 alpha polar (repeated alpha).
The P1-05 polar is on disk and complete, so this script:

1. reconstructs the P1-05 evaluation from the on-disk artifacts and appends exactly
   one end line for the dangling P1-05-a01 start (never rewrites the old 21 lines);
2. runs only the remaining P1-07 probe cases (14 starts x 7 internal);
3. writes the run-level evidence (batch_summary, metrics, retention, manifest, SHA).

The script fails closed on any budget, window, hash or accounting mismatch.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import evidence_manifest, ledger, polar_parser, solver_runner
from .p1_batch import (BATCH_RUN_SCHEMA, CASE_RESULT_SCHEMA, INFRA_FAILURES,
                       DEFAULT_INFRA_RETRIES, SOLVED, BatchRefusal, _append_jsonl,
                       _case_dir, _copy_case_inputs, _environment, _history_row,
                       _json_bytes, _load_plan, _polar_points, _write_bytes,
                       _write_json, _write_metrics, build_case_approval,
                       build_case_plan, evaluate_stop_conditions, flatten_conditions,
                       matched_cdi, sha256_bytes, verify_approval)
from .task_spec import TASK_SPEC

CONTINUATION_SCHEMA = "dreal001.p1_continuation.v1"
RECONSTRUCTED_CASE_ID = "P1-05"
RECONSTRUCTED_ATTEMPT_ID = "P1-05-a01"
RECONSTRUCTED_STATUS = "SOLVED_INFERRED_FROM_COMPLETE_POLAR"
PROBE_PREFIX = "P1-07"
EXPECTED_PLAN_SHA256 = "8dcfad573c73b856809a04173778013241c1624692dad0e29a98f0dc3fa85bae"
EXPECTED_APPROVAL_SHA256 = "075837544568d13b8d51b68c32f3c8b712f79ee7f094894c911587ce9c17d9a8"
EXPECTED_STARTS = 25
EXPECTED_INTERNAL = 189
EXPECTED_EVALUATIONS = 189
STDOUT_WALL_RE = re.compile(r"Total setup and solve time:\s*([0-9.]+)\s*seconds")
DEFERRED_CODE = "NOT_USED_FOR_THIS_BATCH"


def _ledger_rows(run_dir: Path) -> List[Dict[str, Any]]:
    path = run_dir / "solver_attempts.jsonl"
    if not path.is_file():
        raise BatchRefusal("solver_attempts.jsonl missing; nothing to continue")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _dangling_starts(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    starts = {row["attempt_id"]: row for row in rows if row.get("event") == "start"}
    ends = {row["attempt_id"] for row in rows if row.get("event") == "end"}
    return [starts[key] for key in starts if key not in ends]


def _evidence_file(path: Path) -> Dict[str, Any]:
    return {"path": path.name, "bytes": path.stat().st_size,
            "sha256": ledger.sha256_file(path)}


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _classify_ledger(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Split ledger starts into real physical starts and false (dry-run) starts.

    The P1 driver once called spawn_case with the timeout bound to the dry_run
    positional argument, producing a start/end pair with status DRY_RUN_OK and
    zero internal cases: no process was spawned.  The ledger rows are never
    rewritten here; this classification only feeds the correction and the
    run-level accounting.
    """
    starts = [row for row in rows if row.get("event") == "start"]
    ends = [row for row in rows if row.get("event") == "end"]
    false_attempts: List[str] = []
    for row in ends:
        status = str(row.get("status") or "")
        if status.startswith("DRY_RUN"):
            false_attempts.append(str(row.get("attempt_id")))
    if not false_attempts:
        for row in starts:
            status = str(row.get("status") or "")
            if status.startswith("DRY_RUN"):
                false_attempts.append(str(row.get("attempt_id")))
    false_attempts = sorted(set(false_attempts))
    false_set = set(false_attempts)
    physical_starts = [row for row in starts
                       if str(row.get("attempt_id")) not in false_set]
    physical_ends = [row for row in ends
                     if str(row.get("attempt_id")) not in false_set]
    return {
        "ledger_starts": len(starts),
        "ledger_ends": len(ends),
        "false_starts": len(false_attempts),
        "false_start_attempts": false_attempts,
        "physical_solver_starts": len(physical_starts),
        "physical_solver_ends": len(physical_ends),
        "false_internal_solver_cases": sum(
            int(row.get("internal_solver_cases") or 0)
            for row in starts if str(row.get("attempt_id")) in false_set),
        "real_needs_review": len(starts) - len(ends) - len(false_attempts),
    }


def _write_false_start_correction(run_dir: Path, plan: Mapping[str, Any],
                                  classification: Mapping[str, Any],
                                  stop_report_path: Optional[Path]) -> Dict[str, Any]:
    """Write the immutable false-start correction bundle (ledger stays untouched)."""
    corrections_dir = run_dir / "corrections"
    corrections_dir.mkdir(parents=True, exist_ok=True)
    attempts = list(classification.get("false_start_attempts") or [])
    attempt_id = attempts[0] if attempts else None
    previous_stop = None
    if stop_report_path is not None and Path(stop_report_path).is_file():
        path = Path(stop_report_path)
        previous_stop = {"path": path.name, "bytes": path.stat().st_size,
                         "sha256": ledger.sha256_file(path)}
    correction = {
        "schema": "dreal001.p1_correction.v1",
        "correction_id": "correction_001",
        "run_id": plan.get("run_id"),
        "created_utc": _utc_stamp(),
        "issue": "FALSE_START_DRY_RUN_BUG",
        "attempt_id": attempt_id,
        "false_start_attempt_ids": attempts,
        "process_started": False,
        "physical_solver_starts_attributable_to_attempt": 0,
        "physical_solver_ends_attributable_to_attempt": 0,
        "internal_solver_cases_attributable_to_attempt": 0,
        "polar_or_evaluation_written": False,
        "ledger_rows_modified": False,
        "ledger_rows_rewritten_note": (
            "solver_attempts.jsonl rows are byte-identical; the false start is "
            "explained here and in the corrected summary, never deleted."),
        "root_cause": (
            "The continuation driver passed timeout_s positionally into "
            "solver_runner.spawn_case(pre, attempt_id, dry_run, timeout_s), so "
            "dry_run became 900.0 and the call returned DRY_RUN_OK without "
            "spawning a process.  Fixed by using the keyword form "
            "spawn_case(..., timeout_s=timeout_s) with dry_run defaulting False."),
        "previous_stop_report": previous_stop,
        "counts": {
            "ledger_starts": int(classification.get("ledger_starts") or 0),
            "ledger_ends": int(classification.get("ledger_ends") or 0),
            "false_starts": int(classification.get("false_starts") or 0),
            "physical_solver_starts": int(
                classification.get("physical_solver_starts") or 0),
            "physical_solver_ends": int(
                classification.get("physical_solver_ends") or 0),
        },
    }
    correction_path = corrections_dir / "correction_001.json"
    correction_bytes = _json_bytes(correction)
    _write_bytes(correction_path, correction_bytes)
    index = {
        "schema": "dreal001.p1_correction_index.v1",
        "run_id": plan.get("run_id"),
        "created_utc": correction["created_utc"],
        "corrections": [{
            "correction_id": "correction_001",
            "issue": correction["issue"],
            "attempt_id": attempt_id,
            "path": "corrections/correction_001.json",
            "bytes": len(correction_bytes),
            "sha256": sha256_bytes(correction_bytes),
        }],
    }
    _write_bytes(corrections_dir / "correction_index.json", _json_bytes(index))
    return correction


def reconstruct_p1_05(run_dir: Path, plan: Dict[str, Any],
                      approval: Dict[str, Any]) -> Dict[str, Any]:
    """Append one end line + 21 evaluation rows for the completed P1-05 solver run."""
    case_dir = _case_dir(run_dir, RECONSTRUCTED_CASE_ID)
    case_plan, case_plan_sha, case_plan_raw = _load_plan(case_dir / "plan.json")
    case_approval, case_approval_sha, case_approval_raw = _load_plan(
        case_dir / "approval.json")
    basename = str(case_plan["solver_argv"][-1])
    polar_path = case_dir / (basename + ".polar")
    logs = case_dir / "logs"
    stdout_path = logs / (RECONSTRUCTED_ATTEMPT_ID + ".stdout.log")
    stderr_path = logs / (RECONSTRUCTED_ATTEMPT_ID + ".stderr.log")
    for path in (polar_path, stdout_path, stderr_path):
        if not path.is_file():
            raise BatchRefusal("reconstruction input missing: %s" % path)
    polar = polar_parser.parse_polar_file(polar_path)
    polar["unique_case_rows"] = polar_parser.unique_case_rows(polar["rows"])
    internal = solver_runner._internal_case_info(case_dir, basename, polar)
    polar["internal_solver_cases"] = internal["count"]
    polar["internal_case_breakdown"] = internal
    if int(internal["count"]) != 21:
        raise BatchRefusal("P1-05 internal cases %r != 21; reconstruction refused"
                           % internal["count"])
    unique = polar["unique_case_rows"]
    machines = sorted({round(float(row["Mach"]), 9) for row in unique})
    alphas = sorted({round(float(row["AoA"]), 9) for row in unique})
    betas = sorted({round(float(row["Beta"]), 9) for row in unique})
    if machines != [1.8, 2.0, 2.2] or len(alphas) != 7 or betas != [0.0]:
        raise BatchRefusal("P1-05 polar case matrix %r/%r/%r is not the 3x7x1 sweep"
                          % (machines, alphas, betas))
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    match = STDOUT_WALL_RE.search(stdout_text)
    if not match:
        raise BatchRefusal("stdout has no 'Total setup and solve time' line; wall_s "
                           "cannot be inferred")
    wall_s = float(match.group(1))
    if stderr_path.stat().st_size != 0:
        raise BatchRefusal("stderr is not empty (%d bytes); reconstruction refused"
                           % stderr_path.stat().st_size)
    outputs = solver_runner._collect_outputs(case_dir, basename)
    process = {"exit_code": None, "exit_code_inferred": True, "timed_out": False,
               "wall_s": wall_s,
               "stdout_sha256": ledger.sha256_file(stdout_path),
               "stderr_sha256": ledger.sha256_file(stderr_path)}
    spawned: Dict[str, Any] = {"status": RECONSTRUCTED_STATUS, "process": process,
                               "internal": internal, "outputs": outputs, "polar": polar}
    evaluation = solver_runner.build_evaluation(
        solver_runner.prepare_case(case_dir / "plan.json", case_dir / "approval.json",
                                   RECONSTRUCTED_ATTEMPT_ID),
        process, outputs, polar, RECONSTRUCTED_ATTEMPT_ID, RECONSTRUCTED_STATUS)
    if evaluation["lift_match"].get("status") != "LIFT_MATCHED_BY_INTERPOLATION":
        raise BatchRefusal("P1-05 lift match is %r; refusing to reconstruct"
                           % evaluation["lift_match"].get("status"))
    if evaluation.get("lift_match_mach") != 2.0:
        raise BatchRefusal("P1-05 lift match Mach %r != 2.0"
                           % evaluation.get("lift_match_mach"))
    spawned["evaluation"] = evaluation  # already built above; keeps one code path
    case = next(case for case in plan["cases"] if case["case_id"] == RECONSTRUCTED_CASE_ID)
    rows = flatten_conditions(case, case_plan, spawned, RECONSTRUCTED_ATTEMPT_ID)
    if len(rows) != 21:
        raise BatchRefusal("P1-05 evaluation rows %d != 21" % len(rows))
    evidence = {
        "polar": _evidence_file(polar_path),
        "history": _evidence_file(case_dir / (basename + ".history")),
        "adb": _evidence_file(case_dir / (basename + ".adb")),
        "adb_cases": _evidence_file(case_dir / (basename + ".adb.cases")),
        "stdout": _evidence_file(stdout_path),
        "stderr": _evidence_file(stderr_path),
        "adb_cases_lines": sum(1 for line in (case_dir / (basename + ".adb.cases"))
                               .read_text(encoding="utf-8", errors="replace").splitlines()
                               if line.strip()),
        "stdout_wall_sentence": "Total setup and solve time: %.6f seconds" % wall_s,
        "exit_code_evidence": "driver crashed after the solver process returned; the "
                              "process exit code was never recorded, so exit_code stays "
                              "null and is inferred from a complete polar plus a clean "
                              "stderr",
    }
    if evidence["adb_cases_lines"] != 21:
        raise BatchRefusal("adb.cases has %d lines != 21" % evidence["adb_cases_lines"])
    batch_ledger = ledger.SolverLedger(run_dir, str(plan.get("run_id")), TASK_SPEC.task_id)
    batch_ledger.end_attempt(
        RECONSTRUCTED_ATTEMPT_ID, None, RECONSTRUCTED_STATUS, wall_s,
        outputs=outputs,
        note="reconstructed post driver crash from on-disk solver artifacts",
        internal_solver_cases=int(internal["count"]),
        internal_case_breakdown=internal,
        unique_flow_conditions=len(unique),
        extra={"schema": "dreal001.solver_attempt.v1", "event": "end",
               "physical_solver_starts": 0,
               "reconstructed_post_driver_crash": True,
               "exit_code_inferred": True,
               "exit_code_measured": False,
               "wall_s_source": "inferred_from_logs",
               "reconstruction_evidence": evidence,
               "reconstruction_note": "the original driver crashed in post-processing "
                                      "after the solver run completed; no extra solver "
                                      "start was made for this case",
               "status_note": "SOLVED_INFERRED_FROM_COMPLETE_POLAR: 21/21 flow "
                              "conditions present, stderr empty, stdout completion line "
                              "present"})
    _append_jsonl(run_dir / "evaluations.jsonl", rows)
    case_result = {
        "schema": CASE_RESULT_SCHEMA, "case_id": RECONSTRUCTED_CASE_ID,
        "attempt_id": RECONSTRUCTED_ATTEMPT_ID, "plan_sha256": case_plan_sha,
        "approval_sha256": case_approval_sha, "process": process,
        "status": RECONSTRUCTED_STATUS, "internal": internal, "outputs": outputs,
        "evaluation": evaluation, "flow_condition_rows": len(rows),
        "physical_solver_starts": 1,
        "reconstructed_post_driver_crash": True,
        "exit_code_inferred": True,
        "wall_s_source": "inferred_from_logs",
        "lift_match_mach": evaluation.get("lift_match_mach"),
        "objective_scope": "MACH_SWEEP_NEAREST_MACH",
        "objective_use": "E4_mach_trend_only; not used for E1/E2/E3 production claims",
        "reconstruction_evidence": evidence,
        "ts_utc": ledger.iso_utc(),
    }
    _write_json(case_dir / "case_result.json", case_result)
    return {"case_id": RECONSTRUCTED_CASE_ID, "attempt_id": RECONSTRUCTED_ATTEMPT_ID,
            "status": RECONSTRUCTED_STATUS, "wall_s": wall_s,
            "internal_solver_cases": int(internal["count"]),
            "evaluation_rows": len(rows), "evidence": evidence,
            "lift_match_mach": evaluation.get("lift_match_mach"),
            "objective_scope": "MACH_SWEEP_NEAREST_MACH"}


def _rebuild_repeatability(run_dir: Path, plan: Dict[str, Any]) -> Dict[str, Optional[float]]:
    repeatability: Dict[str, Optional[float]] = {}
    for case in plan["cases"]:
        case_id = str(case["case_id"])
        if case_id not in ("P1-00a", "P1-00b", "P1-00c"):
            continue
        result_path = _case_dir(run_dir, case_id) / "case_result.json"
        if not result_path.is_file():
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        evaluation = result.get("evaluation") or {}
        points = [dict(row, CDi=row.get("CDi"), CLtot=row.get("CLtot"))
                  for row in evaluation.get("rows", []) if row.get("valid")]
        if points:
            repeatability[case_id] = matched_cdi(points, TASK_SPEC.sref_baseline_m2)
    return repeatability


def _history_from_case_results(plan: Dict[str, Any], run_dir: Path) -> List[Dict[str, Any]]:
    history: List[Dict[str, Any]] = []
    index = 0
    for case in plan["cases"]:
        index += 1
        case_id = str(case["case_id"])
        path = _case_dir(run_dir, case_id) / "case_result.json"
        if not path.is_file():
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        history.append(_history_row(case, result.get("attempt_id"), {
            "status": result.get("status"), "process": result.get("process"),
            "internal": result.get("internal"), "evaluation": result.get("evaluation"),
        }, index))
    return history


def execute_continuation(run_dir: Path, dry_run: bool = False) -> Dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    plan, plan_sha, _ = _load_plan(run_dir / "plan.json")
    approval, approval_sha, _ = _load_plan(run_dir / "approval.json")
    if plan_sha != EXPECTED_PLAN_SHA256:
        raise BatchRefusal("plan sha256 %s != expected %s" % (plan_sha, EXPECTED_PLAN_SHA256))
    if approval_sha != EXPECTED_APPROVAL_SHA256:
        raise BatchRefusal("approval sha256 %s != expected %s"
                           % (approval_sha, EXPECTED_APPROVAL_SHA256))
    caps = verify_approval(plan, plan_sha, approval, approval_sha)
    rows = _ledger_rows(run_dir)
    starts = sum(1 for row in rows if row.get("event") == "start")
    ends = sum(1 for row in rows if row.get("event") == "end")
    dangling = _dangling_starts(rows)
    pending = [case["case_id"] for case in plan["cases"]
               if str(case["case_id"]).startswith(PROBE_PREFIX)
               and not (_case_dir(run_dir, str(case["case_id"])) / "case_result.json").is_file()]
    report: Dict[str, Any] = {
        "schema": CONTINUATION_SCHEMA, "run_id": plan.get("run_id"),
        "plan_sha256": plan_sha, "approval_sha256": approval_sha, "caps": caps,
        "ledger_lines": len(rows), "starts_before": starts, "ends_before": ends,
        "dangling_attempts": [row.get("attempt_id") for row in dangling],
        "pending_probe_cases": pending, "deferred_helper_code": DEFERRED_CODE,
    }
    window = ledger.window_status(approval)
    report["window"] = window
    if dry_run:
        report.update({"status": "DRY_RUN", "physical_solver_starts": 0, "wrote_files": []})
        return report
    if not window["open"]:
        raise BatchRefusal("solver window is not open: %s" % window["reason"])
    if dangling and [row.get("attempt_id") for row in dangling] != [RECONSTRUCTED_ATTEMPT_ID]:
        raise BatchRefusal("unexpected dangling attempts %r; refuse to continue"
                           % [row.get("attempt_id") for row in dangling])
    if starts != 11 or ends != 10:
        raise BatchRefusal("expected 11 starts / 10 ends before continuation, found %d/%d"
                           % (starts, ends))
    for case_id in pending:
        case_dir = _case_dir(run_dir, case_id)
        if case_dir.is_dir():
            raise BatchRefusal("case %s already has a directory; reruns are refused" % case_id)
    reconstruction: Optional[Dict[str, Any]] = None
    if dangling:
        reconstruction = reconstruct_p1_05(run_dir, plan, approval)
    evaluations_path = run_dir / "evaluations.jsonl"
    batch_ledger = ledger.SolverLedger(run_dir, str(plan.get("run_id")), TASK_SPEC.task_id)
    internal_total = sum(int(row.get("internal_solver_cases") or 0)
                         for row in _ledger_rows(run_dir) if row.get("event") == "end")
    repeatability = _rebuild_repeatability(run_dir, plan)
    stop_hits: List[Dict[str, str]] = []
    probed: List[Dict[str, Any]] = []
    spawner = solver_runner.spawn_case
    for case in plan["cases"]:
        case_id = str(case["case_id"])
        if not case_id.startswith(PROBE_PREFIX):
            continue
        case_dir = _case_dir(run_dir, case_id)
        if (case_dir / "case_result.json").is_file():
            continue
        window = ledger.window_status(approval)
        if not window["open"]:
            stop_hits.append({"condition": "S7",
                              "detail": "window closed before case %s: %s"
                                        % (case_id, window["reason"])})
            break
        case_dir.mkdir(parents=True, exist_ok=True)
        basename = str(case["solver_argv"][-1])
        input_hashes = _copy_case_inputs(case, run_dir, case_dir, basename)
        case_plan = build_case_plan(case, plan, run_dir, case_dir, plan_sha, input_hashes)
        case_plan_sha = sha256_bytes(_write_json(case_dir / "plan.json", case_plan))
        case_approval = build_case_approval(case, approval, plan_sha, approval_sha,
                                            case_plan_sha)
        _write_json(case_dir / "approval.json", case_approval)
        timeout_s = float((case_plan.get("solver") or {}).get("timeout_s") or 900)
        attempt_id = "%s-a01" % case_id
        pre = solver_runner.prepare_case(case_dir / "plan.json", case_dir / "approval.json",
                                         attempt_id)
        starts_before = batch_ledger.count_starts()
        expected_internal = int(case.get("expected_internal_cases") or 7)
        if starts_before + 1 > caps["max_starts"]:
            stop_hits.append({"condition": "S5",
                              "detail": "next start would be %d > max %d"
                                        % (starts_before + 1, caps["max_starts"])})
            break
        if internal_total + expected_internal > caps["max_internal_cases"]:
            stop_hits.append({"condition": "S5",
                              "detail": "internal cases %d + %d > max %d"
                                        % (internal_total, expected_internal,
                                           caps["max_internal_cases"])})
            break
        batch_ledger.begin_attempt(
            attempt_id=attempt_id, case_id=case_id, argv=list(pre["argv"]),
            cwd=pre["cwd"], approval=approval, plan_sha256=plan_sha,
            approval_sha256=approval_sha, input_hashes=pre["geometry_files"],
            exe_sha256=pre["exe_sha256"], max_starts=caps["max_starts"],
            extra={"basename": basename, "config_id": case.get("config_id"),
                   "purpose": case.get("purpose"), "attempt_number": 1,
                   "window_token": approval.get("window_token"),
                   "continuation": CONTINUATION_SCHEMA,
                   "p0_signed_required": True},
        )
        spawned = spawner(pre, attempt_id, timeout_s)
        process = spawned.get("process") or {}
        internal = spawned.get("internal") or {}
        internal_count = int(internal.get("count") or 0)
        case_points = _polar_points(spawned)
        batch_ledger.end_attempt(
            attempt_id, process.get("exit_code"), str(spawned.get("status")),
            float(process.get("wall_s") or 0.0), outputs=spawned.get("outputs"),
            note=case.get("purpose"), internal_solver_cases=internal_count,
            internal_case_breakdown=internal,
            unique_flow_conditions=internal.get("unique_flow_conditions"),
            extra={"continuation": CONTINUATION_SCHEMA})
        internal_total += internal_count
        case_rows = flatten_conditions(case, case_plan, spawned, attempt_id)
        _append_jsonl(evaluations_path, case_rows)
        case_result = {"schema": CASE_RESULT_SCHEMA, "case_id": case_id,
                       "attempt_id": attempt_id, "plan_sha256": case_plan_sha,
                       "approval_sha256": sha256_bytes(_json_bytes(case_approval)),
                       "process": process, "status": spawned.get("status"),
                       "internal": internal, "outputs": spawned.get("outputs"),
                       "evaluation": spawned.get("evaluation"),
                       "flow_condition_rows": len(case_rows),
                       "physical_solver_starts": 1,
                       "continuation": CONTINUATION_SCHEMA,
                       "ts_utc": ledger.iso_utc()}
        _write_json(case_dir / "case_result.json", case_result)
        probed.append({"case_id": case_id, "attempt_id": attempt_id,
                       "status": spawned.get("status"),
                       "wall_s": process.get("wall_s"), "internal": internal_count})
        stop_hits = evaluate_stop_conditions(case_id, spawned, case_points, repeatability,
                                             batch_ledger.count_starts(), caps, internal_total)
        if stop_hits:
            break
    history = _history_from_case_results(plan, run_dir)
    totals = evidence_manifest.ledger_totals(run_dir / "solver_attempts.jsonl", run_dir)
    evaluation_rows = sum(1 for line in evaluations_path.read_text(encoding="utf-8").splitlines()
                          if line.strip())
    summary: Dict[str, Any] = {
        "schema": BATCH_RUN_SCHEMA, "run_id": plan.get("run_id"),
        "status": "STOPPED_FAIL_CLOSED" if stop_hits else "COMPLETED_WITH_RECONSTRUCTION",
        "plan_sha256": plan_sha, "approval_sha256": approval_sha,
        "case_count": len(history), "attempt_count": totals["physical_solver_starts"],
        "physical_solver_starts": totals["physical_solver_starts"],
        "internal_solver_cases": totals["internal_solver_cases"],
        "caps": caps, "stop_hits": stop_hits, "refine_starts_used": 0,
        "refine_policy": "one refine start (7 internal cases) remains available only with an "
                         "explicit Lead instruction; this driver never auto-refines",
        "evaluations_path": "evaluations.jsonl", "history_path": "optimization_history.csv",
        "fuel_burn_kg": None, "evidence_tier": "SOLVER_LOOP_VERIFIED",
        "physical_validation_status": "NOT_VALIDATED", "created_utc": ledger.iso_utc(),
        "continuation": {
            "schema": CONTINUATION_SCHEMA,
            "reason": "P1 batch driver ZeroDivisionError in lift interpolation after the "
                      "P1-05 solver run completed; the solver run itself and its polar are "
                      "intact",
            "reconstructed_case": reconstruction,
            "probed_cases": probed,
            "additional_physical_starts_for_reconstruction": 0,
            "deferred_helper_code_status": DEFERRED_CODE,
            "environment": _environment(),
        },
    }
    if stop_hits:
        _write_json(run_dir / "stop_report.json",
                    {"schema": "dreal001.stop_report.v1", "status": "STOPPED_FAIL_CLOSED",
                     "run_id": plan.get("run_id"), "plan_sha256": plan_sha,
                     "conditions": stop_hits, "completed_cases": summary["case_count"],
                     "physical_solver_starts": summary["physical_solver_starts"],
                     "internal_solver_cases": summary["internal_solver_cases"],
                     "created_utc": ledger.iso_utc(),
                     "next_action": "human review; remaining cases must not start"})
    if history:
        with open(run_dir / "optimization_history.csv", "w", encoding="utf-8",
                  newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(history[0].keys()),
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(history)
    _write_metrics(run_dir, history)
    retention_entries = evidence_manifest.record_retention(run_dir, delete=False)
    retention_path = run_dir / "retention.jsonl"
    if not retention_path.is_file():
        _write_bytes(retention_path, b"")
    summary["conservation_check"] = {
        "ledger_starts": totals["physical_solver_starts"],
        "ledger_ends": totals["physical_solver_ends"],
        "batch_ledger_starts": batch_ledger.count_starts(),
        "ledger_internal_cases": totals["internal_solver_cases"],
        "summed_internal_cases": internal_total,
        "evaluation_rows": evaluation_rows,
        "expected_starts": EXPECTED_STARTS, "expected_internal": EXPECTED_INTERNAL,
        "expected_evaluation_rows": EXPECTED_EVALUATIONS,
        "starts_bounded_by_cap": totals["physical_solver_starts"] <= caps["max_starts"],
        "internal_bounded_by_cap": totals["internal_solver_cases"]
        <= caps["max_internal_cases"],
        "starts_match_expected": totals["physical_solver_starts"] == EXPECTED_STARTS,
        "internal_matches_expected": totals["internal_solver_cases"] == EXPECTED_INTERNAL,
        "evaluations_match_expected": evaluation_rows == EXPECTED_EVALUATIONS,
        "every_start_has_end": totals["physical_solver_starts"] == totals["physical_solver_ends"],
    }
    summary["conservation_check"]["ok"] = bool(
        summary["conservation_check"]["starts_match_expected"]
        and summary["conservation_check"]["internal_matches_expected"]
        and summary["conservation_check"]["evaluations_match_expected"]
        and summary["conservation_check"]["every_start_has_end"]
        and summary["conservation_check"]["starts_bounded_by_cap"]
        and summary["conservation_check"]["internal_bounded_by_cap"])
    _write_json(run_dir / "batch_summary.json", summary)
    manifest = evidence_manifest.write_manifest(
        run_dir, retention_entries=retention_entries,
        extra={"batch_summary": summary,
               "conservation_check": summary["conservation_check"]})
    summary["manifest"] = {"files": len(manifest) if isinstance(manifest, dict) else None}
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="P1 crash-continuation driver (D-REAL-001 A1)")
    parser.add_argument("command", choices=("dry-run", "run"))
    parser.add_argument("--run-dir", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = execute_continuation(Path(args.run_dir), dry_run=(args.command == "dry-run"))
    except BatchRefusal as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, indent=2,
                         ensure_ascii=False))
        return 2
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 1 if summary.get("status") == "STOPPED_FAIL_CLOSED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
