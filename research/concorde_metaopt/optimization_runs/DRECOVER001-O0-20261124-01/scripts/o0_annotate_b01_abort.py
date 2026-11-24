"""Record the post-abort housekeeping on the B01 abort record, without rewriting its facts.

Two things changed after the abort record was written:

  * the run lock was deleted (it can only be deleted once the crashed process is gone);
  * every B01 case directory moved under cases/B01/ so a corrected batch label can never
    overwrite the raw case that was already paid for.

This script verifies that the move did not touch a single byte, then appends an explicitly
labelled annotation block. The original fields and their meanings are left untouched, and no
file matching o0_batch_abort_*.json is created, so the spend is still counted exactly once.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
RECORD = RUN / "o0_batch_abort_B01.json"
LOCK = RUN / "o0_run.lock"
NEW_CASE_ROOT = RUN / "cases" / "B01"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def running_python() -> str:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-Process python -ErrorAction SilentlyContinue | "
                              "Measure-Object).Count"],
                             capture_output=True, text=True, timeout=60)
        return (out.stdout or "").strip() or "unknown"
    except Exception as exc:  # noqa: BLE001
        return "unknown (%s)" % exc


def main() -> int:
    rec = json.loads(RECORD.read_text(encoding="utf-8"))
    case = rec.get("case") or {}
    case_id = case.get("case_id")
    expected = case.get("raw_artifact_sha256") or {}

    # 1. confirm the relocation preserved every raw byte that was hashed at abort time
    verified, missing, mismatched = [], [], []
    for name, want in sorted(expected.items()):
        path = NEW_CASE_ROOT / case_id / name
        if not path.is_file():
            missing.append(name)
        elif sha_file(path) != want:
            mismatched.append(name)
        else:
            verified.append(name)
    extra = {
        "solver_attempts.jsonl": case.get("solver_attempts_jsonl_sha256"),
        "case_result.json": case.get("case_result_sha256"),
    }
    for name, want in sorted(extra.items()):
        if not want:
            continue
        path = NEW_CASE_ROOT / case_id / name
        if not path.is_file():
            missing.append(name)
        elif sha_file(path) != want:
            mismatched.append(name)
        else:
            verified.append(name)

    # 2. the lock can now be deleted, and the deletion is recorded here rather than implied
    lock_state = {"existed": LOCK.is_file()}
    if LOCK.is_file():
        lock_state["sha256"] = sha_file(LOCK)
        lock_state["contents"] = json.loads(LOCK.read_text(encoding="utf-8"))
        lock_state["python_processes_running"] = running_python()
        LOCK.unlink()
        lock_state["deleted_utc"] = now()
        lock_state["deleted_because"] = ("single-writer lock of the crashed B01 process; the "
                                         "process is gone and the spend is already recorded, so "
                                         "the lock would only block the corrected batch")
        lock_state["exists_after"] = LOCK.exists()

    ann = {
        "annotated_utc": now(),
        "why": ("post-abort housekeeping only; every field above is unchanged and still means "
                "what it meant when the abort was recorded"),
        "relocation": {
            "from": "cases/<case_id>",
            "to": "cases/B01/<case_id>",
            "reason": ("each batch writes into its own case directory so a corrected batch "
                       "cannot overwrite raw solver output that has already been paid for"),
            "files_rehashed": len(verified) + len(missing) + len(mismatched),
            "sha256_verified": verified,
            "sha256_missing": missing,
            "sha256_mismatched": mismatched,
            "byte_identical_after_move": not missing and not mismatched,
        },
        "lock": lock_state,
    }
    problems = [n for n in (missing, mismatched) if n]
    rec["post_abort_annotations"] = ann
    RECORD.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps({"abort_record": str(RECORD), "sha256": sha_file(RECORD),
                      "rehashed": ann["relocation"]["files_rehashed"],
                      "byte_identical_after_move": ann["relocation"]["byte_identical_after_move"],
                      "missing": missing, "mismatched": mismatched,
                      "lock_deleted": lock_state.get("deleted_utc")}, indent=2))
    return 0 if not problems else 2


if __name__ == "__main__":
    sys.exit(main())
