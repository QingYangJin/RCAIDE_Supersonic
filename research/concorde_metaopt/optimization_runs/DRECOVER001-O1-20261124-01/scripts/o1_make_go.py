"""Issue the Lead GO for the single O1 three-arm pairing.

Hard gates, none of them bypassable by hand-editing the output:
  * the A5 verdict string must be exactly O1_THREE_ARM_REVIEW_PASS;
  * the verdict must bind the current dossier and preregistration bytes by SHA256;
  * a fresh mechanical verifier round over THESE dossier bytes must report
    O1_BYTES_BOUND_MECHANICALLY with zero failures, written after the dossier, archived;
  * every frozen code file in the preregistration must still match disk;
  * the preregistration must declare zero physical starts already spent.
A GO is issued by the Lead agent: not a human, not the A5 reviewer, and not a science claim.

Run: python scripts/o1_make_go.py
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
PRE = RUN / "o1_preregistration.json"
DOSSIER = RUN / "o1_a5_dossier.md"
RECEIPT = RUN / "o1_dossier_receipt.json"
VERDICT = RUN / "a5_review/verdict.json"
VERDICT_COPY = RUN / "o1_a5_verdict.json"
VERIFY = RUN / "o1_binding_verification.json"
GO = RUN / "o1_go_record.json"
BLOCKED = RUN / "o1_go_blocked.json"
EXPECTED = "O1_THREE_ARM_REVIEW_PASS"


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def canon(payload) -> str:
    return sha_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False).encode("utf-8"))


def code_shas_digest(code_shas: dict) -> str:
    """The digest convention o1_build_dossier.py writes into the receipt.

    It is json.dumps(sort_keys=True) with the DEFAULT separators, not the compact canonical
    form used elsewhere. The two conventions differ by every space after a comma, so a GO that
    hashed the block the other way would refuse a perfectly consistent receipt forever; the
    builder and the two checkers must therefore agree on one convention, and this is it.
    """
    return sha_bytes(json.dumps(code_shas, sort_keys=True).encode("utf-8"))


def code_state(pre: dict) -> dict:
    root = Path(pre["code"]["code_root"])
    state = {}
    for name, expected in pre["code"]["code_shas"].items():
        path = Path(name)
        if not path.is_absolute():
            path = root / name
            if not path.is_file():
                path = REPO / name
        current = sha_file(path) if path.is_file() else None
        state[name] = {"expected": expected, "current": current, "match": current == expected}
    return state


def prior_spend() -> dict:
    """What O1 itself has already spent. Zero until a real O1 batch runs."""
    spend = {"designs": 0, "starts": 0, "internal": 0, "records": []}
    for path in sorted(RUN.glob("o1_batch_close*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cost = payload.get("cost") or {}
        spend["starts"] += int(cost.get("physical_solver_starts_actual") or 0)
        spend["records"].append({"record": path.name, "sha256": sha_file(path),
                                 "starts": cost.get("physical_solver_starts_actual")})
    for path in sorted(RUN.glob("o1_crash*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cost = payload.get("cost") or {}
        spend["starts"] += int(cost.get("physical_solver_starts_actual") or 0)
        spend["records"].append({"record": path.name, "sha256": sha_file(path),
                                 "starts": cost.get("physical_solver_starts_actual")})
    return spend


def main() -> int:
    problems = []
    pre_bytes = PRE.read_bytes()
    pre = json.loads(pre_bytes.decode("utf-8"))
    dossier_bytes = DOSSIER.read_bytes()
    dossier_sha = sha_bytes(dossier_bytes)
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8")) if RECEIPT.is_file() else {}
    verdict = json.loads(VERDICT.read_text(encoding="utf-8")) if VERDICT.is_file() else {}

    if not receipt:
        problems.append("o1_dossier_receipt.json is missing; the dossier bytes are not bound "
                        "by an external record")
    else:
        receipt_sha = (receipt.get("dossier") or {}).get("sha256")
        if receipt_sha != dossier_sha:
            problems.append("dossier receipt binding is %r, current dossier is %s"
                            % (receipt_sha, dossier_sha))
        if (receipt.get("dossier") or {}).get("bytes") != len(dossier_bytes):
            problems.append("dossier receipt records %r bytes, the file has %d"
                            % ((receipt.get("dossier") or {}).get("bytes"), len(dossier_bytes)))
        if (receipt.get("preregistration") or {}).get("sha256") != sha_bytes(pre_bytes):
            problems.append("dossier receipt binds a different preregistration than the disk")
        if receipt.get("code_shas_sha256") != code_shas_digest(pre["code"]["code_shas"]):
            problems.append("dossier receipt froze a different code_shas block")

    if not verdict:
        problems.append("no a5_review/verdict.json exists; nothing has been independently reviewed")
    else:
        if verdict.get("verdict") != EXPECTED:
            problems.append("A5 verdict is %r, expected %r" % (verdict.get("verdict"), EXPECTED))
        if verdict.get("dossier_sha256") != dossier_sha:
            problems.append("A5 verdict binds dossier %r, current is %s"
                            % (verdict.get("dossier_sha256"), dossier_sha))
        if verdict.get("preregistration_sha256") != sha_bytes(pre_bytes):
            problems.append("A5 verdict binds a different preregistration than the disk")

    verifier_state = {}
    if not VERIFY.is_file():
        problems.append("no o1_binding_verification.json exists; the byte binding has never been "
                        "mechanically verified, so this GO would authorise starts on unverified "
                        "bytes")
    else:
        ver = json.loads(VERIFY.read_text(encoding="utf-8"))
        verifier_state = {
            "path": str(VERIFY), "sha256": sha_file(VERIFY),
            "status": ver.get("status"), "check_count": ver.get("check_count"),
            "failure_count": ver.get("failure_count"),
            "dossier_sha256": (ver.get("dossier") or {}).get("sha256"),
            "dossier_bytes": (ver.get("dossier") or {}).get("bytes"),
            "created_utc": ver.get("created_utc"), "archived_as": ver.get("archived_as"),
        }
        if ver.get("status") != "O1_BYTES_BOUND_MECHANICALLY":
            problems.append("binding verifier status is %r, not O1_BYTES_BOUND_MECHANICALLY"
                            % (ver.get("status"),))
        if int(ver.get("failure_count") or 0) != 0:
            problems.append("binding verifier reported %r failures: %r"
                            % (ver.get("failure_count"), ver.get("problems")))
        if (ver.get("dossier") or {}).get("sha256") != dossier_sha:
            problems.append("the verifier round read dossier %r but the disk has %s; the "
                            "verification is stale and must be re-run"
                            % ((ver.get("dossier") or {}).get("sha256"), dossier_sha))
        if int((ver.get("dossier") or {}).get("bytes") or -1) != len(dossier_bytes):
            problems.append("the verifier recorded %r dossier bytes, the file has %d"
                            % ((ver.get("dossier") or {}).get("bytes"), len(dossier_bytes)))
        created = str(ver.get("created_utc") or "")
        written = datetime.fromtimestamp(DOSSIER.stat().st_mtime, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        if created < written:
            problems.append("the verifier round (%s) predates the dossier bytes (%s); re-run "
                            "scripts/o1_verify_binding.py after the dossier is final"
                            % (created, written))
        if not ver.get("archived_as"):
            problems.append("the verifier round was not archived under a5_support/binding_history/, "
                            "so its own bytes cannot be re-checked later")

    if int(pre.get("physical_solver_starts_actual") or 0) != 0:
        problems.append("the preregistration declares %r physical starts already spent; a GO for "
                        "this pairing must be signed over a zero-physical dossier"
                        % (pre.get("physical_solver_starts_actual"),))

    state = code_state(pre)
    for name, row in state.items():
        if not row["match"]:
            problems.append("code sha drift: %s expected %s got %s"
                            % (name, row["expected"], row["current"]))

    caps = pre["budgets"]["caps"]
    cost = pre["budgets"]["cost_model"]
    design_cap = int(caps["max_designs_per_arm"])
    starts_cap = int(caps["max_starts_per_arm"])
    internal_cap = int(caps["max_internal_per_arm"])
    affordable = int(cost["affordable_designs_per_arm"])
    # The internal ceiling binds before the design and start ceilings: 160 / 20 = 8 designs and
    # 8 x 2 = 16 starts per arm, so the honest spendable amount is design-derived, not the stored
    # 12-design / 24-start ceilings.
    spendable_per_arm = {
        "designs": min(design_cap, affordable),
        "starts": min(starts_cap, affordable * int(cost["starts_per_design"])),
        "internal": min(internal_cap, affordable * int(cost["internal_per_design"])),
        "derivation": ("min(stored_cap, affordable_designs x per_design_cost); the 160-internal "
                       "ceiling binds first, so eight designs per arm is the honest number"),
    }
    spendable_all = {
        "designs": spendable_per_arm["designs"] * 3,
        "starts": spendable_per_arm["starts"] * 3,
        "internal": spendable_per_arm["internal"] * 3,
    }
    if spendable_all["starts"] > int(caps["max_starts_all_arms"]):
        problems.append("three-arm spendable starts %d exceed the frozen all-arm cap %d"
                        % (spendable_all["starts"], int(caps["max_starts_all_arms"])))
    if spendable_all["internal"] > int(caps["max_internal_all_arms"]):
        problems.append("three-arm spendable internal %d exceed the frozen all-arm cap %d"
                        % (spendable_all["internal"], int(caps["max_internal_all_arms"])))

    prior = prior_spend()
    authorized = {
        "designs": spendable_all["designs"] - prior["designs"],
        "starts": spendable_all["starts"] - prior["starts"],
        "internal": spendable_all["internal"] - prior["internal"],
    }
    if min(authorized.values()) < 0:
        problems.append("O1 already spent %r, which exceeds the spendable ceiling %r"
                        % (prior, spendable_all))

    if GO.is_file():
        existing = {}
        try:
            existing = json.loads(GO.read_text(encoding="utf-8"))
            existing_dossier = existing.get("a5_dossier_sha256")
        except Exception:  # noqa: BLE001
            existing_dossier = None
        claims_current = (existing_dossier == dossier_sha
                          and existing.get("preregistration_sha256") == sha_bytes(pre_bytes))
        if claims_current:
            problems.append("a GO for exactly these bytes already exists at %s (go_sha256 %r); "
                            "re-issuing it would erase the record of when it was first issued"
                            % (GO, existing.get("go_sha256")))
        else:
            problems.append("a GO exists at %s but binds dossier %r, not the bytes on disk "
                            "(%s). Overwriting it in place would erase the record of which "
                            "bytes were ever authorised; retire it first with "
                            "scripts/o1_retire_stale.py, which archives it under go_history/ "
                            "before removing it from the live path" % (GO, existing_dossier,
                                                                       dossier_sha))

    # A stale verdict copy or binding round on the live path is what makes a GO ambiguous, so
    # the retirement rule is enforced here rather than trusted: every live artifact a GO binds
    # must name the dossier bytes on disk.
    if VERDICT_COPY.is_file():
        try:
            copy_payload = json.loads(VERDICT_COPY.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            copy_payload = {"dossier_sha256": None}
        if copy_payload.get("dossier_sha256") != dossier_sha:
            problems.append("o1_a5_verdict.json binds dossier %r, not the bytes on disk; retire "
                            "it with scripts/o1_retire_stale.py"
                            % (copy_payload.get("dossier_sha256"),))

    if problems:
        report = {"go_issued": False, "problems": problems, "code_state": state,
                  "spendable": {"per_arm": spendable_per_arm, "all_arms": spendable_all},
                  "prior_spend": prior, "created_utc": datetime.now(
                      timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        BLOCKED.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    # The runner reads o1_a5_verdict.json; write it as an exact byte copy of the reviewed verdict
    # so that "the verdict the GO binds" and "the verdict the runner reads" cannot differ.
    verdict_bytes = VERDICT.read_bytes()
    VERDICT_COPY.write_bytes(verdict_bytes)

    go = {
        "schema": "dreal005.o1_go_record.v1",
        "go_issued": True,
        "go_issued_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issued_by": "Lead (agent), not a human approver and not the A5 reviewer",
        "authorization_kind": "O1_THREE_ARM",
        "owner_authorization_ref": pre["owner_authorization_ref"],
        "issue": 15,
        "run_id": pre["run_id"],
        "batch_id": pre["batch_id"],
        "authorization_id": pre["authorization_id"],
        "pairing": {"task_key": pre["pairing"]["task_key"],
                    "pairing_seed": pre["pairing"]["pairing_seed"],
                    "gp_seed": pre["pairing"]["gp_seed"],
                    "tasks_authorised": [pre["pairing"]["task_key"]]},
        "preregistration_path": str(PRE),
        "preregistration_sha256": sha_bytes(pre_bytes),
        "a5_dossier_path": str(DOSSIER),
        "a5_dossier_sha256": dossier_sha,
        "a5_dossier_receipt_path": str(RECEIPT),
        "a5_dossier_receipt_sha256": sha_file(RECEIPT),
        "a5_verdict_path": str(VERDICT_COPY),
        "a5_verdict_source_path": str(VERDICT),
        "a5_verdict_sha256": sha_bytes(verdict_bytes),
        "a5_verdict": verdict["verdict"],
        "a5_reviewer": verdict.get("reviewer"),
        "a5_human_signature": bool(verdict.get("human_signature")),
        "a5_verdict_is_byte_identical_copy": (
            "o1_a5_verdict.json is a byte copy of a5_review/verdict.json; a5_verdict_sha256 "
            "binds that copy, and the runner re-hashes it before spending anything"),
        "byte_binding": ("three independent values agree: sha256(dossier on disk), the external "
                         "o1_dossier_receipt.dossier.sha256, and verdict.dossier_sha256"),
        "byte_verifier": verifier_state,
        "byte_verifier_is_a_hard_precondition": (
            "this GO was refused unless o1_binding_verification.json reported "
            "O1_BYTES_BOUND_MECHANICALLY with zero failures over exactly these dossier bytes, "
            "written after the dossier and archived where it cannot be overwritten"),
        "code_shas": dict(pre["code"]["code_shas"]),
        "caps": caps,
        "cost_model": cost,
        "spendable_under_this_authorization": {"per_arm": spendable_per_arm,
                                               "all_arms": spendable_all},
        "carried_forward_from_earlier_stages": pre["carried_forward"],
        "prior_o1_spend": prior,
        "authorized_remaining": authorized,
        "physical_starts_authorized_this_go": authorized["starts"],
        "physical_starts_used_before_this_go": prior["starts"],
        "internal_cases_authorized": authorized["internal"],
        "designs_authorized_per_arm": spendable_per_arm["designs"],
        "physical_starts_if_everything_admits": (
            "48 equivalent starts minus the 6 equivalent support starts that are solved once = "
            "42 physical starts, of which 6 are the shared support block"),
        "not_authorized": pre["not_authorized"],
        "conditions": [
            "upload and remote readback after every 8 starts or 60 minutes before continuing",
            "abort the pairing if a shared support design fails to admit a raw row",
            "no retry of an interrupted start; an interrupted start stays charged",
            "lift tolerance 1e-3 is never relaxed and no interpolated row may be admitted",
            "the three arms are truncated at the same design count; the report must say so",
            "Mach 2.10 and any second seed require a separate preregistration, A5 review and GO",
        ],
    }
    body = json.dumps(go, ensure_ascii=False, indent=2, sort_keys=True)
    # The self hash covers the canonical JSON of every field except itself.
    go["go_sha256"] = sha_bytes(body.encode("utf-8"))
    go["go_sha256_scope"] = ("sha256 of the canonical JSON (sort_keys, indent 2) of every field "
                             "in this record except go_sha256 and go_sha256_scope")
    GO.write_text(json.dumps(go, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                  newline="\n")
    if BLOCKED.exists():
        BLOCKED.unlink()
    print(json.dumps({"go_issued": True, "go_record": str(GO), "go_file_sha256": sha_file(GO),
                      "go_sha256": go["go_sha256"], "a5_verdict": verdict["verdict"],
                      "a5_reviewer": verdict.get("reviewer"),
                      "authorized_remaining": authorized},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
