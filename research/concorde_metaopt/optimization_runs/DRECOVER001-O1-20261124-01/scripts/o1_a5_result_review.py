"""A5 independent review of the O1 *results* (not the protocol), with read-only local tools.

Reuses the transport and the five read-only tools from o1_a5_review_tools.py so the reviewer
sees exactly the same allowlist discipline as the protocol round. Writes its own verdict to
a5_result_review/ and never touches a5_review/.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import o1_a5_review_tools as H  # noqa: E402

RUN = H.RUN
DOSSIER = RUN / "o1_a5_result_dossier.md"
OUT = RUN / "a5_result_review"
OUT.mkdir(parents=True, exist_ok=True)
MODEL = H.MODEL
MAX_HOPS = 30
TOOL_HOPS = MAX_HOPS - 2

GATES = [
    "R1_SPEND_MATCHES_THE_GO_AND_EVERY_START_IS_IN_THE_LEDGER",
    "R2_THE_THREE_ARMS_GOT_IDENTICAL_BUDGETS",
    "R3_PRIMARY_ENDPOINT_ARITHMETIC_IS_CORRECT",
    "R4_ARMS_DIFFER_ONLY_IN_THE_WARM_START_RULE",
    "R5_A4_RECOMPUTATION_IS_INDEPENDENT_OF_THE_RESULT_FILE",
    "R6_CLAIMS_ARE_BOUNDED_BY_THE_DATA",
    "R7_EVERY_CLAIMED_ARTEFACT_EXISTS_AND_IS_RETRIEVABLE",
    "R8_THE_LEDGER_HAS_NO_UNACCOUNTED_CASE",
]
gate_json = ",".join('"%s":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL"' % g for g in GATES)


def build_prompt(now):
    dossier = DOSSIER.read_text(encoding="utf-8")
    return """You are A5, an independent read-only reviewer. This round reviews the RESULTS of the O1 three-arm batch (a completed, paid, real VSPAERO run), not its protocol: the protocol round already passed and its verdict and GO are cited in the dossier. You DO have read-only tools: sha256_file, stat_file, list_dir, read_text, grep. They are scoped to the O1 run root D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01, the frozen worktree D:/RCAIDE/.worktrees/dreal005-20261124, the A0 run root D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01 and the O0 run root D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01. They cannot write anything. Measure rather than trust: hash the dossier and the result files listed in section 0; open o1_arm_<ARM>.json and check that each arm's best_feasible_di_n really is the minimum of that arm's own anytime di_n sequence; check that the three arms report the same designs/starts/internal counts; re-do the target arithmetic baseline*(1-0.001) yourself; open o1_cost_reconciliation.json and judge whether the reported-versus-contract difference is disclosed and whether it flatters any arm; count the case directories and classify them the way section 7 does: 36 paid case directories (18 coarse + 18 refine) each hold a .polar and a case_result.json, the admission_certificate.json is one per DESIGN and therefore lives only in the refine directories, and the 4 preflight/dry-run directories hold no .polar and no case_result.json because they spent nothing; check upload_receipt.json's readback counts against the packaged counts; check that o1_result.json's not_claimed list really covers the limitations the dossier admits. Do not invent file contents; if a tool returns an error, record it. Do not sign as a human. Section 0b states how the previous result-level review round's three substantive findings were handled; judge whether each was actually addressed in the text on disk, and say so — a claim that a finding was fixed is not evidence that it was. Note also that section 1 explains why this result dossier's hash necessarily differs from the hash bound by the protocol-level verdict: there are two different dossiers (protocol and result), so a hash difference between them is expected and is not byte drift.

The current UTC timestamp is """ + now + """; use it for reviewed_utc and do not discuss or question dates.

Return ONLY one valid compact JSON object, no markdown, ending with }:
{"reviewer":"deepseek-v4.1-flash","review_type":"independent_read_only_result_review","reviewed_utc":"YYYY-MM-DDTHH:MM:SSZ","dossier_sha256":"<sha256 you measured>","verdict":"O1_RESULT_REVIEW_PASS"|"O1_RESULT_REVIEW_CHANGES_REQUIRED"|"O1_RESULT_REVIEW_REJECT","gate_verdicts":{""" + gate_json + """},"tool_calls_made":["..."],"evidence_checked":["..."],"findings":[{"severity":"critical|major|minor|info","finding":"...","evidence":"..."}],"limitations":["..."],"scope":"...","signature":"deepseek-v4.1-flash independent A5 result review with read-only local tools; not a human signature"}

What each gate means:

R1 asks whether the money and the ledger agree: the GO authorises 24 designs / 48 equivalent starts / 480 internal over three arms, the batch reports 36 physical starts, and the run claims every start is recorded in a case_result.json and in tables/o1_solver_case_ledger.csv. A start that was paid for but is missing from the ledger is a FAIL. A disclosed difference between three cost readings (108 reported, 48 by the preregistered model, 36 physical) is not by itself a FAIL if it is disclosed and if the disclosure does not flatter an arm; an undisclosed or flattering difference is.

R2 asks whether the three arms really received the same budget: 8 designs, 16 equivalent starts and 160 internal cases each, and whether any arm got an extra candidate, an extra label or an extra start.

R3 asks whether the arithmetic is right: baseline 135505.77916651228, target = baseline*(1-0.001) = 135370.27338734578, and each arm's best is the minimum over its own anytime sequence. Note that reaching the target is claimed for all three arms; check when (equivalent starts) each arm first crossed it.

R4 asks whether the arms differ only in the warm-start rule: same three shared support designs, same candidate pool of 256 coordinates with no objective values, same GP backend and hyperparameters, same alpha recipe, same admission gate, same geometry contract. The two K-shot arms converging to literally the same two adaptive designs is an observation to record, not a fairness failure, unless you find a path by which one arm saw another arm's results.

R5 asks whether tables/o1_a4_recompute.json and o1_a4_geometry_identity.json are independent of o1_result.json: the recomputation must recompute Di = q*Sref*CDi from the raw polar and the admission certificate at one remote commit, and the geometry identity must be proved by regenerating the .vspgeom and comparing to the paid case plan, not by re-reading the result file.

R6 asks whether the claims stay inside the data: no claim that MAML beats supervised meta-learning (the two arms tie bit-for-bit at the endpoint and only differ in anytime cost), no claim that the model-ranked warm start beats Sobol on this task (it does not: 2.687% versus 0.813%), no global optimality, no regret, no aerodynamic validation, no "converged" language for a batch that was truncated at a common budget.

R7 asks whether every artefact the dossier names exists on disk with the hash the dossier states, and whether the case-level raw bytes are retrievable from the remote repository (the upload receipt must show a readback with zero missing and zero bad).

R8 asks whether the case ledger has a row for every paid start and every internal case: count the case_result.json files, the coarse and refine stages, and compare with the charged totals.

Section 8 discloses a residual file-level gap: o1_result.json's four-item not_claimed list lacks a no-Sobol-superiority clause, and the clause lives only in o1_not_claimed_addendum.json and in the dossier prose. Judge whether that disclosure is honest and adequate, or whether it is just moving an omission to another file - say which, in your own words, as one of your findings. Also judge for yourself whether o1_result.json's cost.note (which claims the 108 equivalent bill is three times the support block) is wrong as written: the dossier asserts it is wrong, but that assertion is a claim you should check, not accept.

Hard limits: at most 8 findings, each finding and evidence <= 240 characters; at most 6 limitations; scope <= 400 characters. JSON must be complete.

DOSSIER:
""" + dossier


def main() -> int:
    candidates = H.load_token()
    token, domain, vault_file = candidates[0]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dossier_sha = hashlib.sha256(DOSSIER.read_bytes()).hexdigest()
    pre = json.loads((RUN / "o1_preregistration.json").read_text(encoding="utf-8"))

    messages = [
        {"role": "system", "content": "You are a strict independent reviewer with read-only "
                                      "tools. Measure what you can, then output only valid "
                                      "compact JSON."},
        {"role": "user", "content": build_prompt(now)},
    ]
    transcript = []
    final_text = ""
    for hop in range(MAX_HOPS):
        if hop >= TOOL_HOPS:
            messages.append({"role": "user", "content": (
                "Tool budget exhausted at hop %d of %d. Do not call any more tools. "
                "Write the verdict JSON now from the measurements you already made, using "
                "O1_RESULT_REVIEW_CHANGES_REQUIRED if a gate is still unverified, and say in "
                "limitations what you could not finish.") % (hop, MAX_HOPS)})
        text, calls, raw = None, None, None
        for attempt in range(len(candidates) + 1):
            try:
                text, calls, raw = H.stream_once(messages, token, domain)
                break
            except urllib.error.HTTPError as exc:
                body = b""
                try:
                    body = exc.read()[:400]
                except Exception:  # noqa: BLE001
                    pass
                print("  gateway HTTP %d on %s (%s): %r" % (
                    exc.code, Path(vault_file).name, domain, body[:200]), flush=True)
                if exc.code != 429 or attempt >= len(candidates):
                    raise
                token, domain, vault_file = candidates[attempt]
                print("  rotating to %s (%s)" % (Path(vault_file).name, domain), flush=True)
        if text is None:
            raise SystemExit("every vault token is out of quota; no review was produced")
        if hop >= TOOL_HOPS and calls:
            print("  refusing %d tool call(s) in the reserved writing hops" % len(calls), flush=True)
            calls = {}
        transcript.append({"hop": hop, "content": text,
                           "tool_calls": {str(k): v for k, v in calls.items()}})
        print("hop %d content_chars %d tool_calls %d" % (hop, len(text), len(calls)), flush=True)
        (OUT / "o1_result_tool_transcript.json").write_text(
            json.dumps({"dossier_sha256": dossier_sha, "hops": len(transcript),
                        "complete": False, "transcript": transcript},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        if not calls:
            final_text = text
            break
        messages.append({"role": "assistant", "content": text or None,
                         "tool_calls": [{"id": c["id"], "type": "function",
                                         "function": {"name": c["name"],
                                                      "arguments": c["arguments"]}}
                                        for c in calls.values()]})
        for c in calls.values():
            name = c.get("name")
            try:
                args = json.loads(c["arguments"] or "{}")
            except Exception as exc:
                result = {"error": "arguments were not valid JSON: %s" % exc}
                args = {}
            if name not in H.TOOLS:
                result = {"error": "tool %r is not in the allowlist" % name}
            else:
                try:
                    result = H.TOOLS[name](**args)
                except Exception as exc:
                    result = {"error": "%s: %s" % (type(exc).__name__, exc)}
            print("  tool %s %s -> %s" % (name, H.brief(args), H.brief(result)), flush=True)
            transcript[-1].setdefault("results", []).append(
                {"name": name, "arguments": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": c["id"],
                             "content": json.dumps(result, ensure_ascii=False)[:20000]})
    else:
        final_text = transcript[-1].get("content") or ""

    (OUT / "o1_result_tool_transcript.json").write_text(
        json.dumps({"dossier_sha256": dossier_sha, "hops": len(transcript),
                    "complete": True, "transcript": transcript},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    start = final_text.find("{")
    end = final_text.rfind("}")
    if start < 0 or end <= start:
        print("NO_JSON_IN_FINAL_OUTPUT", final_text[-500:])
        return 2
    verdict = json.loads(final_text[start:end + 1])
    measured = verdict.get("dossier_sha256")
    verdict["dossier_sha256"] = dossier_sha
    verdict["dossier_sha256_measured_by_harness"] = dossier_sha
    verdict["dossier_sha256_claimed_by_reviewer"] = measured
    verdict["dossier_sha256_overwritten_because"] = (
        "the reviewer is a language model: the harness hashed the bytes it was shown and "
        "substitutes that measurement, keeping the reviewer's own value for audit")
    verdict["dossier_path"] = str(DOSSIER)
    verdict["result_sha256"] = hashlib.sha256((RUN / "o1_result.json").read_bytes()).hexdigest()
    verdict["preregistration_sha256"] = hashlib.sha256(
        (RUN / "o1_preregistration.json").read_bytes()).hexdigest()
    verdict["go_sha256"] = hashlib.sha256((RUN / "o1_go_record.json").read_bytes()).hexdigest()
    verdict["run_id"] = pre.get("run_id")
    verdict["batch_id"] = pre.get("batch_id")
    verdict["authorization_id"] = pre.get("authorization_id")
    verdict["started_utc"] = now
    verdict["model"] = MODEL
    verdict["review_gateway"] = H.BASE
    verdict["tool_access"] = ("READ_ONLY_LOCAL_TOOLS: sha256_file, stat_file, list_dir, read_text, "
                              "grep; allowlisted to the O1 run root, the frozen worktree, the A0 run "
                              "root and the O0 run root; every call recorded in "
                              "a5_result_review/o1_result_tool_transcript.json")
    verdict["tool_hops"] = len(transcript)
    verdict["human_signature"] = False
    verdict["scope_of_this_review"] = ("O1 three-arm RESULTS of batch "
                                       "DRECOVER001-O1-20261124-01-PAIRING-01 only; NOT a protocol "
                                       "re-review, NOT a human signature, NOT an approval of any "
                                       "later stage.")
    # Round history: a PASS only speaks for the bytes it reviewed, so every round is kept.
    # Each round is written to its own dated file BEFORE the live verdict is replaced; the live
    # verdict is the one a reader should trust, and the dated copies are how a later reader proves
    # which bytes each round actually saw. Without this, a re-run quietly erases the previous
    # round's findings -- which is how a real round's verdict gets lost.
    rounds = OUT / "rounds"
    rounds.mkdir(parents=True, exist_ok=True)
    stamp = now.replace("-", "").replace(":", "")
    body = json.dumps(verdict, ensure_ascii=False, indent=2) + "\n"
    round_file = rounds / ("verdict_%s_%s.json" % (stamp, dossier_sha[:16]))
    round_file.write_text(body, encoding="utf-8", newline="\n")
    verdict["round_record"] = str(round_file)
    (OUT / "verdict.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8", newline="\n")
    (OUT / ("raw_lines_%s.txt" % stamp)).write_text(final_text, encoding="utf-8", newline="\n")
    print(json.dumps({"verdict": verdict.get("verdict"), "dossier_sha256": dossier_sha,
                      "hops": len(transcript), "gates": verdict.get("gate_verdicts")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
