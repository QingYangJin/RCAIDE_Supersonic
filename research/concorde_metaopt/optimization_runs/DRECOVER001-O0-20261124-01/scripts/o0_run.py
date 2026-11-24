"""Execute the O0 short BO batch (Issue #15) with a resource monitor and full tables.

The BO loop lives in research.concorde_metaopt.dreal001.ops.o0_short_bo; this module only
supplies the injected evaluator (o0_eval.evaluate_design_logged), the run lock, the
resource monitor, the stop conditions and the tabular outputs. It refuses to start unless
the GO record exists and its SHAs still match disk.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(RUN / "scripts"))

import o0_eval as ev  # noqa: E402
import o0_spend  # noqa: E402
from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0  # noqa: E402
from research.concorde_metaopt.dreal001.ops.resource_monitor import ResourceMonitor  # noqa: E402

GO = RUN / "o0_go_record.json"
LOCK = RUN / "o0_run.lock"
LOG = RUN / "o0_attempts.jsonl"
TABLES = RUN / "tables"
METADATA = RUN / "metadata"


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_go() -> Dict[str, Any]:
    if not GO.is_file():
        raise SystemExit("NO_GO: %s does not exist" % GO)
    go = json.loads(GO.read_text(encoding="utf-8"))
    if not go.get("go_issued"):
        raise SystemExit("NO_GO: go_issued is false")
    problems = []
    if go["a5_dossier_sha256"] != sha_file(RUN / "o0_a5_dossier.md"):
        problems.append("dossier changed after the A5 review")
    receipt = RUN / "o0_dossier_receipt.json"
    if not receipt.is_file():
        problems.append("dossier receipt is missing")
    else:
        rec = json.loads(receipt.read_text(encoding="utf-8"))
        if (rec.get("dossier") or {}).get("sha256") != go["a5_dossier_sha256"]:
            problems.append("dossier receipt disagrees with the GO dossier hash")
        if go.get("a5_dossier_receipt_sha256") not in (None, sha_file(receipt)):
            problems.append("dossier receipt changed after the GO")
    if go["a5_verdict_sha256"] != sha_file(RUN / "a5_review/verdict.json"):
        problems.append("a5 verdict file changed after the GO")
    if go["preregistration_sha256"] != sha_file(RUN / "o0_preregistration.json"):
        problems.append("preregistration changed after the GO")
    if go.get("batch_id") != ev.batch_id():
        problems.append("GO authorizes batch %r but this process would run batch %r"
                        % (go.get("batch_id"), ev.batch_id()))
    # A GO issued before an abort record existed would understate what has been spent.
    if int((go.get("carried_forward") or {}).get("solver_starts") or -1) != prior_spend()["solver_starts"]:
        problems.append("GO carried_forward.solver_starts does not match the abort/crash "
                        "records on disk")
    for rel, expected in go["code_shas"].items():
        path = Path(rel)
        if not path.is_absolute():
            path = REPO / rel
            if not path.is_file():
                path = RUN / rel
        if not path.is_file():
            problems.append("missing code file %s" % rel)
        elif sha_file(path) != expected:
            problems.append("code sha drift: %s" % rel)
    if problems:
        raise SystemExit("GO_INVALID: " + "; ".join(problems))
    return go


CRASH_RECORDS = "o0_batch_crash_*.json"
ABORT_RECORDS = "o0_batch_abort_*.json"


def spend_of(row: Dict[str, Any]) -> Tuple[int, int, int]:
    """Read one abort/crash record's spend, whichever shape it was written in.

    The two record kinds are written by different code paths and do not share key names: an
    abort record (written by hand off the raw case directory) carries charged_starts_actual /
    internal_solver_cases_actual / design_evaluations_actual at the top level, while a crash
    record (written by this runner) nests the ledger summary under "ledger" with
    solver_starts_actual / internal_solver_cases_actual / design_attempts. Reading only one
    shape silently counts a crashed batch as having spent nothing, which is the exact failure
    this function exists to prevent, so both are read and a record that matches neither is a
    hard error rather than a zero.
    """
    if "charged_starts_actual" in row or "design_evaluations_actual" in row:
        return (int(row.get("design_evaluations_actual") or 0),
                int(row.get("charged_starts_actual") or 0),
                int(row.get("internal_solver_cases_actual") or 0))
    ledger = row.get("ledger")
    if isinstance(ledger, dict) and ("solver_starts_actual" in ledger
                                     or "design_attempts" in ledger):
        return (int(ledger.get("design_attempts") or 0),
                int(ledger.get("solver_starts_actual") or 0),
                int(ledger.get("internal_solver_cases_actual") or 0))
    raise SystemExit("UNREADABLE_SPEND_RECORD: %r carries no spend this code can read; a "
                     "record that cannot be read is not a zero bill" % row.get("schema"))
    
def prior_spend() -> Dict[str, int]:
    """What earlier batches under this authorization already spent, counted exactly once.

    The caps belong to the authorization, not to one process. Counting is delegated to
    scripts/o0_spend.py because the two record shapes do not use the same basis: an abort record
    is batch-local, while a crash record's ledger summary is authorization-cumulative and already
    includes what it carried forward. Summing them would bill 24 starts for the 23 an
    authorization spent; reading only one would understate the bill. Both are wrong in the
    direction that matters, so the rule lives in one audited place.
    """
    spend = o0_spend.authorization_spend(RUN)
    return {"design_attempts": spend["design_attempts"],
            "solver_starts": spend["solver_starts"],
            "internal_solver_cases": spend["internal_solver_cases"],
            "records": [{"record": r["name"], "sha256": r["sha256"], "basis": r["basis"],
                         "charged_starts": r["starts"], "internal_solver_cases": r["internal"],
                         "design_evaluations": r["designs"]} for r in spend["records"]],
            "counting_rule": spend["rule"],
            "basis_record": spend["basis_record"]}


def acquire_lock() -> None:
    if LOCK.exists():
        raise SystemExit("RUN_LOCK exists: %s (delete only after confirming it is stale)"
                         % LOCK)
    LOCK.write_text(json.dumps({"pid": id(object()), "created_utc": now(),
                                "note": "single-writer lock for the O0 batch"},
                               indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]], columns: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in columns})


def landing_rows(attempts) -> List[Dict[str, Any]]:
    out = []
    for attempt in attempts:
        coarse = attempt.coarse or {}
        refine = attempt.refine or {}
        out.append({
            "design_index": attempt.design_index, "stage": attempt.stage,
            "design_id": attempt.design_id, "geometry_sha256": attempt.geometry_sha256,
            "is_baseline": attempt.is_baseline,
            "sweep_1": attempt.x12[2], "sweep_2": attempt.x12[3],
            "status": attempt.status, "feasible": attempt.feasible,
            "objective_di_n": attempt.objective, "di_n": attempt.di_n,
            "cl": attempt.cl, "cdi": attempt.cdi, "alpha_deg": attempt.alpha_deg,
            "sref_m2": attempt.sref_m2, "q_pa": attempt.q_pa,
            "lift_rel_error": attempt.lift_rel_error,
            "failure_kind": attempt.failure_kind, "detail": attempt.detail,
            "starts": attempt.starts, "internal": attempt.internal,
            "coarse_case": coarse.get("case_id"), "refine_case": refine.get("case_id"),
            "predicted_alpha_deg": refine.get("predicted_alpha_deg"),
            "audit_id": attempt.audit_id, "admission_id": attempt.admission_id,
            "acquisition": json.dumps(attempt.acquisition, ensure_ascii=False)
            if attempt.acquisition else "",
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-attempts", type=int, default=o0.CAPS["max_design_attempts"])
    parser.add_argument("--bootstrap", type=int, default=o0.CAPS["bootstrap_attempts"])
    parser.add_argument("--seed", type=int, default=20261124)
    parser.add_argument("--smoke", action="store_true",
                        help="build the baseline case and dry-run it; no solver start")
    parser.add_argument("--label", default="B02")
    args = parser.parse_args()
    # Every case path is scoped to the batch label so a corrected batch can never overwrite
    # the raw case that B01 already paid for.
    ev.set_label(args.label)

    if args.smoke:
        case = ev.make_case(o0.BASELINE_X12, "smoke", "coarse", o0.coarse_alphas(),
                            ev.cl_target_for(o0.BASELINE_X12), o0.COARSE_ALPHA_GUESS_DEG)
        result = ev.run(case, "smoke-coarse", dry_run=True)
        print(json.dumps({"dry_run_status": result.get("status"),
                          "physical_solver_starts": result.get("physical_solver_starts"),
                          "case": case["case_id"]}, indent=2))
        return 0 if result.get("status") == "DRY_RUN_OK" else 2

    o0.assert_execution_contract()
    go = check_go()
    acquire_lock()
    TABLES.mkdir(parents=True, exist_ok=True)
    METADATA.mkdir(parents=True, exist_ok=True)
    started = time.time()
    monitor = ResourceMonitor(RUN / "o0_resource.jsonl", interval_s=1.0,
                              label="O0-BO-%s" % args.label)
    monitor.start()

    class Abort(Exception):
        pass

    def evaluate(attempt):
        done = ev.evaluate_design_logged(attempt, LOG)
        if done.is_baseline and done.status != "FEASIBLE_ADMITTED":
            raise Abort("baseline design did not yield an admitted real row: %s (%s)"
                        % (done.status, done.failure_kind))
        if time.time() - started > o0.CAPS["wall_clock_s"]:
            raise Abort("wall clock cap reached after %d attempts" % attempt.design_index)
        return done

    prior = prior_spend()
    if prior["solver_starts"] == 0:
        raise SystemExit("REFUSING_TO_RUN: the abort/crash records show no earlier spend under "
                         "this authorization, but batch B01 charged one start; a missing record "
                         "is not a zero bill")
    ledger = o0.AttemptLedger(prior_design_attempts=prior["design_attempts"],
                              prior_starts=prior["solver_starts"],
                              prior_internal=prior["internal_solver_cases"])
    aborted = None
    try:
        result = o0.run_bo_loop(evaluate=evaluate, ledger=ledger, seed=args.seed,
                                max_attempts=args.max_attempts,
                                bootstrap_count=args.bootstrap)
    except Abort as exc:
        aborted = "ABORT: %s" % exc
        result = {"schema": o0.SCHEMA, "protocol_id": o0.PROTOCOL_ID,
                  "aborted": aborted, "ledger": ledger.summary(),
                  "attempts": [a.as_dict() for a in ledger.attempts]}
    except Exception as exc:  # noqa: BLE001 - any crash must still be accounted for
        # O0-B01 died inside the evaluator and therefore wrote no tables at all, so the one
        # start it had already spent only existed in the raw case directory. A crash is
        # now recorded like any other abort: the ledger already settled the spent starts
        # (o0_short_bo.evaluate_and_settle), and the batch accounting below still gets
        # written with the exception text as the abort reason.
        aborted = "CRASH: %s: %s" % (type(exc).__name__, exc)
        result = {"schema": o0.SCHEMA, "protocol_id": o0.PROTOCOL_ID,
                  "aborted": aborted, "ledger": ledger.summary(),
                  "attempts": [a.as_dict() for a in ledger.attempts]}
        crash = {"schema": "dreal005.o0_batch_crash.v1", "label": args.label,
                 "created_utc": now(), "exception_type": type(exc).__name__,
                 "exception_text": str(exc), "ledger": ledger.summary(),
                 "lock_file": str(LOCK), "lock_contents": (
                     json.loads(LOCK.read_text(encoding="utf-8"))
                     if LOCK.is_file() else None),
                 "lock_disposition": ("left in place on purpose: a crashed batch keeps its "
                                      "single-writer lock until the crash has been read; "
                                      "delete it only after recording why")}
        (RUN / ("o0_batch_crash_%s.json" % args.label)).write_text(
            json.dumps(crash, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
    monitor.stop()
    summary = monitor.summary()
    wall = time.time() - started

    attempts = ledger.attempts
    landing = landing_rows(attempts)
    write_csv(TABLES / ("o0_optimization_history_%s.csv" % args.label), landing, [
        "design_index", "stage", "design_id", "geometry_sha256", "is_baseline",
        "sweep_1", "sweep_2", "status", "feasible", "objective_di_n", "di_n", "cl",
        "cdi", "alpha_deg", "sref_m2", "q_pa", "lift_rel_error", "failure_kind",
        "detail", "starts", "internal", "coarse_case", "refine_case",
        "predicted_alpha_deg", "audit_id", "admission_id", "acquisition"])
    write_csv(TABLES / ("o0_all_evaluations_%s.csv" % args.label), landing, [
        "design_index", "stage", "design_id", "is_baseline", "sweep_1", "sweep_2",
        "status", "feasible", "di_n", "alpha_deg", "lift_rel_error", "starts",
        "internal", "failure_kind"])
    write_csv(TABLES / ("o0_admitted_labels_%s.csv" % args.label),
              [r for r in landing if r["status"] == "FEASIBLE_ADMITTED"],
              ["design_index", "design_id", "admission_id", "audit_id", "di_n", "cl",
               "cdi", "alpha_deg", "sref_m2", "q_pa", "lift_rel_error", "starts",
               "internal"])
    write_csv(TABLES / ("o0_failed_or_null_%s.csv" % args.label),
              [r for r in landing if r["status"] != "FEASIBLE_ADMITTED"],
              ["design_index", "design_id", "status", "failure_kind", "detail",
               "starts", "internal"])
    write_csv(TABLES / ("o0_actual_solver_ledger_%s.csv" % args.label), landing, [
        "design_index", "design_id", "stage", "starts", "internal", "status",
        "coarse_case", "refine_case"])

    batch_starts = sum(a.starts for a in attempts)
    batch_internal = sum(a.internal for a in attempts)
    accounting = {
        "schema": "dreal005.o0_batch_accounting.v1",
        "run_id": ev.RUN_ID, "batch_id": ev.batch_id(),
        "authorization_id": ev.AUTH_ID, "label": args.label,
        "created_utc": now(),
        "go_record_sha256": sha_file(GO),
        "a5_verdict": go["a5_verdict"],
        # Batch-level spend, and the authorization-level total that includes what earlier
        # batches already consumed. Only the authorization-level number may be compared
        # with the caps; reporting the batch number alone would understate real spend.
        "physical_solver_starts_actual": batch_starts,
        "internal_solver_cases_actual": batch_internal,
        "authorization_physical_solver_starts_actual": ledger.starts_used,
        "authorization_internal_solver_cases_actual": ledger.internal_used,
        "carried_forward": ledger.summary()["carried_forward"],
        "carried_forward_records": prior["records"],
        "charged_starts": batch_starts,
        "planned_reserved_starts": o0.CAPS["max_solver_starts"],
        "design_evaluations": len(attempts),
        "cached_reads": 0,
        "retries": o0.CAPS["retries"],
        "parallelism": o0.CAPS["parallelism"],
        "starts_per_design_cap": o0.CAPS["max_starts_per_design"],
        "internal_cases_per_design_cap": o0.CAPS["max_internal_per_design"],
        "execution_contract_asserted": True,
        "max_consecutive_unadmitted_designs": o0.CAPS["max_consecutive_unadmitted_designs"],
        "stopped_by_unadmitted_streak": result.get("stopped_by_unadmitted_streak"),
        "admitted_labels": sum(1 for a in attempts if a.status == "FEASIBLE_ADMITTED"),
        "null_or_failed": sum(1 for a in attempts if a.status != "FEASIBLE_ADMITTED"),
        "valid_label_rate": (sum(1 for a in attempts if a.status == "FEASIBLE_ADMITTED")
                             / max(1, len(attempts))),
        "caps": o0.CAPS,
        "remaining": ledger.remaining(),
        "wall_clock_s": wall,
        "aborted": aborted,
        "resource_log": str(RUN / "o0_resource.jsonl"),
        "resource_summary": summary,
        "physics_validated": False,
        "physical_interpretation": ("lifting-surface VSPAERO internal only; forced-lift "
                                    "induced drag at fixed Mach and altitude"),
    }
    (RUN / ("o0_batch_accounting_%s.json" % args.label)).write_text(
        json.dumps(accounting, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    (RUN / ("o0_result_%s.json" % args.label)).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in accounting.items()
                      if k in ("physical_solver_starts_actual", "internal_solver_cases_actual",
                               "admitted_labels", "null_or_failed", "valid_label_rate",
                               "design_evaluations", "wall_clock_s", "aborted")},
                     ensure_ascii=False, indent=2))
    return 0 if not aborted else 3


if __name__ == "__main__":
    raise SystemExit(main())