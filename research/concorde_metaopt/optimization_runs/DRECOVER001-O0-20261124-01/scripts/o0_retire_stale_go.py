"""Retire a GO record that no longer binds the current dossier bytes.

A GO is a statement about specific bytes. When the dossier or the frozen code changes,
the earlier GO does not become "wrong history", it becomes a GO about other bytes, and
leaving it at o0_go_record.json would let a reader (or a script) mistake it for authority
over the current tree. It is moved into go_history/ with the reason recorded, so the
history stays and the working path is empty of a claim that is no longer true.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
GO = RUN / "o0_go_record.json"
DOSSIER = RUN / "o0_a5_dossier.md"
HISTORY = RUN / "go_history"


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    if not GO.is_file():
        print(json.dumps({"retired": None, "reason": "no GO record at the working path"}))
        return 0
    go = json.loads(GO.read_text(encoding="utf-8"))
    current = sha_file(DOSSIER)
    bound = go.get("a5_dossier_sha256")
    if bound == current:
        print(json.dumps({"retired": None,
                          "reason": "the GO already binds the current dossier bytes"}))
        return 0
    HISTORY.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = HISTORY / ("o0_go_record_SUPERSEDED_%s_%s.json" % (stamp, (bound or "none")[:8]))
    record = {
        "schema": "dreal005.o0_go_record.superseded.v1",
        "retired_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "original_sha256": sha_file(GO),
        "bound_dossier_sha256": bound,
        "current_dossier_sha256": current,
        "reason": ("the dossier (and the frozen code it lists) changed after this GO was "
                   "issued, so the GO no longer states anything about the current bytes; "
                   "keeping it at the working path would present an expired authorization "
                   "as a live one"),
        "superseded_by": "the next GO issued by scripts/o0_make_go.py",
        "go": go,
    }
    dest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")
    GO.unlink()
    print(json.dumps({"retired": str(dest), "old_bound_dossier": bound,
                      "current_dossier": current,
                      "old_go_sha256": record["original_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
