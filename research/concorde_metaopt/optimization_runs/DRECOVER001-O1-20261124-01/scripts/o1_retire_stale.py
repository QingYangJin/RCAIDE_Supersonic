"""Retire authorization artifacts that bind bytes other than the ones on disk.

Why this exists
---------------
A GO is only meaningful if it is obviously the GO for the bytes that are on disk right now.
If a PASS verdict or a binding round left over from an earlier release sits on the live path
next to a freshly re-signed dossier, then a GO issued today would look exactly like a GO
issued against the superseded bytes: a reader (or a later reviewer) cannot tell them apart
from the live path alone.

So stale artifacts are not deleted -- deleting evidence is worse than the disease -- they are
moved into dated history directories and removed from the live path, which leaves exactly one
verdict and one binding round visible for the current bytes.

Rules, all fail-closed:
  * an artifact is retired only when it names a dossier or preregistration sha256 that is not
    the sha256 on disk;
  * an artifact that names the bytes on disk is never touched;
  * an archived file is written under a timestamped name and then removed from the live path,
    and the removal is recorded in the retire record;
  * nothing is ever deleted without first being written somewhere else, byte for byte.

Run: python scripts/o1_retire_stale.py [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
DOSSIER = RUN / "o1_a5_dossier.md"
PREREG = RUN / "o1_preregistration.json"
VERDICT = RUN / "a5_review" / "verdict.json"
VERDICT_COPY = RUN / "o1_a5_verdict.json"
VERIFY = RUN / "o1_binding_verification.json"
GO = RUN / "o1_go_record.json"
VERDICT_HISTORY = RUN / "a5_review" / "history"
BINDING_HISTORY = RUN / "a5_support" / "binding_history"
GO_HISTORY = RUN / "go_history"
RECORD = RUN / "o1_retire_record.json"
SCHEMA = "dreal005.o1_retire_record.v1"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"__unreadable__": str(exc)}


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def retire(path: Path, reason: str, target_dir: Path, dry_run: bool) -> dict:
    """Move one stale artifact into history, byte for byte, and report the move."""
    payload = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha(path),
        "reason": reason,
        "target_dir": str(target_dir),
        "archived_as": None,
        "removed_from_the_live_path": False,
    }
    if dry_run:
        return payload
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / ("%s_%s_%s" % (path.stem, stamp(), payload["sha256"][:16]))
    if target.suffix != path.suffix:
        target = target.with_suffix(path.suffix)
    shutil.copy2(path, target)
    if sha(target) != payload["sha256"]:
        raise SystemExit("copy of %s does not match the original; nothing removed" % (path,))
    payload["archived_as"] = str(target)
    path.unlink()
    payload["removed_from_the_live_path"] = True
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Retire O1 authorization artifacts for superseded bytes")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not DOSSIER.is_file() or not PREREG.is_file():
        raise SystemExit("dossier or preregistration missing; nothing to compare against")
    dossier_sha = sha(DOSSIER)
    prereg_sha = sha(PREREG)

    retired = []
    kept = []

    # The verdict that a GO would consult.
    for path, history in ((VERDICT, VERDICT_HISTORY), (VERDICT_COPY, VERDICT_HISTORY)):
        payload = load(path)
        if payload is None:
            continue
        if "__unreadable__" in payload:
            retired.append(retire(path, "unreadable verdict cannot be trusted for a GO", history,
                                  args.dry_run))
            continue
        names = payload.get("dossier_sha256")
        if names == dossier_sha and payload.get("preregistration_sha256") in (None, prereg_sha):
            kept.append({"path": str(path), "why": "binds the dossier on disk"})
            continue
        retired.append(retire(path, "verdict binds dossier %r, disk is %r"
                              % (names, dossier_sha), history, args.dry_run))

    # The binding round a GO would consult.
    payload = load(VERIFY)
    if payload is not None:
        names = payload.get("dossier", {}).get("sha256")
        names_prereg = payload.get("preregistration", {}).get("sha256")
        if names == dossier_sha and names_prereg in (None, prereg_sha):
            kept.append({"path": str(VERIFY), "why": "binding round is over the bytes on disk"})
        else:
            retired.append(retire(VERIFY, "binding round covers dossier %r / prereg %r, disk is %r / %r"
                                  % (names, names_prereg, dossier_sha, prereg_sha),
                                  BINDING_HISTORY, args.dry_run))

    # A GO, if one was ever written, is retired the same way when it names other bytes.
    payload = load(GO)
    if payload is not None:
        names = payload.get("a5_dossier_sha256")
        if names == dossier_sha and payload.get("preregistration_sha256") in (None, prereg_sha):
            kept.append({"path": str(GO), "why": "GO binds the bytes on disk"})
        else:
            retired.append(retire(GO, "GO binds dossier %r, disk is %r" % (names, dossier_sha),
                                  GO_HISTORY, args.dry_run))

    record = {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": bool(args.dry_run),
        "dossier_on_disk": {"path": str(DOSSIER), "sha256": dossier_sha,
                            "bytes": DOSSIER.stat().st_size},
        "preregistration_on_disk": {"path": str(PREREG), "sha256": prereg_sha,
                                    "bytes": PREREG.stat().st_size},
        "retired": retired,
        "kept": kept,
        "rule": ("an artifact is retired only when it names bytes that are not on disk; it is "
                 "copied into dated history and then removed from the live path, never deleted "
                 "outright, so the record of what was ever reviewed survives"),
    }
    if not args.dry_run:
        RECORD.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        record["record_path"] = str(RECORD)
        record["record_sha256"] = sha(RECORD)
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
