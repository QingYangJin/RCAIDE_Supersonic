"""Mechanically verify the O1 dossier -> receipt -> verdict -> GO byte binding.

The A5 reviewer is a model, not a signer: it cannot recompute SHA256 over the dossier by
hand, so it records the hash this pipeline measured and judges the protocol content. The
byte binding therefore has to be demonstrated mechanically. This script is that check. It
never writes a GO and never asserts a scientific result; it answers one question only: do
the artifacts agree on one set of bytes?

Run: python scripts/o1_verify_binding.py
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
DOSSIER = RUN / "o1_a5_dossier.md"
RECEIPT = RUN / "o1_dossier_receipt.json"
PRE = RUN / "o1_preregistration.json"
VERDICT = RUN / "a5_review/verdict.json"
GO = RUN / "o1_go_record.json"
OUT = RUN / "o1_binding_verification.json"
HISTORY = RUN / "a5_support/binding_history"
STATUS_OK = "O1_BYTES_BOUND_MECHANICALLY"
STATUS_BAD = "O1_BINDING_INCOMPLETE_OR_BROKEN"


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def code_drift(pre: dict) -> list:
    """Every frozen code file must still hash to what the preregistration froze."""
    root = Path(pre["code"]["code_root"])
    drift = []
    for name, expected in pre["code"]["code_shas"].items():
        path = Path(name)
        if not path.is_absolute():
            path = root / name
            if not path.is_file():
                path = REPO / name
        current = sha_file(path) if path.is_file() else None
        if current != expected:
            drift.append({"path": name, "expected": expected, "current": current})
    return drift


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
    pre_bytes = PRE.read_bytes()
    pre_sha = sha_bytes(pre_bytes)
    pre = json.loads(pre_bytes.decode("utf-8"))

    check("receipt_exists", True,
          "o1_dossier_receipt.json present, %d bytes" % RECEIPT.stat().st_size)
    check("receipt_dossier_sha_matches_disk",
          (receipt.get("dossier") or {}).get("sha256") == dossier_sha,
          "receipt %r vs disk %s" % ((receipt.get("dossier") or {}).get("sha256"), dossier_sha))
    check("receipt_dossier_bytes_matches_disk",
          (receipt.get("dossier") or {}).get("bytes") == len(dossier_bytes),
          "receipt %r vs disk %d" % ((receipt.get("dossier") or {}).get("bytes"),
                                     len(dossier_bytes)))
    check("receipt_preregistration_sha_matches_disk",
          (receipt.get("preregistration") or {}).get("sha256") == pre_sha,
          "receipt %r vs disk %s" % ((receipt.get("preregistration") or {}).get("sha256"),
                                     pre_sha))
    # Same digest convention as o1_build_dossier.py and o1_make_go.py: json.dumps(sort_keys=True)
    # with the default separators. All three must agree or a consistent receipt looks corrupt.
    code_sha = sha_bytes(json.dumps(pre["code"]["code_shas"], sort_keys=True).encode("utf-8"))
    check("receipt_code_shas_match_preregistration",
          receipt.get("code_shas_sha256") == code_sha,
          "receipt %r vs prereg %s" % (receipt.get("code_shas_sha256"), code_sha))

    drift = code_drift(pre)
    check("code_files_still_match_preregistration", not drift,
          "drift: %s" % drift if drift else "all %d files match" % len(pre["code"]["code_shas"]))

    # The preregistration itself must still say that nothing has been spent: an O1 GO may only
    # be signed over a dossier that describes a zero-physical state.
    check("preregistration_declares_zero_physical",
          int(pre.get("physical_solver_starts_actual") or 0) == 0,
          "preregistration physical_solver_starts_actual is %r"
          % (pre.get("physical_solver_starts_actual"),))

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

    go_state = "ABSENT"
    if GO.is_file():
        go = json.loads(GO.read_text(encoding="utf-8"))
        go_state = go.get("go_issued")
        check("go_dossier_sha_matches_disk",
              go.get("a5_dossier_sha256") == dossier_sha,
              "go %r vs disk %s" % (go.get("a5_dossier_sha256"), dossier_sha))
        check("go_preregistration_sha_matches_disk",
              go.get("preregistration_sha256") == pre_sha,
              "go %r vs disk %s" % (go.get("preregistration_sha256"), pre_sha))
        verdict_path = RUN / "o1_a5_verdict.json"
        check("go_verdict_sha_matches_disk",
              go.get("a5_verdict_sha256") == (sha_file(verdict_path)
                                              if verdict_path.is_file() else None),
              "go %r vs disk %r" % (go.get("a5_verdict_sha256"),
                                    sha_file(verdict_path) if verdict_path.is_file() else None))
    else:
        checks.append({"check": "go_record_absent_at_verification_time", "ok": True,
                       "detail": ("no GO exists yet, which is the expected ordering: this "
                                  "verifier runs first and o1_make_go.py treats its output as a "
                                  "hard precondition")})

    payload = {
        "schema": "dreal005.o1_binding_verification.v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dossier": {"path": str(DOSSIER), "sha256": dossier_sha, "bytes": len(dossier_bytes)},
        "receipt": {"path": str(RECEIPT), "sha256": sha_file(RECEIPT)},
        "preregistration": {"path": str(PRE), "sha256": pre_sha,
                            "bytes": len(pre_bytes)},
        "a5_verdict": verdict_state,
        "go_record": go_state,
        "checks": checks,
        "check_count": len(checks),
        "failure_count": len(problems),
        "problems": problems,
        "status": STATUS_OK if not problems else STATUS_BAD,
        "note": ("this verifies artifact-to-artifact byte agreement only. It is not a "
                 "scientific result, not an A5 verdict and not a GO."),
        "physical_solver_starts_actual": 0,
    }
    # The archive path is part of the record, so it is decided BEFORE the bytes are serialized:
    # o1_make_go.py refuses a verifier round whose archived_as is empty, and a round added to
    # the dict after serialization could never satisfy that gate.
    HISTORY.mkdir(parents=True, exist_ok=True)
    stamp = payload["created_utc"].replace(":", "").replace("-", "")
    archived = HISTORY / ("o1_binding_verification_%s.json" % stamp)
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
