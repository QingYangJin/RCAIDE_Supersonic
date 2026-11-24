"""Build the machine-readable record of every O1 result-level review round.  

Why this file exists and why the dossier does not narrate rounds
---------------------------------------------------------------
A dossier is supposed to describe artefacts, not to tell the story of how it was edited.  When a
narrative of previous review rounds sits inside the dossier, every claim in it becomes a claim
that has to be corroborated by a file -- and if one of those rounds left no file, the dossier is
suddenly asserting something no reader can check.  So the round history lives here instead:
generated from what is actually on disk (a5_result_review/rounds/ and a5_result_review/history/),
with the rounds that left no file listed separately and marked as uncorroborated.

It also records the governance defect that caused the gap: the first version of the review harness
wrote verdict.json in place, so each round silently deleted the previous round's verdict.  The
harness now writes a dated copy into rounds/ before replacing the live verdict.

Run: python scripts/o1_result_rounds.py
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
REVIEW = RUN / "a5_result_review"
ROUNDS = REVIEW / "rounds"
HISTORY = REVIEW / "history"
OUT = RUN / "o1_result_review_rounds.json"
SCHEMA = "dreal005.o1_result_review_rounds.v1"

# Rounds that really happened but whose verdict file no longer exists, because the harness wrote
# verdict.json in place.  The entries are transcriptions of the generator stdout, and are marked
# as such: they are disclosed, not evidenced.
LOST_ROUNDS = [
    {
        "round": 2,
        "verdict": "O1_RESULT_REVIEW_CHANGES_REQUIRED",
        "dossier_it_bound": "ad65e57f38d1e3148890714231b4684025596e9e68f8635e139984946d66b08b",
        "corroboration": "NONE_ON_DISK",
        "what_it_said": (
            "three substantive findings: (critical) this result dossier's hash differs from the hash bound "
            "by the protocol verdict, suspected byte drift; (major) section 7 claims every case directory "
            "carries admission_certificate.json but the 18 coarse directories do not; (major) o1_result.json's "
            "cost.note says the 108 equivalent bill is three times the support block, while 108 = 3 x 36 is the "
            "whole bill tripled"),
        "why_there_is_no_file": (
            "the harness at that time wrote a5_result_review/verdict.json in place, so the next round overwrote "
            "it; the per-round copy into rounds/ was added afterwards.  The only surviving trace is the generator "
            "stdout, which is no longer retrievable either."),
        "how_a_reader_should_weight_it": (
            "as a disclosure, not as evidence: it is listed here so that nobody can accuse the record of "
            "pretending the round never happened, and it is marked NONE_ON_DISK so that nobody can mistake it "
            "for something they can verify"),
    },
]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def describe(path: Path, where: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "where": where,
        "file": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha(path),
        "verdict": payload.get("verdict"),
        "reviewed_utc": payload.get("reviewed_utc"),
        "dossier_sha256": payload.get("dossier_sha256"),
        "tool_hops": payload.get("tool_hops"),
        "gate_verdicts": payload.get("gate_verdicts"),
        "findings_by_severity": _count(payload.get("findings") or []),
    }


def _count(findings) -> dict:
    out = {}
    for f in findings:
        k = f.get("severity", "?")
        out[k] = out.get(k, 0) + 1
    return out


def main() -> int:
    on_disk = []
    if ROUNDS.is_dir():
        for p in sorted(ROUNDS.glob("verdict_*.json")):
            on_disk.append(describe(p, "a5_result_review/rounds"))
    if HISTORY.is_dir():
        for p in sorted(HISTORY.glob("*.json")):
            try:
                on_disk.append(describe(p, "a5_result_review/history"))
            except Exception:  # noqa: BLE001
                continue
    live = REVIEW / "verdict.json"
    record = {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "live_verdict": describe(live, "a5_result_review") if live.is_file() else None,
        "rounds_with_a_surviving_file": on_disk,
        "rounds_with_no_surviving_file": LOST_ROUNDS,
        "rule": (
            "a result-level verdict speaks only for the dossier bytes it names; every round is kept as its own "
            "dated file, and a round that left no file is listed as uncorroborated rather than omitted"),
        "governance_defect_found_and_fixed": {
            "defect": ("the first version of scripts/o1_a5_result_review.py wrote a5_result_review/verdict.json "
                       "in place, so each round destroyed the previous round's verdict file"),
            "fixed_by": ("the harness now writes a5_result_review/rounds/verdict_<stamp>_<dossier16>.json and "
                         "a dated raw_lines_<stamp>.txt before replacing the live verdict"),
            "residual": ("one round is already lost; it is disclosed above as NONE_ON_DISK and is not counted "
                         "as evidence anywhere in this run"),
        },
    }
    OUT.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"out": str(OUT), "bytes": OUT.stat().st_size, "sha256": sha(OUT),
                      "on_disk_rounds": len(on_disk), "lost_rounds": len(LOST_ROUNDS)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
