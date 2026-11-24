"""Freeze the facts about the aborted O0-B01 attempt into an explicit record.

The first O0 batch died inside bracket_rows() after a real VSPAERO start had already
completed, so one charged start exists on disk without a ledger row. This script
re-derives everything from the raw case directory instead of trusting memory, and
writes o0_batch_abort_B01.json. It never deletes or edits raw evidence.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
CASE = RUN / "cases" / "o0-d00-coarse"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    attempts_path = CASE / "solver_attempts.jsonl"
    rows = [json.loads(line) for line in
            attempts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    begin = next(r for r in rows if str(r.get("event")).lower() in ("begin", "start"))
    end = next(r for r in rows if r.get("event") == "end")
    case_result = json.loads((CASE / "case_result.json").read_text(encoding="utf-8"))
    evaluation = case_result.get("evaluation") or {}
    polar_rows = int(evaluation.get("accounting", {}).get("raw_polar_rows") or 0)
    raw_files = sorted(p.name for p in CASE.iterdir() if p.is_file())
    big = [p for p in CASE.iterdir()
           if p.is_file() and p.suffix.lower() in (".vspgeom", ".vspaero", ".polar",
                                                   ".history", ".adb", ".lod", ".vsp3")]
    payload = {
        "schema": "dreal005.o0_batch_abort_record.v1",
        "run_id": "DRECOVER001-O0-20261124-01",
        "batch_id_attempted": "DRECOVER001-O0-20261124-01-B01",
        "authorization_id": "AUTH-DREAL005-O0-20261124-01",
        "go_record_sha256": sha(RUN / "o0_go_record.json"),
        "created_utc": now(),
        "outcome": "ABORTED_BY_CODE_DEFECT_AFTER_ONE_CHARGED_START",
        "narrative": (
            "The batch acquired the run lock and evaluated bootstrap design 0 (the baseline) "
            "for real. The VSPAERO start completed and wrote a full case directory, but "
            "o0_eval.bracket_rows() then raised AttributeError because solver_runner.run_case() "
            "reports case_result as a path string, not as an inline object. The exception "
            "escaped evaluate_design() before AttemptLedger.settle(), so the run counters never "
            "saw the start. Nothing was deleted: the raw case, its polar, its solver ledger and "
            "its stdout/stderr logs are all still on disk."),
        "root_cause": {
            "exception": "AttributeError: 'str' object has no attribute 'get'",
            "file": "scripts/o0_eval.py",
            "old_line": 175,
            "old_code": 'rows = ((result.get("case_result") or {}).get("evaluation") or {}).get("rows") or []',
            "contract": ("solver_runner.run_case() returns case_result as "
                         "str(case_result_path), so the path has to be read before indexing"),
            "fix": ("bracket_rows() now loads the JSON file when case_result is a str or Path, "
                    "and keeps the inline-dict behaviour for callers that pass one"),
        },
        "charged_starts_actual": int(begin.get("physical_solver_starts") or 0) or 1,
        "internal_solver_cases_actual": int(end.get("internal_solver_cases") or 0),
        "design_evaluations_actual": 1,
        "admitted_labels_actual": 0,
        "retries_actual": 0,
        "parallelism": 1,
        "case": {
            "case_id": "o0-d00-coarse",
            "design_index": 0,
            "stage": "BOOTSTRAP",
            "is_baseline": True,
            "attempt_id": begin.get("attempt_id"),
            "status": end.get("status"),
            "exit_code": end.get("exit_code"),
            "wall_s": end.get("wall_s"),
            "polar_rows": polar_rows,
            "alpha_list_deg": [row.get("alpha_deg") for row in evaluation.get("rows") or []],
            "lift_match_status": (evaluation.get("lift_match") or {}).get("status"),
            "files": raw_files,
            "raw_artifact_paths": [str(p) for p in big],
            "raw_artifact_sha256": {p.name: sha(p) for p in big},
            "solver_attempts_jsonl_sha256": sha(attempts_path),
            "case_result_sha256": sha(CASE / "case_result.json"),
        },
        "why_no_label_was_admitted": (
            "Only the 7-point coarse bracket ran, at 0.35 deg spacing. Admission requires a "
            "raw polar row inside the 1e-3 relative lift tolerance, and the CL increment per "
            "0.35 deg is about 0.012, which is an order of magnitude coarser than the tolerance. "
            "The design therefore has no admissible raw row, and no tolerance was relaxed to "
            "manufacture one."),
        "accounting_consequence": (
            "One physical solver start is spent and must be carried into every later O0 count. "
            "It is recorded here rather than silently re-run, and no retry was granted."),
        "caps_after_this_abort": {"authorized_solver_starts": 36,
                                  "spent_solver_starts": 1,
                                  "remaining_solver_starts": 35,
                                  "authorized_internal_cases": 240,
                                  "spent_internal_cases": int(end.get("internal_solver_cases") or 0),
                                  "remaining_internal_cases": 240 - int(end.get("internal_solver_cases") or 0)},
        "lock_file_left_behind": str(RUN / "o0_run.lock"),
        "lock_disposition": ("Deleted after confirming the process was gone, because a stale "
                             "single-writer lock would otherwise block the corrected batch. The "
                             "deletion is recorded here."),
        "physics_validated": False,
        "note": ("This is an accounting and provenance record for the aborted attempt. It is not "
                 "a GO, not an A5 verdict and not an admitted label."),
    }
    out = RUN / "o0_batch_abort_B01.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"out": str(out), "sha256": sha(out),
                      "charged": payload["charged_starts_actual"],
                      "internal": payload["internal_solver_cases_actual"],
                      "admitted": payload["admitted_labels_actual"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
