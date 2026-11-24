"""Compose the A5 dossier for the D-REAL-EXP-003 H0/A0/O0 gates (zero physical).

The dossier is the only input the independent reviewer sees: exact code SHAs, the
frozen geometry contract, the A0 ablation result, the O0 protocol and its caps, and an
explicit statement of what is NOT authorized.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
A0 = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01")
sys.path.insert(0, str(RUN / "scripts"))
import o0_spend  # noqa: E402

SUPPORT = RUN / "a5_support/o0_a5_support_stats.json"
OUT = RUN / "o0_a5_dossier.md"
RECEIPT = RUN / "o0_dossier_receipt.json"
TICK = chr(96)
VAR_NAMES = ["wing_area", "aspect_ratio", "sweep_1", "sweep_2", "sweep_3",
             "span_location_2", "span_location_3", "chord_ratio_2", "chord_ratio_3",
             "tip_twist", "vertical_tail_area", "vertical_tail_sweep_delta"]
BASELINE_X12 = [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178,
                0.0, 33.91, 0.0]
FIX_EVIDENCE = RUN / "a5_support/fix_evidence/fix_evidence.json"
BINDING_HISTORY = RUN / "a5_support/binding_history"
CLOSE_RECORDS = sorted(RUN.glob("o0_batch_close_*.json"))
BATCH_RESULT = RUN / "o0_result_B02.json"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def code(text: str) -> str:
    return TICK + text + TICK


def latest_verification():
    """The most recent immutable verifier output, with its own path and hash.

    A dossier cannot contain its own final hash, so the honest anchor is an earlier round
    of the same mechanical check, archived under a name that is never overwritten. The
    reviewer can hash that file at any time; nothing here asks it to trust a number the
    document states about itself.
    """
    if not BINDING_HISTORY.is_dir():
        return None, None
    paths = sorted(BINDING_HISTORY.glob("o0_binding_verification_*.json"))
    if not paths:
        return None, None
    best, best_key = None, None
    for path in paths:
        try:
            row = load(path)
        except Exception:
            continue
        key = str(row.get("created_utc") or "")
        if best_key is None or key > best_key:
            best, best_key = (row, path), key
    if best is None:
        return None, None
    return best[0], best[1]


def spend_of(row: dict, name: str) -> tuple:
    """Read one abort/crash record's spend in either shape; unreadable is an error, not a zero.

    Abort records are written from the raw case directory with flat *_actual keys; crash records
    are written by o0_run.py and nest the ledger summary under "ledger". A dossier that read only
    one shape would understate what the authorization has already spent, which is the one number
    this section exists to get right.
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
    """What the authorization already spent, counted exactly once.

    Read back from disk rather than remembered, and counted by scripts/o0_spend.py because the
    two record shapes do not share a basis: an abort record is batch-local, while a crash
    record's ledger summary is authorization-cumulative and already includes what it carried
    forward. Summing them would print 24 starts for the 23 that were spent, and a dossier that
    overstated the bill would be asking the reviewer to authorize against a number that is not
    real. A reader who wants to check this can read o0_spend.authorization_spend() directly.
    """
    spend = o0_spend.authorization_spend(RUN)
    records = []
    for row in spend["records"]:
        path = RUN / row["name"]
        raw = load(path)
        records.append({"record": row["name"], "sha256": row["sha256"],
                        "basis": row["basis"],
                        "outcome": (raw.get("outcome") or raw.get("exception_text")
                                    or (raw.get("defect") or {}).get("what")),
                        "charged_starts": row["starts"],
                        "internal_solver_cases": row["internal"],
                        "design_evaluations": row["designs"],
                        "admitted_labels": raw.get("admitted_labels_actual"),
                        "exception": ((raw.get("root_cause") or {}).get("exception")
                                      or raw.get("exception_text"))})
    return {"design_attempts": spend["design_attempts"],
            "solver_starts": spend["solver_starts"],
            "internal_solver_cases": spend["internal_solver_cases"],
            "records": records,
            "counting_rule": spend["rule"],
            "basis_record": spend["basis_record"],
            "added_batch_local": spend["added_batch_local"]}


def main() -> int:
    pre = load(RUN / "o0_preregistration.json")
    h0 = load(REPO / "docs/evidence/dreal005/h0/h0_gate.json")
    contract = load(REPO / "docs/evidence/dreal005/h0/geometry_contract.json")
    a0 = load(A0 / "training/a0_result.json")
    cost = a0["cost"]
    sup = load(SUPPORT) if SUPPORT.is_file() else None
    lines = []
    add = lines.append

    add("# D-REAL-EXP-003 H0 / A0 / O0 independent review dossier")
    add("")
    add("Issue: #15 (2026-11-24) plus its first comment. Its title is "
        "\"[D-REAL-EXP-003][2026-11-24] \u4efb\u52a1\u6761\u4ef6\u5316FOMAML"
        "\u6d88\u878d\u4e0e\u771f\u5b9eBO\u4f18\u5316\uff1a\u7acb\u5373\u5f00"
        "\u542f\u53cd\u9988\u95ed\u73af\u3001\u7b49\u9884\u7b97\u70ed\u542f\u52a8"
        "\u5bf9\u7167\". That title is where the D-REAL-EXP-003 identifier in this "
        "dossier's name comes from: it is the experiment tag the Issue carries in its own "
        "title, not a label this dossier invents.")
    add("Reviewer: A5, an independent model that this round holds read-only local tools "
        "(sha256_file, stat_file, list_dir, read_text, grep) scoped to the run root and the "
        "run root, the frozen worktree and the read-only A0 run root, so every hash quoted "
        "below is checkable rather than merely stated. "
        "Not a human signature.")
    prior = carried_forward()
    close = load(CLOSE_RECORDS[-1]) if CLOSE_RECORDS else None
    if close:
        add("Physical VSPAERO starts used so far in this issue: **%d** (%d internal alpha "
            "cases): %d starts and %d internal cases by the aborted first attempt in section 0b, "
            "and %d starts and %d internal cases by the optimizer batch closed in section 4b. "
            "The optimizer cap is now fully spent, so there is no further optimizer batch; the "
            "only physics this document still asks for is the separate O0-FINAL verification "
            "budget in section 4b."
            % (prior["solver_starts"], prior["internal_solver_cases"],
               prior["solver_starts"] - int(close["batch_spend"]["solver_starts"]),
               prior["internal_solver_cases"] - int(close["batch_spend"]["internal_cases"]),
               int(close["batch_spend"]["solver_starts"]),
               int(close["batch_spend"]["internal_cases"])))
    else:
        add("Physical VSPAERO starts used so far in this issue: **%d** (%d internal alpha "
            "cases)." % (prior["solver_starts"], prior["internal_solver_cases"]))
    add("")
    add("## 0. File identity")
    add("")
    add("| file | sha256 | bytes |")
    add("| --- | --- | --- |")
    for rel in ("o0_preregistration.json", "o0_batch_close_B02.json",
                "o0_batch_crash_B02.json"):
        path = RUN / rel
        if path.is_file():
            add("| %s | %s | %d |" % (code(rel), code(sha_file(path)), path.stat().st_size))
    for rel in ("docs/evidence/dreal005/h0/h0_gate.json",
                "docs/evidence/dreal005/h0/geometry_contract.json",
                "docs/evidence/dreal005/h0/geometry_contract_verification.json"):
        path = REPO / rel
        add("| %s | %s | %d |" % (code(rel), code(sha_file(path)), path.stat().st_size))
    for rel in ("training/a0_result.json", "training/a0_grid_search.json",
                "tables/a0_arm_metrics.csv", "tables/a0_paired_differences.csv"):
        path = A0 / rel
        # Absolute path, because a reviewer with tools must be able to open the file instead of
        # guessing which root "A0/" is relative to. The A0 run root is a separate allowlisted root.
        add("| %s | %s | %d |" % (code(str(path)), code(sha_file(path)),
                                  path.stat().st_size))
    add("")
    add("**Byte-to-gate binding (verifiable, not asserted).** This dossier cannot contain "
        "its own hash, so the binding is closed from outside in three verifiable steps, and "
        "no step trusts a value this document asserts about itself:")
    add("")
    add("1. Immediately after these bytes are written, " + code("o0_dossier_receipt.json") +
        " is written with the SHA256 and byte count of this exact file, plus the SHA256 of " +
        code("o0_preregistration.json") + ".")
    add("2. The review harness reads these exact bytes from disk, computes sha256 of them, "
        "hands those same bytes to the reviewer and records the measured value in the verdict "
        "as dossier_sha256. The reviewer measures it too when it has tools; the harness value "
        "is substituted for the model's own and both are kept, so neither is taken on trust.")
    add("3. " + code("scripts/o0_verify_binding.py") + " then re-reads the bytes off disk and "
        "writes " + code("o0_binding_verification.json") + " plus an immutable copy under "
        + code("a5_support/binding_history/") + ", and " + code("o0_make_go.py")
        + " is hard-gated on that fresh round: it refuses to issue a GO unless the round "
        "reports " + code("O0_BYTES_BOUND_MECHANICALLY") + " with zero failures, was written "
        "after the dossier bytes, read exactly the current dossier hash and byte count, is "
        "archived, and agrees with both the receipt and verdict.dossier_sha256. One flipped "
        "byte anywhere in that chain blocks the GO with a named reason.")
    add("")
    add("Any reader holding these bytes can check the whole chain offline with one sha256sum "
        "of this file plus two comparisons against the receipt and the verdict. No gate "
        "depends on a hash value that the document reports about itself.")
    add("")
    add("**A document cannot contain its own final hash, so the anchor is the artifact "
        + "that does.** This file is written first; " + code("scripts/o0_verify_binding.py")
        + " then reads the bytes off disk, hashes them, and writes "
        + code("o0_binding_verification.json") + " containing that hash plus the receipt hash "
        + "plus the verdict hash. The GO is refused unless that verifier reports "
        + code("O0_BYTES_BOUND_MECHANICALLY") + " with zero failures. The block below is the "
        + "round already on disk, quoted so the procedure can be inspected without running it: "
        + "it exists because a current-round value cannot be written into the file it measures.")
    add("")
    # Every archived round, in one table: a reviewer should see the failures too, not only the
    # round that happened to pass. Rounds that failed because the verdict still bound older
    # dossier bytes are the expected intermediate state between a dossier edit and its review,
    # and hiding them would make this section look stronger than the archive is.
    rounds = []
    if BINDING_HISTORY.is_dir():
        for path in sorted(BINDING_HISTORY.glob("o0_binding_verification_*.json")):
            try:
                row = load(path)
            except Exception:
                continue
            rounds.append((path, row))
    passing = [(p, r) for p, r in rounds if str(r.get("status")) == "O0_BYTES_BOUND_MECHANICALLY"
               and int(r.get("failure_count") or 0) == 0]
    add("| archived round | status | failures | dossier sha it read | dossier bytes |")
    add("| --- | --- | --- | --- | --- |")
    for path, row in rounds:
        add("| %s | %s | %s | %s | %s |"
            % (code(path.name), code(str(row.get("status"))),
               row.get("failure_count"),
               code(str((row.get("dossier") or {}).get("sha256"))),
               (row.get("dossier") or {}).get("bytes")))
    add("")
    if rounds:
        add("Archive directory: %s. %d round(s) archived, %d of them clean."
            % (code(str(BINDING_HISTORY)), len(rounds), len(passing)))
    add("")
    prev, prev_path = ((passing[-1][1], passing[-1][0]) if passing else (None, None))
    if prev is None:
        add("No archived verifier round has ever passed, so the chain is unproven in this "
            "document and the correct verdict is CHANGES_REQUIRED.")
        add("")
    else:
        add("~~~")
        add("verifier file      : " + str(prev_path.name))
        add("archived at        : " + str(prev_path))
        add("verifier sha256    : " + sha_file(prev_path))
        add("status             : " + str(prev.get("status")))
        add("check_count        : " + str(prev.get("check_count")))
        add("failure_count      : " + str(prev.get("failure_count")))
        add("problems           : " + json.dumps(prev.get("problems") or []))
        add("dossier sha it read: " + str((prev.get("dossier") or {}).get("sha256")))
        add("~~~")
        add("")
        add("**Read the quoted round for exactly what it is.** It is the most recent round that "
            "passed, and it is necessarily a round over an EARLIER dossier: a round over the "
            "bytes you are reading cannot be written into this file, and one cannot exist yet "
            "either, because the round that binds these bytes also has to agree with the "
            "verdict, and the verdict is produced from this file. So the honest order is "
            "dossier, then review, then the binding round, then the GO; the round is a hard "
            "precondition of the GO and never an input to this document. The table above shows "
            "every archived round including the failed ones, because the failures are the "
            "expected intermediate state between a dossier edit and its review, and a table "
            "showing only the clean rows would overstate the archive.")
        add("")
        add("The reviewer can close the loop itself this round: read "
            + code("scripts/o0_verify_binding.py") + " and " + code("scripts/o0_make_go.py")
            + ", then require as a condition of the verdict that the fresh round reports "
            + code("O0_BYTES_BOUND_MECHANICALLY") + ", with zero failures, created after this "
            "file's mtime, carrying this file's sha256 and byte count, archived, and equal to "
            "the receipt and the verdict hash. Every one of those checks is enforced in "
            + code("o0_make_go.py") + " before a GO can exist, so the condition is mechanical "
            "rather than rhetorical.")
        add("")
    fix_ev = load(FIX_EVIDENCE) if FIX_EVIDENCE.is_file() else None
    add("## 0b. The aborted first attempt (O0-B01), disclosed rather than deleted")
    add("")
    add("The first real batch did run, for one charged start, and then stopped on a code defect "
        "in the Lead's own orchestration. It is reported here in full because a reviewer "
        "comparing this dossier against the earlier request would otherwise be reviewing a "
        "protocol that has never touched the solver, and that would be false.")
    add("")
    for rec in prior["records"]:
        if rec["basis"] == "BATCH_LOCAL":
            add("- %s (sha256 %s, basis BATCH_LOCAL): outcome %s; this batch charged %s solver "
                "start(s), %s internal alpha case(s) and %s design evaluation(s); admitted labels "
                "%s; recorded exception %s."
                % (code(rec["record"]), code(str(rec["sha256"])), code(str(rec["outcome"])),
                   rec["charged_starts"], rec["internal_solver_cases"],
                   rec["design_evaluations"], rec["admitted_labels"],
                   code(str(rec["exception"]))))
        else:
            add("- %s (sha256 %s, basis AUTHORIZATION_CUMULATIVE): outcome %s; its ledger counts "
                "the whole authorization, i.e. %s solver starts, %s internal alpha cases and %s "
                "design attempts including everything carried forward from the record above, so "
                "it is read as a running total and never added to the batch-local record; "
                "recorded exception %s."
                % (code(rec["record"]), code(str(rec["sha256"])), code(str(rec["outcome"])),
                   rec["charged_starts"], rec["internal_solver_cases"],
                   rec["design_evaluations"], code(str(rec["exception"]))))
    add("")
    add("**What went wrong.** " + code("solver_runner.run_case()") + " reports the case result "
        "as the path of " + code("case_result.json") + ", not as an inline object. The "
        "evaluator consumed that path as if it were a dict, so the coarse bracket parse raised "
        + code("AttributeError: 'str' object has no attribute 'get'") + " after the solver had "
        "already solved. Two fixes follow from that, and both change code under review:")
    add("")
    add("1. " + code("o0_eval.bracket_rows()") + " now loads the JSON when the field is a path "
        "and keeps the inline-dict branch for callers that pass one. The real polar that was "
        "already paid for was then replayed through the fixed path with zero new starts: the "
        "seven rows reproduce the root alpha at 5.18132 deg with a quadratic fit R^2 of "
        "0.999988 over a slope of 0.034384 per degree, which confirms the coarse bracket was "
        "usable and that only the parse was broken.")
    add("2. " + code("o0_short_bo.evaluate_and_settle()") + " wraps every evaluator call so that "
        "an exception still settles whatever the evaluator already declared it spent before the "
        "error propagates. A start that has been paid for can no longer vanish from the counters "
        "just because the surrounding code raised.")
    add("")
    add("**What the aborted start cost, and exactly how much of a design it was.** The crash "
        "happened between the two stages of design 0, so only the coarse stage was ever paid "
        "for: one solver start and seven internal alpha cases (the seven-point bracket). The "
        "thirteen-point refinement stage never ran and its second start was never issued. A "
        "complete design costs two starts and twenty internal cases, which is why this "
        "carry-forward reads one of twenty rather than two of twenty: the design is a third "
        "paid for, not half.")
    add("")
    ceil_designs = pre["caps"]["max_design_attempts"]
    per_design_starts = pre["caps"]["max_starts_per_design"]
    per_design_internal = pre["caps"]["max_internal_per_design"]
    spendable_starts = ceil_designs * per_design_starts
    spendable_internal = ceil_designs * per_design_internal
    designs_left = ceil_designs - prior["design_attempts"]
    further_starts = spendable_starts - prior["solver_starts"]
    further_internal = spendable_internal - prior["internal_solver_cases"]
    needed_starts = designs_left * per_design_starts
    needed_internal = designs_left * per_design_internal
    add("**The budget arithmetic, written out so it cannot be read two ways.** Each design "
        "costs exactly %d starts and exactly %d internal cases, and the design cap is %d. "
        "Therefore the most this authorization can ever spend is %d x %d = %d starts and "
        "%d x %d = %d internal cases. The two stored ceilings behave differently, and both "
        "statements are checked rather than assumed: the %d-start ceiling is strictly inert "
        "because %d < %d, so the design cap binds first and those extra starts can never be "
        "reached; the %d-internal ceiling is not inert, it coincides exactly with the design "
        "cap (%d = %d), so the two bind together and cross-check each other instead of one "
        "being slack. Quoting 36 starts as if it were usable budget was the mistake in the "
        "previous round, and it is not repeated here."
        % (per_design_starts, per_design_internal, ceil_designs, ceil_designs,
           per_design_starts, spendable_starts, ceil_designs, per_design_internal,
           spendable_internal, pre["caps"]["max_solver_starts"], spendable_starts,
           pre["caps"]["max_solver_starts"], pre["caps"]["max_internal_cases"],
           spendable_internal, pre["caps"]["max_internal_cases"]))
    add("")
    if designs_left > 0:
        add("Carry-forward, closed against the design cap so no reader has to guess: %d of %d "
            "design attempts remain, %d of %d spendable starts remain (%d already paid), and %d "
            "of %d spendable internal cases remain (%d already paid). Those remaining designs "
            "need exactly %d starts and %d internal cases, which fits with %d spare start(s) and "
            "%d spare internal case(s); the design cap and the spendable ceilings therefore never "
            "disagree." 
            % (designs_left, ceil_designs, further_starts, spendable_starts,
               prior["solver_starts"], further_internal, spendable_internal,
               prior["internal_solver_cases"], needed_starts, needed_internal,
               further_starts - needed_starts, further_internal - needed_internal))
    else:
        add("Carry-forward, closed against the design cap so no reader has to guess: %d of %d "
            "design attempts remain, because all %d are spent and the last one was closed by "
            "the batch record in section 4b. %d of %d spendable starts and %d of %d spendable "
            "internal cases also remain unspent, but they are stranded rather than available: a "
            "start cannot be spent without a design to spend it on, and none may be proposed. "
            "The two caps therefore still agree with each other, and the residue is stated here "
            "instead of being offered as spare budget."
            % (designs_left, ceil_designs, prior["design_attempts"], further_starts,
               spendable_starts, further_internal, spendable_internal))
    add("")
    add("**No label was manufactured out of it.** The aborted design has no admitted raw row. "
        "Two different gaps are in play and they should not be conflated: the coarse grid moves "
        "alpha in 0.35 deg steps, which at the measured 0.0328-0.0338 CL/deg slope is about "
        "0.012 CL between neighbouring rows, roughly an order of magnitude coarser than the "
        "1e-3 lift tolerance in CL, and about 330 times the tolerance when the same gap is "
        "expressed in alpha. Interpolation can bridge the CL gap to any accuracy one likes, "
        "but it does not create a row, so nothing was promoted and the design carries no "
        "label. The refine stage exists to turn that bridged alpha into an actual sampled row "
        "inside tolerance, and it never ran.")
    add("")
    add("**Why this is a protocol question for the reviewer, not just an incident report.** The "
        "reviewer is asked to decide whether this record is fit to stand as the account of "
        "what was spent, after (a) the parse defect is fixed, (b) exception-path settlement is "
        "enforced in code, and (c) the charged start is carried forward instead of reset. If the "
        "reviewer judges that a fixed defect plus a carried-forward charge is not enough, the "
        "correct verdict is CHANGES_REQUIRED, and neither the optimizer GO nor the O0-FINAL GO "
        "will be issued; both writers refuse to issue one without a PASS on these exact bytes.")
    add("")
    add("**Review ordering, stated because it is easy to misread as a missing artifact.** At "
        "the moment this dossier is reviewed there is deliberately no GO record and no A5 "
        "verdict for this batch: " + code("o0_make_go.py") + " refuses to write a GO unless a "
        "PASS verdict already exists and binds to these exact bytes, so a GO cannot precede "
        "the review that authorizes it. A missing o0_go_record.json is therefore the correct "
        "pre-review state, and its absence is checkable, not an omission. The dossier asks "
        "for fitness to be authorized; it does not assert that authorization happened.")
    add("")
    add("**The binding is also mechanically checked by a tool, not only described here.** "
        + code("scripts/o0_verify_binding.py") + " (sha256 " + code(sha_file(RUN / "scripts/o0_verify_binding.py")) +
        ") recomputes every hash in this chain from the files on disk and fails if any of them "
        "disagrees: dossier bytes, receipt record, preregistration bytes, all code SHAs, the "
        "verdict and the GO when they exist. It writes " + code("o0_binding_verification.json") +
        ". A reviewer who suspects the binding is merely asserted can ask for that file, or "
        "re-run those commands directly; nothing in the chain needs the reviewer to trust a "
        "number printed in this document.")
    add("")
    add("H0 gate canonical hash: %s. Geometry contract: %s."
        % (code(h0["h0_gate_sha256"]), code(h0["geometry_contract_sha256"])))
    add("")
    add("## 0c. Executed evidence that the two fixes are in the frozen code")
    add("")
    add("The previous review said, correctly, that section 0b described two fixes but showed no "
        "execution under the listed code SHAs. This section is that execution, produced offline "
        "with zero solver starts by " + code("scripts/o0_fix_evidence.py") + ".")
    add("")
    if fix_ev is not None:
        add("Evidence file: %s (sha256 %s, %d bytes)."
            % (code("a5_support/fix_evidence/fix_evidence.json"), code(sha_file(FIX_EVIDENCE)),
               FIX_EVIDENCE.stat().st_size))
        add("")
        add("| artifact | sha256 | bytes |")
        add("| --- | --- | --- |")
        for name in ("bracket_rows_excerpt", "evaluate_and_settle_excerpt"):
            row = fix_ev["results"].get(name) or {}
            add("| %s | %s | %s |" % (code(name), code(str(row.get("excerpt_sha256"))),
                                      row.get("excerpt_bytes")))
        add("")
        r1 = fix_ev["results"].get("pytest_o0_short_bo") or {}
        r2 = fix_ev["results"].get("pytest_ledger") or {}
        r3 = fix_ev["results"].get("replay_paid_b01") or {}
        add("- `pytest research/concorde_metaopt/tests/test_recovery_o0_short_bo.py -q` -> exit "
            "%s, %s (log sha256 %s). That file contains the two regression tests for the "
            "exception-path settle and the over-declared-charge case."
            % (r1.get("returncode"), code((r1.get("tail") or ["?"])[-1]),
               code(str(r1.get("log_sha256")))))
        add("- `pytest research/concorde_metaopt/tests/test_recovery_ledger.py -q` -> exit %s, %s "
            "(log sha256 %s)." % (r2.get("returncode"), code((r2.get("tail") or ["?"])[-1]),
                                  code(str(r2.get("log_sha256")))))
        pred = r3.get("predict") or {}
        replay_json = load(Path(r3["json"])) if r3.get("json") else {}
        fit = replay_json.get("fit") or {}
        refine = replay_json.get("refine") or {}
        add("- Replay of the paid B01 polar through the fixed parse path -> exit %s, %s rows, "
            "method %s, root alpha %s deg, quadratic R^2 %s on %s points, refine window %s to "
            "%s deg. This is real solver output that was already charged, read back with zero "
            "new starts; it exercises exactly the code path that raised on B01."
            % (r3.get("returncode"), r3.get("n_rows"), code(str(pred.get("method"))),
               ("%.5f" % pred["predicted_alpha_deg"]) if pred.get("predicted_alpha_deg") else "n/a",
               ("%.6f" % fit["r2"]) if fit.get("r2") is not None else "n/a",
               fit.get("n_points"), refine.get("min"), refine.get("max")))
    else:
        add("The evidence file is absent, which by this dossier's own rule means the two fixes "
            "are unproven and the correct verdict is CHANGES_REQUIRED.")
    add("")
    add("## 1. Exact code SHAs under review")
    add("")
    add("| path | sha256 | bytes |")
    add("| --- | --- | --- |")
    for rel, row in pre["code_shas"].items():
        add("| %s | %s | %s |" % (code(rel), code(str(row["sha256"])), row["bytes"]))
    add("")
    add("These are the only files that will execute in the O0 batch. Everything else is "
        "read-only data. If any of them changes, this review is void.")
    add("")
    add("**Where each path actually lives, so a reviewer with tools can hash it.** Paths of the "
        "form %s resolve against the run root %s, NOT against the frozen worktree; the worktree "
        "has its own %s directory with unrelated files in it. Repository paths such as %s "
        "resolve against the frozen worktree %s. The external audit script is listed by absolute "
        "path because it lives in a third root. The table above prints the bare path only "
        "because that is the key the pre-registration stores; this paragraph is the mapping."
        % (code("scripts/o0_*.py"), code(str(RUN)), code("scripts/"),
           code("research/concorde_metaopt/..."), code(str(REPO))))
    add("")
    add("## 2. H0 gate: frozen geometry contract and the design-space conflict")
    add("")
    add("- Frozen 12 variables in order: %s."
        % ", ".join(code(v) for v in pre["geometry"]["variable_order"]))
    add("- Fixed fuselage variables: %s."
        % ", ".join("%s=%s" % (code(k), v) for k, v in pre["geometry"]["fixed_15"].items()))
    add("- Baseline 12D vector: %s." % code(json.dumps(pre["geometry"]["baseline_x12"])))
    add("- Baseline design id: %s." % code(pre["geometry"]["baseline_design_id"]))
    add("")
    add("**Recorded conflict, not silently fixed.** %s declares stage P1 with "
        "frozen true; design_space._validate_space raises for any frozen space, so "
        "load_design_space() cannot load the 12D YAML from the production path. The lead did "
        "NOT flip frozen to false and did NOT touch main. The H0 contract file is the "
        "executable frozen copy and the optimizer builds geometry with build_geometry() "
        "directly, bypassing only that guard."
        % code("research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"))
    add("")
    probe_path = RUN / "audits" / "production_loader_probe.json"
    if probe_path.is_file():
        probe_bytes = probe_path.read_bytes()
        probe = json.loads(probe_bytes.decode("utf-8"))
        add("Production loader probe on the untouched YAML, archived at "
            + code("audits/production_loader_probe.json") + " (sha256 "
            + hashlib.sha256(probe_bytes).hexdigest() + ", " + str(len(probe_bytes)) + " bytes): "
            + "loaded=%s, exception_type=%s, physical solver starts %s."
            % (probe.get("loaded"), probe.get("exception_type"),
               probe.get("physical_solver_starts_actual")))
        add("")
        add("    " + str(probe.get("exception_text")))
    else:
        add("Production loader probe on the untouched YAML: loaded=%s, exception_type=%s. "
            "No archived probe artifact exists, so this claim is unverified."
            % (contract["production_loader_probe"]["loaded"],
               contract["production_loader_probe"]["exception_type"]))
    add("")
    add("Active-mask evidence from the measured 12D CDi response audit on existing raw rows: "
        "max|dCDi| sweep_1 1.707e-3, sweep_2 6.977e-4, wing_area 1.45e-10, "
        "vertical_tail_area 0.0, fuselage_length 0.0. Nine of twelve variables show no "
        "measurable CDi response on those samples, so this batch optimizes only the "
        "sweep_1/sweep_2 local box. The dossier does not claim the other ten variables are "
        "physically irrelevant; it claims this batch does not spend starts to find out.")
    add("")
    add("**Stated limit of that evidence: the response audit rests on N=8 historical M202 "
        "rows**, roughly one perturbed design per variable, so a small CDi effect on a "
        "variable could hide inside the row-to-row spread. That is precisely why the search "
        "space here is a local 2D box around the frozen baseline, and why an O0 result will be "
        "reported as a local improvement at fixed lift, never as a statement about the full "
        "12D design space.")
    add("")
    add("## 3. A0 ablation: what was actually trained")
    add("")
    add("- scope %s; training scope %s." % (code(a0["scope"]), code(a0["training_scope"])))
    add("- physical starts %s; internal alpha cases %s; admitted labels %s; "
        "physics_validated %s; fuel_burn_kg %s."
        % (a0["physical_solver_starts_actual"], a0["internal_solver_cases_actual"],
           a0["admitted_scientific_labels"], a0["physics_validated"], a0["fuel_burn_kg"]))
    add("- Arms: %s." % ", ".join(code(name) for name in a0["arms"]))
    add("- COND_SUPERVISED_16D is a plain supervised MSE regressor on 16 inputs (12 "
        "normalised design coordinates plus 4 known task conditions). It never calls "
        "meta_train_step and its recorded inner_gradient_updates is 0. That is the specific "
        "P2 defect Issue #15 asked to fix.")
    add("- COND_FOMAML_16D is the same network under a first-order MAML outer loop. The "
        "primary mechanism comparison is COND_FOMAML_16D minus COND_SUPERVISED_16D at equal "
        "K and equal seed.")
    add("- Checkpoint selection is unified: every trained arm reports the step with minimum "
        "validation MAE at validation K=%d, so no arm is advantaged by picking last vs best."
        % int(pre.get("validation_k") or 1))
    add("- Mean test MAE by arm and K (n = 2 test tasks x 3 seeds), newtons:")
    add("")
    add("| arm | K=0 | K=1 | K=3 |")
    add("| --- | --- | --- | --- |")
    table = {}
    for row in a0["summary"]:
        if row["split"] != "test":
            continue
        table.setdefault(row["arm"], {})[row["k"]] = row["mean_mae_n"]
    for arm in a0["arms"]:
        cells = table.get(arm, {})
        add("| %s | %s | %s | %s |" % (
            code(arm),
            ("%.1f" % cells[0]) if 0 in cells else "-",
            ("%.1f" % cells[1]) if 1 in cells else "-",
            ("%.3f" % cells[3]) if 3 in cells else "-"))
    add("")
    add("Core pair mean test delta (COND_FOMAML_16D minus COND_SUPERVISED_16D): **%.1f N**."
        % a0["core_pair_mean_test_delta_mae_n"])
    add("")
    add("Reading rule stated up front: the large effect is the 4D condition vector, not the "
        "meta objective. The meta objective helps slightly at K=1 and K=3 and is worse at "
        "K=0. Predicting Di_N in newtons is not a claim about sampling speed.")
    add("")
    add("Cost actually spent (offline training, host-wide sampling): wall %.1f s, CPU busy "
        "mean %.3f, memory load mean %.2f%%, peak tracked working set %.1f MB."
        % (cost["training_wall_s"], cost["cpu_busy_fraction_mean"],
           cost["memory_load_percent_mean"], cost["tracked_working_set_bytes_max"] / 1e6))
    add("")
    if sup is not None:
        st = sup["a0_paired_statistics"]
        add("### 3b. Paired dispersion for the core pair, and what it does NOT show")
        add("")
        add("The core pair is paired cell by cell (same task, same seed, same K): %d test "
            "cells and %d validation cells." % (st["test"]["n_cells"], st["val"]["n_cells"]))
        add("")
        add("| split | mean delta (N) | sd | 95% bootstrap CI of the mean | FOMAML better | supervised better | sign-test p |")
        add("| --- | --- | --- | --- | --- | --- | --- |")
        for split in ("test", "val"):
            row = st[split]
            ci = row["bootstrap_95_ci_mean_delta_n"]
            add("| %s | %.1f | %.1f | [%.1f, %.1f] | %d | %d | %.3f |"
                % (split, row["mean_delta_mae_n"], row["sd_delta_mae_n"], ci[0], ci[1],
                   row["count_fomaml_better"], row["count_supervised_better"],
                   row["sign_test_two_sided_p"]))
        add("")
        add("**Read this honestly: the meta objective is not established by A0.** On the test "
            "split the -893 N point estimate has a 95 percent interval that straddles zero, and "
            "FOMAML wins 8 of 18 paired cells against 10 losses. On validation the same "
            "comparison is significantly *worse* for FOMAML. The defensible conclusion is that "
            "the 4D condition vector is the large, reproducible effect and that a first-order "
            "meta objective makes no measurable difference at K<=3 on this data volume. O0 is "
            "therefore not premised on the meta learner being better; it is premised on the "
            "conditional model being usable inside a real feedback loop.")
        add("")
        am = sup["o0_alpha_resolution_margin"]
        add("### 3c. Alpha resolution measured from the raw polars, across all real runs")
        add("")
        add("The reviewer objected that the replay evidence was circular and rested on one run. "
            "These numbers are recomputed differently: every readable M202 polar in every real "
            "run root is read (%d roots searched), cases are grouped by their 12D design vector "
            "so a re-run of the same design counts once, the widest-span polar per design is "
            "used, and a quadratic CL(alpha) fit locates the fixed-lift root. %d unique designs "
            "yielded a locatable root; %d further design(s) were kept out because their root "
            "lies outside the measured alpha span, and they are listed rather than extrapolated."
            % (am["n_run_roots_searched"], am["n_unique_designs"], len(am["outside_span"])))
        add("")
        add("| quantity | value |")
        add("| --- | --- |")
        add("| CL slope at the target | %.5f to %.5f per deg |"
            % tuple(am["cl_slope_per_deg_range"]))
        add("| alpha half-width of the 1e-3 lift tolerance | %.4f to %.4f deg |"
            % tuple(am["tolerance_window_half_width_deg_range"]))
        add("| refinement step | 0.004 deg |")
        add("| raw rows guaranteed inside the tolerance window | at least %d |"
            % am["min_rows_guaranteed_inside_tolerance_window"])
        add("| refinement half-width (0.024 deg) in CL units | %.6f |"
            % am["refine_half_width_in_cl_units"])
        add("| refinement half-width vs the tolerance window | %.2fx |"
            % am["refine_half_width_vs_tolerance"])
        add("| largest measured root offset from the coarse centre | %.4f deg |"
            % am["max_alpha_root_offset_from_coarse_centre_deg"])
        add("| coarse bracket half-width | %.2f deg |" % am["coarse_half_width_deg"])
        add("| coarse coverage margin over the worst measured root | %.4f deg |"
            % am["coarse_coverage_margin_deg"])
        coup = am.get("measured_sweep_1_alpha_root_coupling_deg_per_deg")
        add("| measured sweep_1 -> fixed-lift alpha coupling | %s deg per deg |"
            % ("n/a" if coup is None else "%.4f" % coup))
        add("")
        add("Per-design measurements (all rows are real VSPAERO polars):")
        add("")
        add("| design id | differs from baseline in | area, sweep_1, sweep_2 | source run | "
            "alpha span | root alpha | CL slope |")
        add("| --- | --- | --- | --- | --- | --- | --- |")
        for d in am["designs"]:
            key = list(d["design_key"])
            diffs = [VAR_NAMES[i] for i in range(12)
                     if abs(float(key[i]) - float(BASELINE_X12[i])) > 1e-9]
            did = hashlib.sha256(json.dumps(key).encode("utf-8")).hexdigest()[:8]
            add("| %s | %s | %.4f m2, %.1f, %.1f | %s | %.2f to %.2f deg | %.4f deg | %.5f |"
                % (code(did),
                   code(", ".join(diffs)) if diffs else "nothing (this is the frozen baseline)",
                   d["wing_area_m2"], d["sweep_1_deg"], d["sweep_2_deg"],
                   code(d["source_run_id"]), d["source_alpha_span_deg"][0],
                   d["source_alpha_span_deg"][1], d["alpha_root_deg"],
                   d["local_cl_slope_per_deg"]))
        add("")
        add("What that buys, stated as a margin rather than a hope: the 1e-3 tolerance is about "
            "0.005 deg of alpha wide, the refinement step is 0.004 deg, so any design whose true "
            "root lies within the 0.024 deg refinement window has at least %d raw rows inside "
            "tolerance. The refinement half-width is %.2fx the tolerance window, which is the "
            "estimator margin, and the coarse bracket covers every measured root with %.2f deg "
            "to spare."
            % (am["min_rows_guaranteed_inside_tolerance_window"],
               am["refine_half_width_vs_tolerance"], am["coarse_coverage_margin_deg"]))
        add("")
        add("**The residual risk is named, not hidden, and the evidence limit is stated.** This "
            "is 7 unique designs from the historical M202 sweep family, not a sample over the O0 "
            "subspace: it supports the tolerance-window geometry (a 1e-3 lift tolerance really is "
            "about 0.005 deg of alpha, so a 0.004 deg step cannot miss the window when the coarse "
            "fit lands inside 0.024 deg), and it does not prove that a novel subspace design's "
            "root always lands inside the 2.1 deg bracket. If a design's root falls outside the "
            "0.024 deg refinement window it records objective=None and still pays both starts, "
            "which is the failure mode the ledger charges and the tables report. %d skipped "
            "case(s) are listed with reasons in the support file rather than quietly dropped."
            % len(am["skipped"]))
        add("")
        add("Support statistics file: %s (sha256 %s, %d bytes), produced offline with zero "
            "solver starts, and re-runnable by anyone holding the raw runs."
            % (code("a5_support/o0_a5_support_stats.json"), sha_file(SUPPORT),
               SUPPORT.stat().st_size))
        add("")
        add("**The quantitative version of the alpha argument, so it does not rest on prose.** "
            "The coarse bracket is a plus minus %.2f deg window around the baseline alpha %.2f "
            "deg. The search box is plus minus 1.5 deg in sweep_1 and plus minus 1.5 deg in "
            "sweep_2, both smaller than the plus minus 1.05 deg bracket that the historical "
            "polars span. The measured sweep_1 to fixed-lift alpha coupling is %.4f deg per "
            "deg, so moving sweep_1 across its whole +-1.5 deg box moves the fixed-lift alpha "
            "by at most about %.2f deg, which is %.1fx smaller than the bracket half-width. "
            "That is why the 7-row coarse quadratic is expected to land inside the 0.024 deg "
            "refinement window even for a design the historical data has never seen."
            % (am["coarse_half_width_deg"], 5.18,
               coup if coup is not None else 0.0,
               abs((coup or 0.0) * 1.5),
               (am["coarse_half_width_deg"] / abs((coup or 1.0) * 1.5))))
        add("")
        add("## 3d. The two open majors from the previous round, answered here")
        add("")
        add("**Major 1, byte binding.** The reviewer now holds read-only tools, so it measures "
            "this file's hash itself instead of accepting one, and the harness measures the "
            "same bytes and records both values in the verdict. The remaining gap is ordering, "
            "not trust: the verifier round that binds these bytes can only run after they "
            "exist, so section 8 quotes an earlier round and states plainly that it read an "
            "earlier dossier. " + code("o0_make_go.py") + " now refuses a GO unless a fresh "
            "round exists that reports " + code("O0_BYTES_BOUND_MECHANICALLY") + " with zero "
            "failures, was created after this file's mtime, recorded this file's sha256 and "
            "byte count, is archived under " + code("a5_support/binding_history/") + ", and "
            "agrees with the receipt and the verdict. That is a code path, not a promise, so "
            "the correct action is to require the fresh round rather than to accept prose.")
        add("")
        add("**Major 2, how strong is the alpha margin.** The previous round was judged on 3 "
            "readable polars. This round the statistic is rebuilt over every real run root "
            "(R2, G1, G2, P1, P2): %d roots searched, %d unique 12D designs with a locatable "
            "root, %d design(s) excluded because the root lies outside the measured alpha span "
            "and listed rather than extrapolated, %d case(s) skipped with a recorded reason. The "
            "tolerance-window geometry (a 1e-3 lift tolerance is about 0.0052 deg of alpha, so a "
            "0.004 deg step puts at least 3 real rows inside it) and the coupling bound above "
            "are what the protocol relies on; both are recomputed from raw polars and both are "
            "reproducible offline. The honest limit stays stated: 7 designs from one M202 family "
            "is not a sample over the O0 subspace, and a design whose root misses the 0.024 deg "
            "window records objective=None while still paying its 2 starts."
            % (am["n_run_roots_searched"], am["n_unique_designs"],
               len(am["outside_span"]), len(am["skipped"])))
        add("")
        add("## 4. O0: the real feedback optimization protocol")
        add("")
        add("- Task %s at Mach 2.02, altitude 18288 m, L_ref 1333704.4 N, tolerance 1e-03; "
            "objective Di_N = q*Sref*CDi of an admitted raw polar row."
            % code("O0-M202"))
        add("- Free variables %s and %s inside %s. Every other variable is held at its frozen "
            "baseline; check_design() raises if anything else moves."
            % (code("sweep_1"), code("sweep_2"),
               code(json.dumps(pre["search_space"]["bounds"]))))
        add("- Bootstrap: LHS on the frozen box, baseline forced first.")
        add("- Adaptive backend %s, max %d adaptive attempts."
            % (code("RECOVERY_NUMPY_RBF_GP_EI_V1"),
               pre["search_space"]["adaptive"]["max_adaptive_attempts"]))
        add("- One design evaluation costs exactly 2 charged starts: 7-point coarse bracket "
            "around 5.18 deg (spans 2.1 deg), then 13-point refinement centred on the coarse "
            "quadratic CL(alpha) root, plus minus 0.024 deg at 0.004 deg resolution.")
        add("- Internal alpha cases per design: exactly 20 (7 coarse + 13 refine), equal to the "
            "20 cap rather than merely under it.")
        add("- Caps as stored in the code: %s."
            % code(json.dumps(pre["caps"], sort_keys=True)))
        add("- How those caps interact, stated once: the design cap (%d) times the exact "
            "per-design cost (2 starts, 20 internal cases) gives a spendable ceiling of %d "
            "starts and %d internal cases. The stored %d-start cap is strictly inert (%d < "
            "%d), so it is not budget and is never quoted as remaining budget. The stored "
            "%d-internal cap is not inert: it equals the spendable ceiling exactly (%d = %d), "
            "so the design cap and the internal cap bind together and confirm each other. No "
            "number in this list is a remainder; remainders appear only in the carry-forward "
            "paragraph below."
            % (ceil_designs, spendable_starts, spendable_internal,
               pre["caps"]["max_solver_starts"], spendable_starts,
               pre["caps"]["max_solver_starts"], pre["caps"]["max_internal_cases"],
               spendable_internal, pre["caps"]["max_internal_cases"]))
        add("- After the carry-forward: %d start and %d internal cases already paid for, so at "
            "most %d further designs, %d further starts and %d further internal cases remain. "
            "Every number in this document is a spendable total unless the sentence says "
            "\"further\"." 
            % (prior["solver_starts"], prior["internal_solver_cases"], designs_left,
               further_starts, further_internal))
        if designs_left == 0:
            add("- The optimizer cap is now exhausted: no further design may be proposed under "
                "this authorization, so the optimizer batch cannot run again even though a "
                "residual %d start and %d internal case are arithmetically unspent (a start "
                "cannot be spent without a design to spend it on). The only physics still asked "
                "for is the separate O0-FINAL verification budget in section 4b."
                % (further_starts, further_internal))
        add("")
        add("**Per-design cost is an exact invariant, not an upper bound.** "
            + code("o0_short_bo.assert_execution_contract()") + " asserts that "
            "max_starts_per_design equals 2 and that the alpha plan agrees, and "
            "AttemptLedger.charge() rejects any charge that would take one design past 2 starts "
            "or 20 internal cases, so a third start on the same design is architecturally "
            "impossible rather than merely discouraged. An earlier revision carried the generic "
            "Issue-#15 wording of 3 starts per design while the evaluator spends exactly 2; that "
            "inconsistency is fixed at the cap, not by loosening the evaluator.")
        add("")
        add("**What the attempt numbers count.** max_design_attempts=12, bootstrap_attempts=4 and "
            "max_adaptive_attempts=8 all count distinct designs. None of them authorizes solving "
            "one design twice: bootstrap designs are LHS with duplicates rejected, and the GP "
            "backend refuses a duplicate observation, so re-evaluating a design already in the "
            "table raises instead of consuming budget. A repeat would also cost 2 new starts, "
            "which the per-design cap forbids.")
        add("")
        add("**Serial and retry-free by assertion.** parallelism=1 and retries=0 are enforced "
            "values inside that same assertion, not prose in this document: any other value "
            "raises ProtocolError before the first start, and the runner calls the assertion "
            "before it validates the GO record.")
        add("")
        add("**Why the coarse bracket is 2.1 deg wide.** The fixed-lift alpha moves about %.2f "
            "deg per degree of sweep_1 on the measured M202 polars (section 3c), so across the "
            "+-1.5 deg search box the target can move by at most about %.2f deg; a plus minus "
            "1.05 deg bracket around the baseline alpha keeps every measured root inside with "
            "%.2f deg of margin. A coarse quadratic fit on 7 rows across 2.1 deg then predicts "
            "the root inside the 0.024 deg refinement window, which at 0.004 deg resolution puts "
            "at least %d raw rows inside the 1e-3 lift tolerance."
            % (coup if coup is not None else 0.0, abs((coup or 0.0) * 1.5),
               am["coarse_coverage_margin_deg"],
               am["min_rows_guaranteed_inside_tolerance_window"]))
        add("")
        add("**Tolerance is not relaxed and no interpolation is promoted.** A design whose "
            "refined polar contains no actual row inside 1e-3 is recorded as a failure with "
            "objective=None; it still pays both starts and all 20 internal cases.")
        add("")
        streak_cap = pre["caps"]["max_consecutive_unadmitted_designs"]
        add(("**A missed refinement window cannot silently eat the whole budget.** A design "
             "that misses the refinement window still pays its 2 starts, so 12 such designs "
             "could spend 24 starts, zero of them useful, with zero admitted rows. The stop "
             "rule is code, not prose: "
             + code("CAPS[\"max_consecutive_unadmitted_designs\"]")
             + " = %d, and run_bo_loop() counts any design that ends with objective=None and "
             "breaks out with budget deliberately unspent once %d consecutive designs have "
             "failed to admit a raw row. That is %d charged starts -- %d designs times the exact 2 "
             "starts per design -- plus an explicit "
             % (streak_cap, streak_cap, 2 * streak_cap, streak_cap))
            + code("stopped_by_unadmitted_streak") + " reason in the result, not 12 misses. "
            "assert_execution_contract() refuses a value that would not bite before the design "
            "cap.")
        add("")
        add("Stop conditions: the baseline design (bootstrap design 0) fails: the batch aborts at "
            "once and the remaining budget is not spent, because a baseline failure means the "
            "protocol rather than the aerodynamics is broken; %d consecutive designs with no "
            "admitted raw row (added this round, and it is the answer to the budget-drain "
            "objection); any spendable limit reached, which after the final batch means %d "
            "further designs, %d further starts or %d further internal cases (the stored 36-start "
            "ceiling is unreachable and the stored 240-internal ceiling is the same number as the "
            "design-derived one); two consecutive designs with no solver result at all; wall "
            "clock %d s; any accounting inconsistency (ledger charge rejected); upload and remote "
            "readback after every 8 starts or 60 minutes, before continuing."
            % (streak_cap, designs_left, further_starts, further_internal,
               pre["caps"]["wall_clock_s"]))
    add("")
    sep = pre["o0_final"]["separate_budget"]
    bud_starts = int(sep["verification_starts_max"])
    bud_internal = int(sep["verification_internal_cases_max"])
    bud_probes = int(sep["wake_probe_starts_max"])
    bud_rep_per_design = int(sep["max_repeat_runs_per_design"])
    bud_refine = int(sep["refinement_points"])
    bud_nodes_ref = int(sep["n_wake_nodes_reference"])
    bud_nodes_probe = int(sep["n_wake_nodes_probe"])
    bud_void = int(sep.get("void_rows_max") or 0)
    rep_runs = 2 * bud_rep_per_design
    rep_internal = rep_runs * bud_refine
    probe_internal = bud_probes * bud_refine
    void_internal = bud_void * bud_refine
    repair = pre["o0_final"].get("repair_of_the_first_verification_attempt") or {}
    spent_starts = int(repair.get("spent_before_this_pre_registration") or 0)
    spent_internal = int(repair.get("internal_before_this_pre_registration") or 0)
    left_starts = int(repair.get("remaining_to_spend") or 0)
    left_internal = int(repair.get("remaining_internal") or 0)
    add("## 4b. The O0-FINAL verification step: a separate budget, and a separate review")
    add("")
    add("The optimizer batch is not the end of the work. The improvement it reports still has to "
        "survive being measured again by a procedure that cannot choose what to measure. That is "
        "the O0-FINAL step, and it is the one place where a reader could reasonably suspect that "
        "the budget is being quietly extended, so it is written out here with its arithmetic "
        "instead of being left to the summary line.")
    add("")
    add("- **What is re-measured.** Exactly two designs: the frozen baseline, and the admitted "
        "non-baseline design with the lowest Di_N in the closed batch. Both are re-solved from "
        "scratch with new case ids in fresh empty directories, in the same frozen configuration, "
        "%d times each. The improvement is then the difference between two independently "
        "measured pairs rather than one optimistic number." % bud_rep_per_design)
    add("- **Pre-registered budget.** These numbers are already frozen in "
        + code("o0_preregistration.json") + " under " + code("o0_final.separate_budget") +
        " before a single verification start is spent: %d verification starts, %d internal alpha "
        "cases, at most %d repeat runs per design, %d wake probes, wake nodes %d for the "
        "reference mesh against %d for the probe, and %d refinement points per case."
        % (bud_starts, bud_internal, bud_rep_per_design, bud_probes, bud_nodes_ref,
           bud_nodes_probe, bud_refine))
    add(("- **Itemization, so the total cannot be taken on faith.** The budget is gross: it "
         "covers the three starts the crashed first attempt already spent as well as the five that "
         "remain. %d void rows x %d refinement points = %d internal cases (already spent, never "
         "admissible, never re-run), plus %d wake probes x %d = %d internal cases (one of which, "
         "the baseline probe, is already spent and complete on disk), plus %d repeat runs x %d = "
         "%d internal cases still to spend. That is %d + %d + %d = %d internal cases and %d + %d + "
         "%d = %d starts, of which %d starts / %d internal cases are already spent and %d starts / "
         "%d internal cases remain. The runner does not trust these numbers: it reads them from the "
         "pre-registration and exits with BUDGET_NOT_PRE_REGISTERED if a key is missing or with "
         "BUDGET_MISMATCH if a value disagrees with its own code."
         % (bud_void, bud_refine, void_internal, bud_probes, bud_refine, probe_internal,
            rep_runs, bud_refine, rep_internal,
            void_internal, probe_internal, rep_internal,
            void_internal + probe_internal + rep_internal,
            bud_void, bud_probes, rep_runs, bud_void + bud_probes + rep_runs,
            spent_starts, spent_internal, left_starts, left_internal)))
    add("- **Why this is not extra optimizer budget.** Verification cannot propose a design and "
        "cannot admit one. It re-measures two designs that were already selected and already paid "
        "for, and the wake probe is never admitted at all, because the admission mesh is fixed at "
        "%d wake nodes and the probe is deliberately solved on %d. The optimizer caps are spent "
        "and stay spent; nothing here can spend them again."
        % (bud_nodes_ref, bud_nodes_probe))
    add("- **Why it needs its own review and its own GO.** " + code("o0_preregistration.json") +
        " records " + code("requires_its_own_a5_review: true") + " and " +
        code("requires_its_own_go: true") + "; the GO file is " + code("o0_final_go_record.json") +
        " with authorization kind " + code("O0_FINAL_VERIFICATION") + "; and " +
        code("scripts/o0_final.py") + " refuses to move without it. That gate checks the verdict, "
        "the dossier hash, the pre-registration hash, a fresh mechanical binding round, the eight "
        "pre-registered budget numbers one by one, the verification ledger that shows what the "
        "crashed first attempt already spent, and the two design identities it is allowed to "
        "re-measure. A verdict on the optimizer protocol is therefore not a verdict on this step, "
        "which is why section 7 asks for both.")
    add("- **What counts as a start, and what does not.** A case directory is not a start. " +
        code("scripts/o0_eval.py") + " creates a case directory with " + code("plan.json") + ", " +
        code("approval.json") + ", " + code("task_spec.json") + ", the geometry files and the "
        "case inputs before anything is solved, so a directory can exist while zero solver starts "
        "have happened. A start is counted only when there is a " + code(".polar") + " file and a " +
        code("case_result.json") + " with " + code("physical_solver_starts = 1") + ", or when the "
        "ledger charges it before the spawn. The directories under " + code("cases/O0F/") + " that "
        "hold preparation files and no polar are therefore preflight output, not spend; " +
        code("scripts/_preflight_inventory.py") + " prints the file count, the byte count and the "
        "polar count of each one so the distinction is checkable rather than asserted.")
    add("- **Why the ledger is a file and not a counter in memory.** " +
        code("o0_final/verification_ledger.json") + " is read back when the runner starts and "
        "written after every charge, so a crash between two starts cannot zero the bill, and a "
        "label that has already been charged cannot be charged a second time, so a re-run cannot "
        "be smuggled in as a fresh case.")
    add("")
    add("### 4c. The first attempt at this step crashed, and what that cost")
    add("")
    add("This is disclosed here because a verification budget that grew from six starts to eight "
        "without the crash being stated, and without the three starts it cost being charged, would "
        "be exactly the kind of thing this dossier exists to make impossible to hide. The growth is "
        "therefore stated with its cause, its cost and its evidence.")
    add("")
    add("- **What happened.** The first attempt died on its third start with " +
        code("wake probe cap exceeded: 2 rows") + ". The two rows it had already charged were the "
        "baseline repeats, and they had been charged as " + code("kind=wake") + " because the "
        "runner derived the kind from the wake count and gave every repeat two wake nodes instead "
        "of the admission mesh of eight. With " + code("max_wake_probe_starts = 2") + ", the third "
        "charge was refused while the third solver run was already running.")
    add("- **What it actually cost.** Three real solver starts and %d internal alpha cases: "
        "two baseline repeats at two wake nodes, plus one baseline probe at sixteen wake nodes that "
        "completed with its polar and " % spent_internal +
        code("case_result.json") + " still on the disk. The two wake-node-two cases are void: their "
        "polar output is real, but the mesh is not the admitted mesh, so they can never be admitted "
        "and they must never be re-run under those labels.")
    add("- **What was wrong with the ledger, and not just with the code.** The ledger recorded two "
        "starts and 26 internal cases, both mislabelled, and it was missing the third start "
        "entirely, because the charge happened after the run instead of before it. A crash "
        "therefore destroyed a paid start rather than billing it. The repair is in the ordering, "
        "not in the arithmetic: the charge is now made before the solver is spawned, a crash after "
        "a charge writes a record beside the ledger, and the kind is a plan field that is never "
        "inferred from a number.")
    add("- **How the ledger was repaired.** " + code("scripts/o0_repair_ledger.py") + " re-reads "
        "the three case directories, checks the sha256 of each polar and each " +
        code("case_result.json") + ", and rewrites the ledger with three rows carrying that "
        "evidence: two " + code("void") + " rows for the mis-configured repeats and one " +
        code("wake") + " row for the completed probe. The pre-repair ledger is preserved inside the "
        "repaired file under " + code("repair") + ", including its own sha256, so the correction is "
        "auditable rather than invisible.")
    add("- **What the repair does not do.** It does not re-classify a paid start as unspent, it does "
        "not re-run any case that already produced paid output, it does not spend a start, and it "
        "does not widen an optimizer cap. The five remaining starts and %d remaining internal cases "
        "are what a GO can authorize; the runner reads the ledger back and the cap arithmetic "
        "happens there, not in this paragraph." % left_internal)
    add("- **Why this is inside the owner's limit.** The owner's acceptance note allows a first "
        "verification batch of at most twelve real solver starts. The gross verification spend "
        "here is %d starts, and the three already spent are disclosed rather than recycled, so the "
        "replacement batch stays well inside that limit without pretending the crash was free."
        % bud_starts)
    add("")
    add("### 4d. The second attempt spent nothing, and that is stated too")
    add("")
    add("A disclosure section that only reports the crashes that cost money would be a selection of "
        "the convenient ones, so the run that died for free is recorded as well.")
    attempts_free = (pre.get("o0_final", {}).get("repair_of_the_first_verification_attempt", {})
                     .get("attempts_that_spent_nothing") or [])
    for item in attempts_free:
        add("- **What happened.** " + item["what_happened"] + ".")
        add("- **Root cause.** " + item["root_cause"] + ".")
        add("- **What it cost.** " + item["what_it_cost"] + ".")
        add("- **How it is closed.** " + item["how_it_is_closed"] + ".")
        add("- **How it is prevented from recurring.** " + item["how_it_is_prevented_from_recurring"] +
            ".")
    add("")
    add("- **The four verdicts are pre-registered strings and none of them is PASS:** " +
        ", ".join(code(v) for v in pre["o0_final"]["verdicts"]) + ".")
    add("")
    if close is not None:
        close_path = CLOSE_RECORDS[-1]
        impro = float(close.get("improvement_n") or 0.0)
        frac = float(close.get("improvement_fraction_of_baseline") or 0.0)
        add("**The optimizer batch this step would verify, already closed and disclosed.** Batch "
            "%s closed with outcome %s, and no cap was exceeded (%s). The batch ended with an "
            "exception that reads like a crash and is not one: the adaptive loop asked for a %dth "
            "design after the %d-design cap was already fully spent, and the ledger refused, which "
            "is the ledger doing its job. The loop bound is fixed by subtracting the carried-forward "
            "designs; the fix changes code that is listed in section 1."
            % (code(str(close.get("batch_id") or "B02")), code(str(close.get("outcome"))),
               code("was_any_cap_exceeded=%s" % str(close.get("was_any_cap_exceeded")).lower()),
               ceil_designs + 1, ceil_designs))
        add("")
        add("The measured improvement, before any verification: baseline Di_N %.2f N, best admitted "
            "non-baseline Di_N %.2f N, difference **%.2f N**, which is %.4f%% of the baseline. That "
            "is a small effect and it is reported as small. Whether it survives re-measurement is "
            "exactly what O0-FINAL is for, and it is why the verdict it can produce is one of four "
            "strings rather than a success flag."
            % (float((close.get("baseline") or {}).get("di_n") or 0.0),
               float((close.get("best_non_baseline") or {}).get("di_n") or 0.0), impro,
               100.0 * frac))
        add("")
        add("Closure record: %s (sha256 %s, %d bytes)." % (code(close_path.name),
                                                          code(sha_file(close_path)),
                                                          close_path.stat().st_size))
    else:
        add("**The optimizer batch is not closed yet**, so this section cannot name the two designs "
            "the verification step would re-measure. " + code("scripts/o0_final.py") + " refuses to "
            "run when no " + code("o0_batch_close_*.json") + " exists, so the verification budget "
            "cannot be spent without a closed batch behind it.")
    add("")
    add("## 5. Accounting and resource instrumentation")
    add("")
    add("- " + code("AttemptLedger.settle()") + " is the only writer of the run counters. It adopts "
        "what the evaluator reports and routes it through " + code("charge()") + ", which raises if "
        "any per-design or per-run cap would be exceeded, so an over-spending evaluator fails "
        "closed instead of overspending.")
    add("- Six quantities are reported per batch: physical starts, internal alpha cases, charged "
        "starts, planned or reserved starts, design evaluations, cached reads.")
    add("- Batch spend and authorization spend are reported separately, and only the authorization "
        "total is comparable with the caps. The batch accounting file carries " +
        code("carried_forward") + " with the records it was read from, so a restarted batch cannot "
        "be mistaken for a fresh authorization.")
    add("- **The carry-forward is counted once, by one rule, from one file.** " +
        code("scripts/o0_spend.py") + " is the only place that decides this. An abort record "
        "reports batch-local numbers; a crash record's ledger summary is authorization-cumulative "
        "and already includes what it carried forward. Summing the two would print %d starts for "
        "the %d that were actually spent, so the module takes the newest cumulative record as the "
        "floor and only adds a batch-local record that the floor cannot already contain. The "
        "counting rule it applied is quoted verbatim in the receipt."
        % (prior["solver_starts"] + 1, prior["solver_starts"]))
    add("- **The failure mode that produced the abort in section 0b is now a settled charge, not a "
        "silent loss.** " + code("AttemptLedger.settle()") + " runs even when the evaluator raises, "
        "and a charge that would breach a cap keeps the original exception while restoring the "
        "declared amounts into the abort record, so a crash preserves the bill instead of erasing "
        "it.")
    add("- CPU and memory are sampled during the optimization by the resource monitor: host-wide CPU "
        "busy fraction, physical memory load, and the tracked working set of the python and "
        "vspaero processes. It is pure " + code("ctypes") + " because " + code("psutil") +
        " is not installed, and a write failure is reported rather than raised, so monitoring "
        "cannot take the batch down.")
    add("")
    add("## 6. What this dossier does NOT authorize")
    add("")
    add("- No solver start before a separate A5 verdict on these exact bytes and a Lead GO record "
        "whose hashes match the files above.")
    add("- O1 warm-start arms are not authorized. They need their own pre-registration, their own "
        "review and their own GO.")
    add("- The O0-FINAL verification starts in section 4b are not authorized by the optimizer GO. "
        "They need their own verdict and their own " + code("o0_final_go_record.json") + ".")
    add("- Lift tolerance, target lift, reference quantities and mesh standard are frozen. Changing "
        "any of them to manufacture an improvement is out of scope, and a row that is interpolated "
        "rather than sampled is never admitted.")
    add("- Earlier approval adapters are not used, and no old authorization id and no old GO record "
        "is reused. A GO is bound to one batch id and one set of bytes.")
    add("- No new design can be proposed after the optimizer caps are spent. The remaining physical "
        "budget in this issue is the O0-FINAL verification budget in section 4b and nothing else.")
    add("- " + code("physics_validated") + " stays " + code("false") + " and " +
        code("fuel_burn_kg") + " stays " + code("null") + ". This is a lifting-surface VSPAERO "
        "internal-only objective, not a mission-level result.")
    add("")
    add("## 7. Requested verdict")
    add("")
    if designs_left == 0 and close:
        add("**First, the optimizer batch that already ran.** No further optimizer batch is "
            "requested: the authorization's design cap is exhausted, so this section asks whether "
            "what already happened is properly stated. The binding limits were: at most %d design "
            "attempts, exactly %d solver starts and exactly %d internal alpha cases per design, "
            "which means at most %d starts and %d internal cases could ever be spent because the "
            "design cap binds first; tolerance 1e-3 never relaxed and no interpolated row admitted; "
            "zero retries and parallelism 1 asserted by the same check rather than promised in "
            "prose." % (ceil_designs, per_design_starts, per_design_internal, spendable_starts,
                        spendable_internal))
        add("")
        add("Measured against those limits, the closed batch itself spent **%d designs, %d "
            "starts and %d internal cases**, of which %d admitted raw rows and %d failed or null; "
            "improvement of the best non-baseline design over the re-measured baseline is %.1f N "
            "(%.3f%%). Both designs are re-measured independently in section 4b before any "
            "improvement is called verified."
            % (int(close["batch_spend"]["designs"]), int(close["batch_spend"]["solver_starts"]),
               int(close["batch_spend"]["internal_cases"]),
               int(close["batch_spend"]["admitted_labels"]),
               int(close["batch_spend"]["failed_or_null"]),
               float(close["improvement_n"]),
               100.0 * float(close["improvement_fraction_of_baseline"])))
        add("")
        add("Two different totals appear in this dossier on purpose, and neither is a typo. The "
            "**batch-local** spend of the closed optimizer batch is %d designs / %d starts / %d "
            "internal cases. The **authorization-cumulative** spend is %d designs / %d starts / %d "
            "internal cases, because the earlier batch that crashed (section 0b) had already "
            "charged %d design / %d start / %d internal case before it died. The difference is "
            "exactly that aborted attempt: %d design, %d start and %d internal case. Whenever this "
            "document says \"paid so far\" it means the cumulative number, because that is the "
            "number a reader needs in order to know what the authorization has actually cost."
            % (int(close["batch_spend"]["designs"]), int(close["batch_spend"]["solver_starts"]),
               int(close["batch_spend"]["internal_cases"]),
               prior["design_attempts"], prior["solver_starts"], prior["internal_solver_cases"],
               prior["design_attempts"] - int(close["batch_spend"]["designs"]),
               prior["solver_starts"] - int(close["batch_spend"]["solver_starts"]),
               prior["internal_solver_cases"] - int(close["batch_spend"]["internal_cases"]),
               prior["design_attempts"] - int(close["batch_spend"]["designs"]),
               prior["solver_starts"] - int(close["batch_spend"]["solver_starts"]),
               prior["internal_solver_cases"] - int(close["batch_spend"]["internal_cases"])))
    else:
        add("**First, the optimizer protocol.** Decide whether the H0 contract, the A0 ablation and "
            "the O0 protocol above are fit to authorize a fresh limited optimizer batch. The "
            "binding limits are: at most %d design attempts, exactly %d solver starts and exactly "
            "%d internal alpha cases per design, which means at most %d starts and %d internal "
            "cases can ever be spent because the design cap binds first; tolerance 1e-3 never "
            "relaxed and no interpolated row admitted; zero retries and parallelism 1 asserted by "
            "the same check rather than promised in prose."
            % (ceil_designs, per_design_starts, per_design_internal, spendable_starts,
               spendable_internal))
    add("")
    if designs_left == 0:
        add("The carry-forward, derived from the records on disk and not from prose: %d start and "
            "%d internal case(s) are already paid for out of %d spendable starts and %d spendable "
            "internal cases, against %d design attempts out of %d. That leaves %d further starts "
            "and %d further internal cases arithmetically, but %d further design attempts -- and "
            "a start or an internal case cannot be spent without a design to spend it on. The "
            "residue is stranded, not available: no optimizer spend remains, and the only physics "
            "still requested is the separate verification budget in section 4b."
            % (prior["solver_starts"], prior["internal_solver_cases"], spendable_starts,
               spendable_internal, prior["design_attempts"], ceil_designs, further_starts,
               further_internal, designs_left))
    else:
        add("The carry-forward, derived from the records on disk and not from prose: %d start and "
            "%d internal case(s) are already paid for, so at most %d further starts (%d spendable "
            "minus %d) and %d further internal cases (%d minus %d) remain, and at most %d further "
            "design attempts (%d minus %d already spent). %d designs x %d internal = %d, so the "
            "internal remainder agrees with the design remainder and neither number was typed by "
            "hand."
            % (prior["solver_starts"], prior["internal_solver_cases"], further_starts,
               spendable_starts, prior["solver_starts"], further_internal, spendable_internal,
               prior["internal_solver_cases"], designs_left, ceil_designs,
               prior["design_attempts"], designs_left, per_design_internal, needed_internal))
    add("")
    add("This asks for a verdict on the executed protocol, its accounting and the carry-forward, "
        "not on a reset budget.")
    add("")
    add("**Second, the O0-FINAL verification budget.** Decide whether the separate, "
        "pre-registered verification step in section 4b is fit to authorize its own %d starts and "
        "%d internal cases: the itemization above, the rule that picks the two designs, the "
        "requirement of a fresh binding round and a separate GO, the ledger that survives a crash, "
        "and the refusal to admit a wake probe. These starts are spent after the optimizer batch is "
        "closed; they cannot be folded into an optimizer cap, and the optimizer cap cannot be "
        "reopened to pay for them." % (bud_starts, bud_internal))
    add("")
    add("**What this dossier does not ask for.** It does not ask for a verdict on O1, on mission-level "
        "physics, or on any number that would require trusting a value this document states about "
        "itself.")
    add("")
    add("## 8. How this document's own hash becomes checkable, in two rounds")
    add("")
    add("A single file cannot state its own sha256. This section therefore anchors the binding in "
        "the archived output of the mechanical verifier and states exactly what the next round must "
        "produce, so a reviewer can require it as a condition instead of trusting prose.")
    add("")
    if passing:
        anchor_path, anchor = passing[-1]
        add("Round N-1, archived and hashable at %s:" % code(anchor_path.name))
        add("")
        add("~~~")
        add("verifier sha256    : %s" % sha_file(anchor_path))
        add("status             : %s" % anchor.get("status"))
        add("check_count        : %s" % anchor.get("check_count"))
        add("failure_count      : %s" % anchor.get("failure_count"))
        add("problems           : %s" % json.dumps(anchor.get("problems") or []))
        add("dossier it read    : %s" % (anchor.get("dossier") or {}).get("sha256"))
        add("dossier bytes      : %s" % (anchor.get("dossier") or {}).get("bytes"))
        add("archived at        : %s" % code(str(anchor_path)))
        add("~~~")
    else:
        add("**No clean round is archived yet.** That is a disclosure, not a gate: the round that "
            "binds these bytes cannot exist before these bytes do.")
    add("")
    add("That round reads an **earlier** dossier than the one you are reading. It proves the "
        "procedure is mechanical and has completed at least once; it does not prove anything about "
        "these bytes. The round that covers these bytes does not exist yet and is a hard "
        "precondition of the GO.")
    add("")
    add("Round N, which the GO depends on, happens after these bytes exist: " +
        code("scripts/o0_verify_binding.py") + " re-reads them off disk, hashes them, recomputes "
        "every other hash in the chain, and writes " + code("o0_binding_verification.json") +
        " plus an immutable copy under " + code("a5_support/binding_history/") + ". Both GO "
        "writers refuse to issue a GO unless that fresh round reports " +
        code("O0_BYTES_BOUND_MECHANICALLY") + " with zero failures, was created after this file's "
        "mtime, recorded exactly this file's sha256 and byte count, is archived, and agrees with "
        "the receipt and with verdict.dossier_sha256. So the verdict can be made conditional on an "
        "artifact that does not exist yet, and the condition is enforced by code rather than by "
        "trust.")
    add("")
    add("**What that buys, and what it does not.** It buys a mechanically enforced binding that has "
        "passed at least once, whose output is archived where it cannot be overwritten, and which "
        "is a hard precondition of both GO records. It does not buy an independent measurement of "
        "the current bytes by the reviewer beyond what its own read-only tools can hash. Section 0 "
        "says so rather than hiding it.")
    add("")

    payload = ("\n".join(lines) + "\n").encode("utf-8")
    OUT.write_bytes(payload)
    pre_path = RUN / "o0_preregistration.json"
    receipt = {
        "schema": "dreal005.o0_dossier_receipt.v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dossier": {"path": str(OUT), "sha256": hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload), "chars": len(payload.decode("utf-8"))},
        "preregistration": {"path": str(pre_path), "sha256": sha_file(pre_path)},
        "code_shas_sha256": hashlib.sha256(
            json.dumps(pre["code_shas"], sort_keys=True).encode("utf-8")).hexdigest(),
        "physical_solver_starts_actual": prior["solver_starts"],
        "internal_solver_cases_actual": prior["internal_solver_cases"],
        "carried_forward": prior,
        "counting_rule": prior["counting_rule"],
        "basis_record": prior["basis_record"],
        "o0_final_budget": {"verification_starts": bud_starts,
                            "verification_internal_cases": bud_internal,
                            "wake_probe_starts": bud_probes},
        "sections": [ln[3:].strip() for ln in lines if ln.startswith("## ")],
        "note_physical": ("non-zero on purpose: this receipt reports measured spend under the "
                          "authorization, including the one charged start from the aborted first "
                          "attempt documented in section 0b, and not the intent of the next batch"),
    }
    RECEIPT.write_bytes((json.dumps(receipt, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print("dossier  %s  %s  %d bytes" % (str(OUT), receipt["dossier"]["sha256"], len(payload)))
    print("receipt  %s  %s" % (str(RECEIPT), receipt["created_utc"]))
    print("prior    %d designs / %d starts / %d internal"
          % (prior["design_attempts"], prior["solver_starts"], prior["internal_solver_cases"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
