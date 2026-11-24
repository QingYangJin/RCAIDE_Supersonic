"""Mechanically verify the O0 dossier -> receipt -> verdict -> GO byte binding.

The A5 reviewer is a single-shot model with no tools: it cannot recompute SHA256 over a
14 KB document, so it can only record the hash that this pipeline measured for it and judge
the protocol content. That means the byte binding must be demonstrated by a mechanical
check, not by the reviewer's claim. This script is that check. It never writes a GO and it
never asserts a scientific result; it only answers one question: do the four artifacts
agree on one set of bytes?
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
DOSSIER = RUN / "o0_a5_dossier.md"
RECEIPT = RUN / "o0_dossier_receipt.json"
PRE = RUN / "o0_preregistration.json"
VERDICT = RUN / "a5_review/verdict.json"
GO = RUN / "o0_go_record.json"
OUT = RUN / "o0_binding_verification.json"
HISTORY = RUN / "a5_support/binding_history"


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def main() -> int:
    checks = []
    problems = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            problems.append("%s: %s" % (name, detail))

    dossier_bytes = DOSSIER.read_bytes()
    dossier_sha = sha_bytes(dossier_bytes)
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    pre_sha = sha_file(PRE)
    pre = json.loads(PRE.read_text(encoding="utf-8"))

    check("receipt_exists", True, "o0_dossier_receipt.json present, %d bytes"
          % RECEIPT.stat().st_size)
    check("receipt_dossier_sha_matches_disk",
          (receipt.get("dossier") or {}).get("sha256") == dossier_sha,
          "receipt %r vs disk %s" % ((receipt.get("dossier") or {}).get("sha256"),
                                     dossier_sha))
    check("receipt_dossier_bytes_matches_disk",
          (receipt.get("dossier") or {}).get("bytes") == len(dossier_bytes),
          "receipt %r vs disk %d" % ((receipt.get("dossier") or {}).get("bytes"),
                                     len(dossier_bytes)))
    check("receipt_preregistration_sha_matches_disk",
          (receipt.get("preregistration") or {}).get("sha256") == pre_sha,
          "receipt %r vs disk %s" % ((receipt.get("preregistration") or {}).get("sha256"),
                                     pre_sha))
    code_sha = sha_bytes(json.dumps(pre["code_shas"], sort_keys=True).encode("utf-8"))
    check("receipt_code_shas_match_preregistration",
          receipt.get("code_shas_sha256") == code_sha,
          "receipt %r vs prereg %s" % (receipt.get("code_shas_sha256"), code_sha))

    drift = []
    for rel, row in pre["code_shas"].items():
        path = Path(rel)
        if not path.is_absolute():
            path = REPO / rel
            if not path.is_file():
                path = RUN / rel
        current = sha_file(path) if path.is_file() else None
        if current != row["sha256"]:
            drift.append({"path": rel, "expected": row["sha256"], "current": current})
    check("code_files_still_match_preregistration", not drift,
          "drift: %s" % drift if drift else "all %d files match" % len(pre["code_shas"]))

    verdict_state = "ABSENT"
    if VERDICT.is_file():
        verdict = json.loads(VERDICT.read_text(encoding="utf-8"))
        verdict_state = verdict.get("verdict")
        check("verdict_dossier_sha_matches_disk",
              verdict.get("dossier_sha256") == dossier_sha,
              "verdict %r vs disk %s" % (verdict.get("dossier_sha256"), dossier_sha))
        check("verdict_preregistration_sha_matches_disk",
              verdict.get("preregistration_sha256") == pre_sha,
              "verdict %r vs disk %s" % (verdict.get("preregistration_sha256"), pre_sha))
        check("verdict_dossier_sha_matches_receipt",
              verdict.get("dossier_sha256") == (receipt.get("dossier") or {}).get("sha256"),
              "verdict vs receipt")
    else:
        check("verdict_present", False, "%s does not exist yet" % VERDICT)

    # The GO is written after this file, so its checks are reported here but they are also
    # enforced by o0_make_go.py itself (this script's output is a hard precondition there).
    go_state = "ABSENT"
    if GO.is_file():
        go = json.loads(GO.read_text(encoding="utf-8"))
        go_state = go.get("go_issued")
        check("go_dossier_sha_matches_disk",
              go.get("a5_dossier_sha256") == dossier_sha,
              "go %r vs disk %s" % (go.get("a5_dossier_sha256"), dossier_sha))
        check("go_receipt_sha_matches_disk",
              go.get("a5_dossier_receipt_sha256") in (None, sha_file(RECEIPT)),
              "go receipt hash vs disk %s" % sha_file(RECEIPT))
    else:
        checks.append({"name": "go_record_absent_at_verification_time", "ok": True,
                       "detail": ("no GO exists yet, which is the expected ordering: this "
                                  "verifier runs first and o0_make_go.py treats its output as a "
                                  "precondition")})

    payload = {
        "schema": "dreal005.o0_binding_verification.v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dossier": {"path": str(DOSSIER), "sha256": dossier_sha, "bytes": len(dossier_bytes)},
        "receipt": {"path": str(RECEIPT), "sha256": sha_file(RECEIPT)},
        "preregistration": {"path": str(PRE), "sha256": pre_sha},
        "a5_verdict": verdict_state,
        "go_record": go_state,
        "checks": checks,
        "check_count": len(checks),
        "failure_count": len(problems),
        "problems": problems,
        "status": ("O0_BYTES_BOUND_MECHANICALLY" if not problems
                   else "O0_BINDING_INCOMPLETE_OR_BROKEN"),
        "note": ("this verifies artifact-to-artifact byte agreement only. It is not a "
                 "scientific result, not an A5 verdict and not a GO."),
        "physical_solver_starts_actual": 0,
    }
    # Keep every round: the A5 dossier quotes an archived round as its byte-binding anchor,
    # so an artifact that this script overwrites could not serve as that anchor. The archive
    # path is part of the record, so it is decided BEFORE the bytes are serialized; an earlier
    # version added it to the in-memory dict after writing, which made the archived_as gate in
    # o0_make_go.py unsatisfiable no matter how many clean rounds ran.
    HISTORY.mkdir(parents=True, exist_ok=True)
    stamp = payload["created_utc"].replace(":", "").replace("-", "")
    archived = HISTORY / ("o0_binding_verification_%s.json" % stamp)
    payload["archived_as"] = str(archived)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    OUT.write_text(text, encoding="utf-8", newline="\n")
    archived.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "checks": len(checks),
                      "failures": problems, "out": str(OUT),
                      "sha256": sha_file(OUT)}, ensure_ascii=False, indent=2))
    return 0 if not problems else 2


if __name__ == "__main__":
    raise SystemExit(main())
