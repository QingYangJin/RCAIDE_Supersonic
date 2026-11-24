"""Issue the Lead GO for the O0-FINAL independent verification budget.

This is a second authorization, and it is deliberately harder to obtain than the first one:

  * the A5 verdict must be exactly the expected PASS and must bind to the current dossier bytes;
  * the dossier receipt and the reviewer measurement must agree with disk;
  * a mechanical byte verifier round must have read exactly these dossier bytes, after they were
    written, archived where it cannot be overwritten, with zero failures;
  * the pre-registration must already contain the itemized verification budget, and that budget
    must equal what scripts/o0_final.py would spend -- a budget typed into the runner is not a
    pre-registered budget;
  * the two designs to be verified are derived from the closed batch result by the frozen
    selection rule and written into this record by design id, because the pre-registration
    necessarily predates the batch that produced those ids;
  * the optimizer batch must be closed by its own batch record before any verification start.

A GO is issued by the Lead agent, not by a human and not by the A5 reviewer.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(RUN / "scripts"))

import o0_spend  # noqa: E402

PRE = RUN / "o0_preregistration.json"
DOSSIER = RUN / "o0_a5_dossier.md"
VERDICT = RUN / "a5_review/verdict.json"
RECEIPT = RUN / "o0_dossier_receipt.json"
VERIFIER = RUN / "o0_binding_verification.json"
FINAL_GO = RUN / "o0_final_go_record.json"
RESULT = RUN / "o0_result_B02.json"
EXPECTED = "H0_A0_O0_REVIEW_PASS"
KIND = "O0_FINAL_VERIFICATION"


def sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def spend_of(row: Dict[str, Any], name: str) -> tuple:
    """Read one abort/crash record's spend in either shape; unreadable is an error, not a zero."""
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


def carried_forward() -> Dict[str, Any]:
    """What the optimizer authorization already spent, counted once.

    Delegated to scripts/o0_spend.py: an abort record is batch-local while a crash record's
    ledger is authorization-cumulative, so summing the two would bill 24 starts for the 23 the
    authorization actually spent. A final GO that overstated the optimizer's spend would be
    wrong in the safe direction only by accident, and this record must not be accidentally right.
    """
    spend = o0_spend.authorization_spend(RUN)
    return {"design_attempts": spend["design_attempts"],
            "solver_starts": spend["solver_starts"],
            "internal_solver_cases": spend["internal_solver_cases"],
            "records": [{"record": r["name"], "sha256": r["sha256"], "basis": r["basis"],
                         "charged_starts": r["starts"], "internal_solver_cases": r["internal"],
                         "design_evaluations": r["designs"]} for r in spend["records"]],
            "counting_rule": spend["rule"],
            "basis_record": spend["basis_record"]}


def pick_designs(result: Dict[str, Any]) -> Dict[str, Any]:
    """The frozen selection rule: the admitted baseline, and the lowest-Di_N admitted candidate."""
    baseline = None
    best = None
    for row in result.get("attempts") or []:
        if row.get("status") != "FEASIBLE_ADMITTED":
            continue
        if row.get("is_baseline"):
            baseline = row
        elif best is None or float(row["di_n"]) < float(best["di_n"]):
            best = row
    return {"baseline": baseline, "best": best}


def main() -> int:
    problems: List[str] = []
    pre_bytes = PRE.read_bytes()
    pre = json.loads(pre_bytes.decode("utf-8"))
    dossier_sha = sha_file(DOSSIER)
    dossier_bytes = len(DOSSIER.read_bytes())
    v = json.loads(VERDICT.read_text(encoding="utf-8")) if VERDICT.is_file() else {}
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8")) if RECEIPT.is_file() else {}
    result = json.loads(RESULT.read_text(encoding="utf-8")) if RESULT.is_file() else {}

    # 1. Review: the PASS must name these exact bytes, and two independent records must agree.
    if v.get("verdict") != EXPECTED:
        problems.append("a5 verdict is %r, expected %r" % (v.get("verdict"), EXPECTED))
    if v.get("dossier_sha256") != dossier_sha:
        problems.append("a5 dossier binding is %r, current dossier is %s"
                        % (v.get("dossier_sha256"), dossier_sha))
    if v.get("preregistration_sha256") != hashlib.sha256(pre_bytes).hexdigest():
        problems.append("a5 preregistration binding is %r, current preregistration is %s"
                        % (v.get("preregistration_sha256"),
                           hashlib.sha256(pre_bytes).hexdigest()))
    receipt_sha = (receipt.get("dossier") or {}).get("sha256")
    if not receipt:
        problems.append("no o0_dossier_receipt.json exists; the dossier bytes are unbound")
    elif receipt_sha != dossier_sha:
        problems.append("dossier receipt binds %r, disk is %s" % (receipt_sha, dossier_sha))

    # 2. Mechanical byte verification over these bytes, after they were written, archived.
    verifier_state: Dict[str, Any] = {}
    if not VERIFIER.is_file():
        problems.append("no o0_binding_verification.json; the byte binding was never verified")
    else:
        ver = json.loads(VERIFIER.read_text(encoding="utf-8"))
        verifier_state = {
            "path": str(VERIFIER), "sha256": sha_file(VERIFIER),
            "status": ver.get("status"), "check_count": ver.get("check_count"),
            "failure_count": ver.get("failure_count"),
            "dossier_sha256": (ver.get("dossier") or {}).get("sha256"),
            "dossier_bytes": (ver.get("dossier") or {}).get("bytes"),
            "created_utc": ver.get("created_utc"), "archived_as": ver.get("archived_as"),
        }
        if ver.get("status") != "O0_BYTES_BOUND_MECHANICALLY":
            problems.append("byte verifier status is %r" % (ver.get("status"),))
        if int(ver.get("failure_count") or 0) != 0:
            problems.append("byte verifier reported %r failures" % (ver.get("failure_count"),))
        if (ver.get("dossier") or {}).get("sha256") != dossier_sha:
            problems.append("byte verifier read an earlier dossier; re-run the verifier")
        if int((ver.get("dossier") or {}).get("bytes") or -1) != dossier_bytes:
            problems.append("byte verifier recorded %r bytes, disk has %d"
                            % ((ver.get("dossier") or {}).get("bytes"), dossier_bytes))
        written = datetime.fromtimestamp(DOSSIER.stat().st_mtime, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        if str(ver.get("created_utc") or "") < written:
            problems.append("byte verifier round (%s) predates the dossier bytes (%s)"
                            % (ver.get("created_utc"), written))
        if not ver.get("archived_as"):
            problems.append("byte verifier round was not archived and can be overwritten")

    # 3. The verification budget must already be itemized in the pre-registration, and must equal
    #    the caps the runner would enforce. Anything else is an unreviewed budget.
    final_block = pre.get("o0_final") or {}
    budget_src = dict(final_block.get("separate_budget") or {})
    expected_budget = {"max_verification_starts": 8,
                       "max_verification_internal_cases": 104,
                       "max_repeat_runs_per_design": 2,
                       "max_wake_probe_starts": 2,
                       "max_void_rows": 2,
                       "n_wake_nodes_reference": 8,
                       "n_wake_nodes_probe": 16,
                       "refinement_points": 13}
    rename = {"max_verification_starts": "verification_starts_max",
              "max_verification_internal_cases": "verification_internal_cases_max",
              "max_wake_probe_starts": "wake_probe_starts_max",
              "max_void_rows": "void_rows_max"}
    budget: Dict[str, Any] = {}
    for key, value in expected_budget.items():
        source = rename.get(key, key)
        if source not in budget_src and key not in budget_src:
            problems.append("pre-registration does not state %r in o0_final.separate_budget, so "
                            "the verification budget was never reviewed" % (source,))
            continue
        raw = budget_src.get(source, budget_src.get(key))
        budget[key] = int(raw)
        if int(raw) != int(value):
            problems.append("pre-registration budget %s is %r but the runner enforces %r"
                            % (source, raw, value))
    auth_block = final_block.get("authorization") or {}
    if auth_block.get("authorization_kind") != KIND:
        problems.append("pre-registration authorization kind is %r, not %r"
                        % (auth_block.get("authorization_kind"), KIND))
    if not auth_block.get("requires_its_own_a5_review"):
        problems.append("pre-registration does not require its own A5 review")
    if not auth_block.get("requires_its_own_go"):
        problems.append("pre-registration does not require its own GO")

    # 4. The optimizer batch must be closed, and the two designs come from its result.
    closed = sorted(RUN.glob("o0_batch_close_*.json"))
    close_state: Dict[str, Any] = {}
    if not closed:
        problems.append("no o0_batch_close_*.json; the optimizer batch is not closed, so a "
                        "verification start would be unauditable")
    else:
        close = json.loads(closed[-1].read_text(encoding="utf-8"))
        close_state = {"path": str(closed[-1]), "sha256": sha_file(closed[-1]),
                       "outcome": close.get("outcome"),
                       "design_cap_fully_used": close.get("design_cap_fully_used")}
        if close.get("was_any_cap_exceeded"):
            problems.append("the optimizer batch record says a cap was exceeded")
    if not result:
        problems.append("no %s exists; the two designs to verify cannot be derived"
                        % (RESULT.name,))
    picks = pick_designs(result)
    if not picks["baseline"]:
        problems.append("the batch result has no admitted baseline row")
    if not picks["best"]:
        problems.append("the batch result has no admitted non-baseline row; the pre-registered "
                        "verdict for that case is NO_FEASIBLE_NONBASELINE and no verification "
                        "start may be authorized")
    authorized_designs = {}
    for name in ("baseline", "best"):
        row = picks[name] or {}
        authorized_designs[name] = {
            "design_id": row.get("design_id"),
            "design_index": row.get("design_index"),
            "is_baseline": bool(row.get("is_baseline")),
            "x12": row.get("x12"),
            "alpha_cent_deg": row.get("alpha_deg"),
            "batch_di_n": row.get("di_n"),
        }

    # 4b. A GO is a statement about bytes. If a GO already exists at the working path and binds
    #     other bytes, this script must not quietly overwrite it: the old record has to be retired
    #     into go_history/ first, so that the only way a GO changes is through a recorded
    #     supersession and never by an in-place rewrite that leaves no trace of the predecessor.
    if FINAL_GO.is_file():
        prior_go = {}
        try:
            prior_go = json.loads(FINAL_GO.read_text(encoding="utf-8"))
        except Exception:
            prior_go = {}
        if prior_go.get("a5_dossier_sha256") != dossier_sha:
            problems.append(
                "a GO already exists at %s and binds dossier %r, not the current %s; retire it with "
                "scripts/o0_retire_stale_final_go.py first. Overwriting a GO in place would erase "
                "the record of which bytes were ever authorized"
                % (FINAL_GO, prior_go.get("a5_dossier_sha256"), dossier_sha))

    # 5. The verification ledger must already show what the crashed first attempt spent, and the
    #    pre-registration must disclose it. A GO that pretends the verification is unspent would
    #    authorize a batch nine starts wide and would report a cost that never happened.
    ledger_path = RUN / (auth_block.get("ledger_file") or "o0_final/verification_ledger.json")
    ledger_state: Dict[str, Any] = {}
    repair_block = final_block.get("repair_of_the_first_verification_attempt") or {}
    if not ledger_path.is_file():
        problems.append("no %s; a verification GO cannot be issued before the earlier "
                        "verification spend is on the ledger" % (ledger_path,))
    else:
        led = json.loads(ledger_path.read_text(encoding="utf-8"))
        rows = led.get("rows") or []
        ledger_state = {
            "path": str(ledger_path), "sha256": sha_file(ledger_path),
            "verification_starts_actual": led.get("verification_starts_actual"),
            "verification_internal_cases_actual":
                led.get("verification_internal_cases_actual"),
            "kinds": [r.get("kind") for r in rows],
            "void_rows_actual": ledger_state.get("void_rows_actual"),
            "admissible_rows_actual": led.get("admissible_rows_actual"),
            "rows": [{"label": r.get("label"), "kind": r.get("kind"),
                      "starts": r.get("starts"), "internal": r.get("internal"),
                      "note": r.get("note")} for r in rows],
            "repair": led.get("repair"),
        }
        ledger_state["void_rows_actual"] = len([r for r in rows if r.get("kind") == "void"])
        if int(led.get("verification_starts_actual") or 0) != int(
                repair_block.get("spent_before_this_pre_registration") or 0):
            problems.append(
                "the ledger records %r verification starts but the pre-registration discloses %r "
                "as already spent; the two must agree or the replacement batch would either "
                "re-spend or hide starts"
                % (led.get("verification_starts_actual"),
                   repair_block.get("spent_before_this_pre_registration")))
        if int(led.get("verification_internal_cases_actual") or 0) != int(
                repair_block.get("internal_before_this_pre_registration") or 0):
            problems.append(
                "the ledger records %r verification internal cases but the pre-registration "
                "discloses %r" % (led.get("verification_internal_cases_actual"),
                                  repair_block.get("internal_before_this_pre_registration")))
        void_rows = [r for r in rows if r.get("kind") == "void"]
        if len(void_rows) != int(budget.get("max_void_rows") or 0):
            problems.append("the ledger holds %d void row(s) but the pre-registered void cap is %r"
                            % (len(void_rows), budget.get("max_void_rows")))
        for row in void_rows:
            evidence = row.get("evidence") or {}
            if not evidence.get("polar_sha256") or not evidence.get("case_result_sha256"):
                problems.append("void row %r carries no sha256 for the polar or the case_result it "
                                "charges; a row without evidence is a claim, not a bill"
                                % (row.get("label"),))
        if not repair_block:
            problems.append("the pre-registration has no "
                            "o0_final.repair_of_the_first_verification_attempt block, so the "
                            "crashed first attempt is not disclosed")
        if int(budget.get("max_verification_starts") or 0) < int(
                led.get("verification_starts_actual") or 0):
            problems.append("the pre-registered verification start cap is smaller than the starts "
                            "already spent")

    prior = carried_forward()
    if problems:
        report = {"go_issued": False, "authorization_kind": KIND, "problems": problems,
                  "byte_verifier": verifier_state, "batch_close": close_state,
                  "authorized_designs": authorized_designs, "carried_forward_optimizer": prior,
                  "verification_ledger": ledger_state}
        (RUN / "o0_final_go_blocked.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    go = {
        "schema": "dreal005.o0_final_go_record.v1",
        "go_issued": True,
        "go_issued_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "authorization_kind": KIND,
        "issued_by": "Lead (agent), not a human approver and not the A5 reviewer",
        "written_by": {
            "script": str(Path(__file__)),
            "sha256": sha_file(Path(__file__)),
            "argv": list(sys.argv),
            "why": ("a reader must be able to tell which writer produced this record; a GO whose "
                    "writer cannot be identified cannot be distinguished from one typed by hand"),
        },
        "owner_authorization_ref": pre.get("owner_authorization_ref"),
        "issue": pre.get("issue"),
        "run_id": pre.get("run_id"),
        "authorization_id": pre.get("authorization_id"),
        "preregistration_path": str(PRE),
        "preregistration_sha256": hashlib.sha256(pre_bytes).hexdigest(),
        "a5_dossier_path": str(DOSSIER),
        "a5_dossier_sha256": dossier_sha,
        "a5_dossier_bytes": dossier_bytes,
        "a5_dossier_receipt_path": str(RECEIPT),
        "a5_dossier_receipt_sha256": sha_file(RECEIPT),
        "a5_verdict_path": str(VERDICT),
        "a5_verdict_sha256": sha_file(VERDICT),
        "a5_verdict": v.get("verdict"),
        "a5_reviewer": v.get("reviewer"),
        "a5_human_signature": False,
        "byte_verifier": verifier_state,
        "byte_verifier_is_a_hard_precondition": (
            "this record was refused unless a fresh mechanical verifier round reported "
            "O0_BYTES_BOUND_MECHANICALLY with zero failures over exactly these dossier bytes, "
            "written after the dossier and archived where it cannot be overwritten"),
        "batch_close": close_state,
        "optimizer_batch_result": {"path": str(RESULT), "sha256": sha_file(RESULT)},
        "optimizer_carried_forward": prior,
        "optimizer_budget_note": (
            "the optimizer authorization is exhausted by design; this record authorizes no "
            "further optimizer start and cannot propose or admit a new design"),
        "authorized_designs": authorized_designs,
        "verification_budget": budget,
        "verification_budget_source": ("read back from o0_preregistration.json "
                                       "o0_final.separate_budget; a budget typed into the runner "
                                       "would not be pre-registered and is refused"),
        "verification_ledger": ledger_state,
        "verification_spend_carried_forward": {
            "starts_already_spent": ledger_state.get("verification_starts_actual"),
            "internal_cases_already_spent":
                ledger_state.get("verification_internal_cases_actual"),
            "budget_is_gross": ("the pre-registered 8 starts and 104 internal cases are the whole "
                                "of the verification step, gross. Three of those starts and 39 "
                                "internal cases were already spent before this GO; the five "
                                "starts and 65 internal cases that remain are what this GO "
                                "actually authorizes, and the ledger decides that, not this "
                                "paragraph"),
            "how_the_remainder_is_enforced": ("the runner reads the ledger back on start-up and "
                                              "refuses any charge past the pre-registered cap, "
                                              "so the already-spent starts are subtracted "
                                              "automatically rather than by arithmetic in a "
                                              "comment"),
        },
        "ledger_file": (auth_block.get("ledger_file")
                        or "o0_final/verification_ledger.json"),
        "caps_are_separate_from_the_optimizer_caps": (
            "these starts are itemized verification work; they never extend the O0 search "
            "budget and may not be used to look for a better design"),
        "not_authorized": [
            "any further optimizer start or any new design proposal",
            "O1 warm-start arms",
            "any change to the lift tolerance, target lift or reference quantities",
            "re-use of the O0 optimizer GO for verification work",
        ],
        "conditions": [
            "the verification ledger is charged before the case is evaluated and persists "
            "after every charge; a crash restarts owing what was already spent",
            "wake-probe cases at 16 wake nodes are never admitted and never counted as labels",
            "no retry of an interrupted verification start; an interrupted start stays charged",
            "lift tolerance 1e-3 is never relaxed and no interpolated row may be admitted",
            "resulting verdict is one of the four pre-registered verdict strings, never 'PASS'",
        ],
    }
    FINAL_GO.write_text(json.dumps(go, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({"go_issued": True, "final_go_record": str(FINAL_GO),
                      "final_go_sha256": sha_file(FINAL_GO),
                      "authorization_kind": KIND,
                      "authorized_designs": {k: v["design_id"]
                                             for k, v in authorized_designs.items()},
                      "verification_budget": budget},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())