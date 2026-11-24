"""Issue the Lead GO for the first limited O0 real batch.

Hard gates, all checked here and none bypassable by hand-editing the output:
  * the A5 verdict string must be exactly the expected PASS;
  * the verdict must bind to the current dossier bytes by SHA256;
  * the verdict must bind to the current preregistration bytes by SHA256;
  * every file in the preregistration code_shas block must still match disk.
A GO is issued by the Lead agent, not by a human and not by A5.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
PRE = RUN / "o0_preregistration.json"
DOSSIER = RUN / "o0_a5_dossier.md"
VERDICT = RUN / "a5_review/verdict.json"
RECEIPT = RUN / "o0_dossier_receipt.json"
GO = RUN / "o0_go_record.json"
EXPECTED = "H0_A0_O0_REVIEW_PASS"

sys.path.insert(0, str(RUN / "scripts"))
import o0_spend  # noqa: E402  (single authority on how spent budget is counted)


def spend_of(row: dict, name: str) -> tuple:
    """Read one abort/crash record's spend in either shape; unreadable is an error, not a zero.

    Abort records are written by hand from the raw case directory (flat *_actual keys); crash
    records are written by o0_run.py and nest the ledger summary under "ledger". A GO that read
    only one shape would understate what an authorization has already spent.
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
    raise SystemExit("UNREADABLE_SPEND_RECORD: %s carries no spend this code can read; a record "
                     "that cannot be read is not a zero bill" % name)


def carried_forward() -> dict:
    """What earlier batches under this authorization already spent, counted once.

    A GO must never claim that nothing has been spent, and it must not bill an authorization
    twice either: an abort record is batch-local while a crash record is
    authorization-cumulative, so adding both would report 24 starts for the 23 actually spent.
    scripts/o0_spend.py owns that rule; this function reports it instead of re-deriving it.
    """
    spend = o0_spend.authorization_spend(RUN)
    return {"design_attempts": spend["design_attempts"],
            "solver_starts": spend["solver_starts"],
            "internal_solver_cases": spend["internal_solver_cases"],
            "records": [{"record": r["name"], "sha256": r["sha256"], "basis": r["basis"],
                         "charged_starts": r["starts"],
                         "internal_solver_cases": r["internal"],
                         "design_evaluations": r["designs"]} for r in spend["records"]],
            "counting_rule": spend["rule"], "basis_record": spend["basis_record"]}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def main() -> int:
    pre_bytes = PRE.read_bytes()
    pre = json.loads(pre_bytes.decode("utf-8"))
    dossier_sha = sha_file(DOSSIER)
    v = json.loads(VERDICT.read_text(encoding="utf-8"))
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8")) if RECEIPT.is_file() else {}

    problems = []
    # Three-way byte binding: disk == external receipt == reviewer measurement.
    receipt_sha = (receipt.get("dossier") or {}).get("sha256")
    if not receipt:
        problems.append("o0_dossier_receipt.json is missing; the dossier bytes are not "
                        "bound by an external record")
    elif receipt_sha != dossier_sha:
        problems.append("dossier receipt binding is %r, current dossier is %s"
                        % (receipt_sha, dossier_sha))
    elif v.get("dossier_sha256") != receipt_sha:
        problems.append("reviewer dossier hash %r disagrees with the external receipt %r"
                        % (v.get("dossier_sha256"), receipt_sha))
    # Hard precondition: a fresh mechanical verifier round over THESE bytes. The reviewer
    # measures what it can, but the GO must not rest on a verifier round that read an earlier
    # version of the dossier, and it must not rest on the reviewer's arithmetic either.
    ver_path = RUN / "o0_binding_verification.json"
    verifier_state = {}
    if not ver_path.is_file():
        problems.append("no o0_binding_verification.json exists; the byte binding has never been "
                        "mechanically verified, so the GO would authorize starts on unverified bytes")
    else:
        ver = json.loads(ver_path.read_text(encoding="utf-8"))
        verifier_state = {
            "path": str(ver_path), "sha256": sha_file(ver_path),
            "status": ver.get("status"), "check_count": ver.get("check_count"),
            "failure_count": ver.get("failure_count"),
            "dossier_sha256": (ver.get("dossier") or {}).get("sha256"),
            "dossier_bytes": (ver.get("dossier") or {}).get("bytes"),
            "created_utc": ver.get("created_utc"),
            "archived_as": ver.get("archived_as"),
        }
        if ver.get("status") != "O0_BYTES_BOUND_MECHANICALLY":
            problems.append("broad verifier status is %r, not O0_BYTES_BOUND_MECHANICALLY"
                            % ver.get("status"))
        if int(ver.get("failure_count") or 0) != 0:
            problems.append("broad verifier reported %r failures: %r"
                            % (ver.get("failure_count"), ver.get("problems")))
        if (ver.get("dossier") or {}).get("sha256") != dossier_sha:
            problems.append("the verifier round read dossier %r but the dossier on disk is %s; "
                            "the verification is stale and must be re-run"
                            % ((ver.get("dossier") or {}).get("sha256"), dossier_sha))
        if int((ver.get("dossier") or {}).get("bytes") or -1) != len(DOSSIER.read_bytes()):
            problems.append("the verifier recorded %r dossier bytes but the file has %d"
                            % ((ver.get("dossier") or {}).get("bytes"),
                               len(DOSSIER.read_bytes())))
        created = str(ver.get("created_utc") or "")
        written = datetime.fromtimestamp(DOSSIER.stat().st_mtime, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        if created < written:
            problems.append("the verifier round (%s) predates the dossier bytes (%s); re-run "
                            "scripts/o0_verify_binding.py after the dossier is final"
                            % (created, written))
        if not ver.get("archived_as"):
            problems.append("the verifier round was not archived under a5_support/binding_history/, "
                            "so its own bytes cannot be re-checked later")
    if v.get("verdict") != EXPECTED:
        problems.append("a5 verdict is %r, expected %r" % (v.get("verdict"), EXPECTED))
    if v.get("dossier_sha256") != dossier_sha:
        problems.append("a5 dossier binding is %r, current dossier is %s"
                        % (v.get("dossier_sha256"), dossier_sha))
    if v.get("preregistration_sha256") != sha_bytes(pre_bytes):
        problems.append("a5 preregistration binding is %r, current preregistration is %s"
                        % (v.get("preregistration_sha256"), sha_bytes(pre_bytes)))
    prior = carried_forward()
    caps = pre["caps"]
    # The per-design caps bind first, so the spendable totals are design-derived, not the
    # stored solver ceilings. 12 designs x 2 starts = 24 and 12 designs x 20 internal = 240;
    # the stored 36-start ceiling is unreachable. Writing 35 here (36 minus the paid start)
    # would contradict the dossier and authorize budget no batch can ever spend.
    design_attempts = int(caps["max_design_attempts"])
    per_design_starts = int(caps["max_starts_per_design"])
    per_design_internal = int(caps["max_internal_per_design"])
    spendable = {
        "design_attempts": design_attempts,
        "solver_starts": min(int(caps["max_solver_starts"]), design_attempts * per_design_starts),
        "internal_solver_cases": min(int(caps["max_internal_cases"]),
                                     design_attempts * per_design_internal),
        "derivation": ("min(stored_cap, max_design_attempts x per_design_cost); the design cap "
                       "binds first, so the stored solver-start ceiling is inert"),
    }
    authorized = {
        "design_attempts": spendable["design_attempts"] - prior["design_attempts"],
        "solver_starts": spendable["solver_starts"] - prior["solver_starts"],
        "internal_solver_cases": (spendable["internal_solver_cases"]
                                  - prior["internal_solver_cases"]),
    }
    if min(authorized.values()) < 0:
        problems.append("carried-forward spend %r already exceeds the spendable ceiling %r"
                        % (prior, spendable))
    code_state = {}
    for rel, row in pre["code_shas"].items():
        path = REPO / rel if not Path(rel).is_absolute() else Path(rel)
        if not path.is_file():
            path = RUN / rel
        current = sha_file(path) if path.is_file() else None
        code_state[rel] = {"expected": row["sha256"], "current": current,
                           "match": current == row["sha256"]}
        if current != row["sha256"]:
            problems.append("code sha drift: %s expected %s got %s"
                            % (rel, row["sha256"], current))
    if problems:
        report = {"go_issued": False, "problems": problems, "code_state": code_state}
        (RUN / "o0_go_blocked.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    go = {
        "schema": "dreal005.o0_go_record.v1",
        "go_issued": True,
        "go_issued_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issued_by": "Lead (agent), not a human approver and not the A5 reviewer",
        "owner_authorization_ref": "Issue #15 (2026-11-24) body plus first comment; Owner instruction m11649",
        "issue": 15,
        "run_id": pre["run_id"],
        "batch_id": pre["batch_id"],
        "authorization_id": pre["authorization_id"],
        "preregistration_path": str(PRE),
        "preregistration_sha256": sha_bytes(pre_bytes),
        "a5_dossier_path": str(DOSSIER),
        "a5_dossier_sha256": dossier_sha,
        "a5_dossier_receipt_path": str(RECEIPT),
        "a5_dossier_receipt_sha256": sha_file(RECEIPT),
        "byte_binding": ("three independent values agree: sha256(dossier on disk), "
                         "o0_dossier_receipt.dossier.sha256, verdict.dossier_sha256"),
        "a5_verdict_path": str(VERDICT),
        "a5_verdict_sha256": sha_file(VERDICT),
        "a5_verdict": v["verdict"],
        "a5_reviewer": v.get("reviewer"),
        "byte_verifier": verifier_state,
        "byte_verifier_is_a_hard_precondition": (
            "this GO was refused unless o0_binding_verification.json reported "
            "O0_BYTES_BOUND_MECHANICALLY with zero failures over exactly these dossier bytes, "
            "written after the dossier, and archived where it cannot be overwritten"),
        "a5_human_signature": False,
        "code_shas": {rel: row["sha256"] for rel, row in pre["code_shas"].items()},
        "caps": pre["caps"],
        "spendable_under_this_authorization": spendable,
        "carried_forward": prior,
        "authorized_remaining": authorized,
        "physical_starts_authorized_this_go": authorized["solver_starts"],
        "physical_starts_used_before_this_go": prior["solver_starts"],
        "internal_cases_authorized": authorized["internal_solver_cases"],
        "internal_cases_used_before_this_go": prior["internal_solver_cases"],
        "design_attempts_authorized": authorized["design_attempts"],
        "caps_are_for_the_authorization_not_the_batch": (
            "the caps in the pre-registration bind the authorization id; starts and internal "
            "cases consumed by an earlier aborted batch are carried forward, so the amounts "
            "authorized here are the remainder, not the full cap"),
        "not_authorized": pre["not_authorized"],
        "conditions": [
            "upload and remote readback after every 8 starts or 60 minutes before continuing",
            "abort the batch if the baseline design fails to yield an admitted real row",
            "no retry of an interrupted start; an interrupted start stays charged",
            "lift tolerance 1e-3 is never relaxed and no interpolated row may be admitted",
            "O1 warm-start arms require a separate preregistration, A5 review and GO",
        ],
    }
    GO.write_text(json.dumps(go, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8", newline="\n")
    print(json.dumps({"go_issued": True, "go_record": str(GO),
                      "go_sha256": sha_file(GO), "a5_verdict": v["verdict"],
                      "a5_reviewer": v.get("reviewer")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
