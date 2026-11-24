"""Retire the O1 *result-level* verdict when it binds dossier bytes that are no longer on disk.

Same rule as scripts/o1_retire_stale.py (which covers the protocol-level artifacts), applied to
the result-level review: a PASS only speaks for the exact bytes that were reviewed. When the
result dossier is edited after the review, the old verdict is copied into dated history and then
removed from the live path, so exactly one live verdict names the bytes a reader can see.

It never deletes: the copy is taken first and its sha256 is verified against the original before
the live path is unlinked. Fail-closed on anything it cannot read.

Run: python scripts/o1_result_retire_stale.py [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
DOSSIER = RUN / "o1_a5_result_dossier.md"
LIVE = RUN / "a5_result_review" / "verdict.json"
COPY = RUN / "o1_a5_result_verdict.json"
HISTORY = RUN / "a5_result_review" / "history"
RECORD = RUN / "o1_result_retire_record.json"
SCHEMA = "dreal005.o1_result_retire_record.v1"


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


def retire(path: Path, reason: str, dry_run: bool) -> dict:
    payload = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha(path),
        "reason": reason,
        "archived_as": None,
        "removed_from_the_live_path": False,
    }
    if dry_run:
        return payload
    HISTORY.mkdir(parents=True, exist_ok=True)
    target = HISTORY / ("verdict_%s_%s.json" % (stamp(), payload["sha256"][:16]))
    shutil.copy2(path, target)
    if sha(target) != payload["sha256"]:
        raise SystemExit("copy of %s does not match the original; nothing removed" % (path,))
    payload["archived_as"] = str(target)
    path.unlink()
    payload["removed_from_the_live_path"] = True
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Retire the O1 result verdict for superseded dossier bytes")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not DOSSIER.is_file():
        raise SystemExit("result dossier missing; nothing to compare against")
    dossier_sha = sha(DOSSIER)

    retired = []
    kept = []
    for path in (LIVE, COPY):
        payload = load(path)
        if payload is None:
            continue
        if "__unreadable__" in payload:
            retired.append(retire(path, "unreadable verdict cannot be trusted", args.dry_run))
            continue
        names = payload.get("dossier_sha256")
        if names == dossier_sha:
            kept.append({"path": str(path), "why": "binds the result dossier on disk"})
            continue
        retired.append(retire(path, "verdict binds dossier %r, disk is %r" % (names, dossier_sha),
                              args.dry_run))

    record = {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": bool(args.dry_run),
        "dossier_on_disk": {"path": str(DOSSIER), "sha256": dossier_sha,
                            "bytes": DOSSIER.stat().st_size},
        "retired": retired,
        "kept": kept,
        "rule": ("a result-level PASS speaks only for the dossier bytes it reviewed; a verdict over "
                 "superseded bytes is copied into dated history and then removed from the live path, "
                 "never deleted outright"),
    }
    if not args.dry_run:
        RECORD.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        record["record_path"] = str(RECORD)
        record["record_sha256"] = sha(RECORD)
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
