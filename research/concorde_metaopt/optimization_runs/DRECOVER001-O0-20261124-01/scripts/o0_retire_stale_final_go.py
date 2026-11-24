"""Retire the O0-FINAL GO that no longer binds the current dossier bytes, and archive the
artefacts of the crashed first verification attempt.

A GO is a statement about specific bytes. The final GO was issued for the dossier that
allowed six verification starts; the dossier now on disk allows eight, describes the crash
and carries the repaired ledger. The old GO is therefore not wrong history, it is a GO
about other bytes, and leaving it at o0_final_go_record.json would let a reader or a
script mistake an expired authorization for a live one. It is moved into go_history/ with
the reason recorded, and the plan / rounds / logs of the crashed attempt are moved into
o0_final/history/ so that the next run cannot overwrite the only record of what the crash
produced. Nothing is deleted.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
GO = RUN / "o0_final_go_record.json"
DOSSIER = RUN / "o0_a5_dossier.md"
PRE = RUN / "o0_preregistration.json"
HISTORY = RUN / "go_history"
OUT = RUN / "o0_final"
ATTEMPT_HISTORY = OUT / "history"


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    out = {"retired": None, "archived_attempt_artefacts": [], "moved_nothing": []}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if GO.is_file():
        go = json.loads(GO.read_text(encoding="utf-8"))
        current = sha_file(DOSSIER)
        bound = go.get("a5_dossier_sha256")
        if bound == current:
            out["moved_nothing"].append("the final GO already binds the current dossier bytes")
        else:
            HISTORY.mkdir(parents=True, exist_ok=True)
            dest = HISTORY / ("o0_final_go_record_SUPERSEDED_%s_%s.json" % (stamp, (bound or "none")[:8]))
            record = {
                "schema": "dreal005.o0_final_go_record.superseded.v1",
                "retired_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "original_sha256": sha_file(GO),
                "bound_dossier_sha256": bound,
                "bound_preregistration_sha256": go.get("preregistration_sha256"),
                "current_dossier_sha256": current,
                "current_preregistration_sha256": sha_file(PRE) if PRE.is_file() else None,
                "reason": ("the dossier and the pre-registration changed after this GO was issued "
                           "(the crashed first verification attempt is now disclosed and the "
                           "verification budget is gross 8 starts / 104 internal cases), so this "
                           "record no longer states anything about the current bytes; keeping it "
                           "at the working path would present an expired authorization as live"),
                "superseded_by": "the next GO issued by scripts/o0_make_final_go.py",
                "go": go,
            }
            dest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
            GO.unlink()
            out["retired"] = {"path": str(dest), "old_bound_dossier": bound,
                              "current_dossier": current,
                              "old_go_sha256": record["original_sha256"]}
    else:
        out["moved_nothing"].append("no final GO record at the working path")
    attempt_dir = ATTEMPT_HISTORY / ("first_verification_attempt_%s" % stamp)
    for name in ("o0_final_plan.json", "o0_final_rounds.json",
                 "o0_final_run.log", "o0_final_preflight.log"):
        src = OUT / name if (OUT / name).is_file() else RUN / name
        if not src.is_file():
            continue
        want = sha_file(src)
        already = None
        if ATTEMPT_HISTORY.is_dir():
            for other in sorted(ATTEMPT_HISTORY.iterdir()):
                cand = other / name
                if cand.is_file() and sha_file(cand) == want:
                    already = cand
                    break
        if already is not None:
            dest = already
        else:
            attempt_dir.mkdir(parents=True, exist_ok=True)
            dest = attempt_dir / name
            shutil.copy2(src, dest)
            out["archived_attempt_artefacts"].append(
                {"name": name, "from": str(src), "to": str(dest), "sha256": sha_file(dest),
                 "bytes": dest.stat().st_size})
        # The archived copy is byte-identical, so leaving the original at the live path would keep
        # a stale artefact where a reader expects the current run's file. The crashed attempt's
        # rounds file in particular still carries the two mislabelled kind=wake rows: that is
        # history, and history belongs in history/ and not next to the live ledger.
        if src.parent != ATTEMPT_HISTORY and src.is_file() and sha_file(src) == sha_file(dest):
            src.unlink()
            out.setdefault("removed_from_the_live_path", []).append(
                {"name": name, "removed": str(src), "kept_at": str(dest),
                 "why": ("the crashed attempt's artefact is byte-identical at the archived copy; "
                         "keeping it at the working path would present stale, mislabelled rows "
                         "next to the repaired ledger")})
    if attempt_dir.is_dir():
        (attempt_dir / "README.md").write_text(
            "# The crashed first O0-FINAL verification attempt\n\n"
            "These are the plan, the rounds file and the logs of the run that died with\n"
            "a wake probe cap error on 2026-11-24. The three solver starts it spent\n"
            "are charged in ../verification_ledger.json as two void rows and one wake row, with\n"
            "the sha256 of the polar and case_result.json that back each of them. The files are\n"
            "kept here so that the repaired run cannot overwrite the only record of what the\n"
            "crash produced. Nothing in this directory is evidence of a verified improvement.\n",
            encoding="utf-8", newline="\n")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
