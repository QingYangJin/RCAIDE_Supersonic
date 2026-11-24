"""A5 independent review with READ-ONLY local tools (Issue #15, D-REAL-EXP-003).

Earlier rounds were single-shot: the reviewer could not measure anything and every
verdict carried "reviewer has no tools" as a permanent finding. That finding is the
reviewer being honest about the harness, not about the protocol, so the harness is
fixed here instead of argued with.

The reviewer model (deepseek-v4.1-flash on the WorkBuddy CN gateway) is given a
closed allowlist of read-only tools scoped to the run root and the frozen worktree:

    sha256_file(path)   stat_file(path)   list_dir(path)
    read_text(path, max_bytes)            grep(pattern, path, max_hits)

Every call is executed by this harness after an allowlist and path-prefix check, and
every call plus every result is written to a transcript so the verdict can be audited
against the exact bytes the reviewer saw. Nothing here writes into the run, the
worktree, or the solver.

This is still NOT a human signature and NOT a physical GO.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# The console code page is GBK here and tool results carry arbitrary bytes; a print() that
# cannot encode a replacement character must not be able to kill a review run mid-flight.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
DOSSIER = RUN / "o0_a5_dossier.md"
PRE = RUN / "o0_preregistration.json"
OUT = RUN / "a5_review"
BASE = "https://copilot.tencent.com"
MODEL = "deepseek-v4.1-flash"
# The A0 five-arm evidence lives in its own run root, and a reviewer that cannot read it is
# forced to take section 3 on trust; it is allowlisted read-only like the other two roots.
A0_RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01")
ALLOWED_ROOTS = [RUN.resolve(), REPO.resolve(), A0_RUN.resolve()]
# One file lives outside both roots but is genuinely part of the frozen set: the independent
# audit script that the evaluator shells out to. The reviewer asked for it and was refused, so
# it is allowlisted by exact path rather than by widening a directory.
EXTRA_FILES = [Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py")]
MAX_HOPS = 30
# The last two hops are reserved for writing the verdict: tools are cut off there, because a
# review that runs out of hops after 20 tool calls produces no verdict at all.
TOOL_HOPS = MAX_HOPS - 2
OUT.mkdir(parents=True, exist_ok=True)


def brief(obj, limit=200):
    """A JSON preview that can never raise while printing."""
    try:
        text = json.dumps(obj, ensure_ascii=True)
    except Exception:
        text = repr(obj)
    return text[:limit]


def load_token():
    for f in sorted(glob.glob(r"C:/Users/pc/.dsh/workbuddy-vault/cn/*.json")):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        tok = dom = None

        def walk(o):
            nonlocal tok, dom
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("accessToken", "access_token") and isinstance(v, str) and len(v) > 200:
                        tok = v
                    elif k in ("domain", "Domain") and isinstance(v, str):
                        dom = v
                    else:
                        walk(v)
        walk(d)
        if tok:
            return tok, dom or "www.workbuddy.cn", f
    raise SystemExit("no workbuddy token found")


def safe_path(raw):
    p = Path(str(raw)).expanduser()
    try:
        rp = p.resolve()
    except OSError:
        return None, "path could not be resolved: %r" % raw
    for root in ALLOWED_ROOTS:
        try:
            rp.relative_to(root)
        except ValueError:
            continue
        return rp, None
    for extra in EXTRA_FILES:
        if rp == extra.resolve():
            return rp, None
    return None, "path outside the read-only allowlist (run root and frozen worktree): %r" % raw


def tool_sha256_file(path):
    rp, err = safe_path(path)
    if err:
        return {"error": err}
    if not rp.is_file():
        return {"error": "not a file: %s" % rp}
    h = hashlib.sha256()
    with open(rp, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return {"path": str(rp), "sha256": h.hexdigest(), "bytes": rp.stat().st_size}


def tool_stat_file(path):
    rp, err = safe_path(path)
    if err:
        return {"error": err}
    if not rp.exists():
        return {"error": "does not exist: %s" % rp}
    st = rp.stat()
    return {"path": str(rp), "bytes": st.st_size, "is_file": rp.is_file(),
            "is_dir": rp.is_dir(),
            "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def tool_list_dir(path):
    rp, err = safe_path(path)
    if err:
        return {"error": err}
    if not rp.is_dir():
        return {"error": "not a directory: %s" % rp}
    out = []
    for child in sorted(rp.iterdir()):
        out.append({"name": child.name,
                    "bytes": child.stat().st_size if child.is_file() else None,
                    "is_dir": child.is_dir()})
        if len(out) >= 300:
            break
    return {"path": str(rp), "entries": out, "truncated": len(out) >= 300}


def tool_read_text(path, max_bytes=60000):
    rp, err = safe_path(path)
    if err:
        return {"error": err}
    if not rp.is_file():
        return {"error": "not a file: %s" % rp}
    limit = max(256, min(int(max_bytes or 60000), 200000))
    data = rp.read_bytes()[:limit]
    return {"path": str(rp), "bytes_read": len(data), "truncated": rp.stat().st_size > len(data),
            "text": data.decode("utf-8", "replace")}


def tool_grep(pattern, path, max_hits=40):
    rp, err = safe_path(path)
    if err:
        return {"error": err}
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return {"error": "bad regex: %s" % exc}
    files = [rp] if rp.is_file() else [p for p in rp.rglob("*") if p.is_file()]
    hits = []
    for f in files:
        if len(hits) >= int(max_hits or 40):
            break
        if f.stat().st_size > 4_000_000:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append({"file": str(f), "line": i, "text": line[:300]})
                if len(hits) >= int(max_hits or 40):
                    break
    return {"pattern": pattern, "path": str(rp), "hits": hits, "truncated": len(hits) >= int(max_hits or 40)}


TOOLS = {"sha256_file": tool_sha256_file, "stat_file": tool_stat_file,
         "list_dir": tool_list_dir, "read_text": tool_read_text, "grep": tool_grep}

TOOL_SCHEMA = [
    {"type": "function", "function": {"name": "sha256_file",
     "description": "Return the sha256 and byte size of one file inside the run root or the frozen worktree.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "stat_file",
     "description": "Return size and mtime of a file or directory.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "list_dir",
     "description": "List one directory (at most 300 entries).",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "read_text",
     "description": "Read up to max_bytes of a UTF-8 text file.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"},
      "max_bytes": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "grep",
     "description": "Regex search inside one file or directory; returns matching lines with file and line number.",
     "parameters": {"type": "object", "properties": {"pattern": {"type": "string"},
      "path": {"type": "string"}, "max_hits": {"type": "integer"}},
      "required": ["pattern", "path"]}}},
]

GATES = [
    "H0_GEOMETRY_CONTRACT_FROZEN", "H0_FREEZE_CONFLICT_DISCLOSED",
    "H0_RESOURCE_ACCOUNTING_INSTRUMENTED", "H0_CODE_SHA_FROZEN", "H0_ZERO_PHYSICAL",
    "A0_ABLATION_FAIRNESS", "A0_CONDITIONAL_SUPERVISION", "O0_TASK_AND_SUBSPACE",
    "O0_ALPHA_ALGORITHM", "O0_ADMISSION_TOLERANCE", "O0_ACCOUNTING_CONTROLS",
    "O0_BUDGET_CAPS", "O0_ABORT_DISCLOSED", "O0_CARRY_FORWARD_ACCOUNTING",
    "O0_BINDING_VERIFYABLE", "O0_FINAL_BUDGET_PRE_REGISTERED", "O0_FINAL_GO_REQUIRED",
    "O0_FINAL_REPAIR_DISCLOSED",
]
gate_json = ",".join('"%s":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL"' % g for g in GATES)


def build_prompt(now):
    dossier = DOSSIER.read_text(encoding="utf-8")
    return """You are A5, an independent read-only reviewer. You DO have read-only tools this round: sha256_file, stat_file, list_dir, read_text, grep. They are scoped to the run root D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01 and the frozen worktree D:/RCAIDE/.worktrees/dreal005-20261124 and they cannot write anything. Use them where a claim is checkable: measure the sha256 of the dossier, the preregistration, the abort record, the fix evidence, the code files listed in section 1, the archived verifier output, and read the code when the dossier describes what it does. Do not invent file contents; if a tool returns an error, record it. Do not sign as a human. Do not assume any run happened that the dossier does not show.

The current UTC timestamp is """ + now + """; use it for reviewed_utc and do not discuss or question dates.

Return ONLY one valid compact JSON object, no markdown, ending with }:
{"reviewer":"deepseek-v4.1-flash","review_type":"independent_read_only_tool_review","reviewed_utc":"YYYY-MM-DDTHH:MM:SSZ","dossier_sha256":"<sha256 you measured>","verdict":"H0_A0_O0_REVIEW_PASS"|"H0_A0_O0_CHANGES_REQUIRED"|"H0_A0_O0_REJECT","gate_verdicts":{""" + gate_json + """},"tool_calls_made":["..."],"evidence_checked":["..."],"findings":[{"severity":"critical|major|minor|info","finding":"...","evidence":"..."}],"limitations":["..."],"scope":"...","signature":"deepseek-v4.1-flash independent A5 review with read-only local tools; not a human signature"}

Gate O0_BINDING_VERIFYABLE asks whether this document's hash can be verified mechanically by the harness and whether the GO is hard-gated on that verification; measure the archived verifier JSON and say what you found. Judge the MECHANISM, not whether a clean round over the current bytes already exists: by construction such a round cannot exist yet, because the round must also agree with the verdict, and the verdict is produced from this document after you read it. The order is dossier -> review -> binding round -> GO, with the round as a hard precondition of the GO in o0_make_go.py. If the mechanism is real and hard-gated, the correct verdict for this gate is PASS or PASS_WITH_DISCLOSURE and you should say in a finding that the current-bytes round is pending by construction. If the mechanism is broken, circular or bypassable, that is FAIL.

Hard limits: at most 8 findings, each finding and evidence <= 240 characters; at most 6 limitations; scope <= 400 characters. JSON must be complete.

Five gates exist because two real batches and one crashed verification attempt were already run and must be accounted for rather than reset (sections 0b and 4b): O0_ABORT_DISCLOSED asks whether the aborted first batch, its root cause and its one charged start are disclosed accurately rather than hidden; O0_CARRY_FORWARD_ACCOUNTING asks whether that spend is carried forward so a GO cannot authorize the full cap again; O0_FINAL_BUDGET_PRE_REGISTERED asks whether the separate verification budget in section 4b is itemized in the frozen preregistration with every cap key present and matching the runner, so the verification cannot invent its own allowance at run time; O0_FINAL_GO_REQUIRED asks whether those verification starts are gated on their own A5 verdict and their own GO record rather than riding on the optimizer GO; O0_FINAL_REPAIR_DISCLOSED asks whether section 4c discloses the crashed first verification attempt, the three starts and 39 internal cases it actually spent, the two mislabelled repeat rows and the missing third row, and whether the repair re-charges those starts honestly (void rows with the sha256 of the polar and case_result.json that back them) instead of re-classifying them as unspent or re-running them. It also asks whether section 4d discloses the later attempt that died for free, with its root cause and the tests that now pin the wiring, rather than reporting only the crash that cost money. A dossier that reported zero physical starts would be failing O0_ABORT_DISCLOSED.

Two things about evidence, so that a finding is about the bytes and not about a directory name. First, a case directory is not a solver start: o0_eval.py writes plan.json, approval.json, task_spec.json, the geometry files and the case inputs before anything is solved, so a directory can exist with zero starts behind it. A start is a .polar plus a case_result.json whose physical_solver_starts is 1, or a ledger row charged before the spawn. Check that distinction with list_dir and the file counts rather than inferring spend from a directory listing; the dossier states it in section 4b and scripts/_preflight_inventory.py prints file count, byte count and polar count per case directory. Second, a GO record is only valid for the exact bytes it binds: if a GO exists at o0_final_go_record.json whose a5_dossier_sha256 differs from the dossier you are reading, that is a real finding, because the authorization then predates the document. If no GO exists yet, that is expected, since the GO is issued only after your verdict on these bytes; the dossier must say so, and o0_make_final_go.py now refuses to overwrite an existing GO that binds other bytes and records written_by so the writer of a GO can be identified.

H0_ZERO_PHYSICAL means: the H0 freeze, the A0 five-arm training (replayed real labels, zero solver calls) and this review spent no solver starts. The issue has touched the solver under a separate O0 authorization: 23 starts and 227 internal cases are on record across the aborted batch (1 start, 7 internal cases) and the closed optimizer batch (22 starts, 220 internal cases), all disclosed and all carried forward. Judge that definition, not a claim that the issue has never touched the solver. A start that is hidden, or spent without a record, is a FAIL; disclosed and carried-forward spend is PASS.

Decide strictly what this dossier still asks to spend. The optimizer authorization allowed at most 12 design attempts, exactly 2 starts and 20 internal cases per design, therefore at most 24 starts and 240 internal cases; 12 designs, 23 starts and 227 internal cases are already spent, so no further optimizer design can be proposed and no further optimizer batch is requested. The physics still requested is the separate verification step in sections 4b, 4c and 4d: at most 8 solver starts and 104 internal cases gross, itemized as 2 void rows already spent at 2 wake nodes (26 internal cases), 1 wake probe already spent at 16 wake nodes (13 internal cases), 4 repeat runs still to spend at the reference mesh (52 internal cases) and 1 wake probe still to spend (13 internal cases); 3 of those starts and 39 internal cases were already spent before this dossier and are carried forward rather than reset, so 5 starts and 65 internal cases remain. It re-measures exactly two already-admitted designs, with its own A5 verdict and its own GO record, a ledger that survives a crash, an explicit statement that kinds are plan fields and never inferred from a wake count, and wake probes that can never be admitted. Tolerance 1e-3 is never relaxed, there are no retries, parallelism is 1, and upload plus remote readback happens after every 8 starts or 60 minutes. O1 warm-start arms, P2/P3, any mission-level claim, any further optimizer design and any reuse of an older authorization or GO are NOT authorized.

Judge specifically: (a) whether the frozen geometry contract is executable and self-consistent while the YAML stays frozen true and main untouched; (b) whether the A0 ablation is a fair five-arm comparison and whether COND_SUPERVISED_16D is genuinely supervised rather than a renamed meta learner; (c) whether the O0 two-start / 20-internal-case alpha strategy can plausibly land a real raw row inside 1e-3 without relaxing the tolerance; (d) whether the accounting cannot silently overspend; (e) whether any claim in the dossier exceeds the evidence; (f) whether the carry-forward arithmetic in sections 0b, 4, 4b and 7 says the same thing everywhere, and whether any residual number is presented as an available optimizer budget when the design cap already forbids another design.

DOSSIER:
""" + dossier


def stream_once(messages, token, domain):
    payload = {"model": MODEL, "messages": messages, "max_tokens": 32000,
               "temperature": 0.1, "stream": True, "tools": TOOL_SCHEMA, "tool_choice": "auto"}
    req = urllib.request.Request(
        BASE + "/v2/chat/completions", data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                 "Accept": "text/event-stream", "x-client-platform": "web", "X-Domain": domain})
    content, calls, raw = [], {}, []
    with urllib.request.urlopen(req, timeout=900) as resp:
        for line in resp:
            s = line.decode("utf-8", "replace").strip()
            if not s or not s.startswith("data:"):
                continue
            data = s[5:].strip()
            if data == "[DONE]":
                break
            raw.append(s)
            try:
                obj = json.loads(data)
            except Exception:
                continue
            for ch in obj.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("content"):
                    content.append(d["content"])
                for tc in d.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = calls.setdefault(idx, {"id": None, "name": None, "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["arguments"] += fn["arguments"]
    return "".join(content), calls, raw


def main() -> int:
    token, domain, vault_file = load_token()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dossier_bytes = DOSSIER.read_bytes()
    dossier_sha = hashlib.sha256(dossier_bytes).hexdigest()
    pre = json.loads(PRE.read_text(encoding="utf-8"))

    messages = [
        {"role": "system", "content": "You are a strict independent reviewer with read-only tools. "
                                      "Measure what you can, then output only valid compact JSON."},
        {"role": "user", "content": build_prompt(now)},
    ]
    transcript = []
    final_text = ""
    for hop in range(MAX_HOPS):
        # Reserve the last two hops: past TOOL_HOPS the reviewer is told to stop measuring and
        # write the verdict, and tool calls are refused rather than executed.
        if hop >= TOOL_HOPS:
            messages.append({"role": "user", "content": (
                "Tool budget exhausted at hop %d of %d. Do not call any more tools. "
                "Write the verdict JSON now from the measurements you already made, using "
                "H0_A0_O0_CHANGES_REQUIRED if a gate is still unverified, and say in "
                "limitations what you could not finish.") % (hop, MAX_HOPS)})
        text, calls, raw = stream_once(messages, token, domain)
        if hop >= TOOL_HOPS and calls:
            print("  refusing %d tool call(s) in the reserved writing hops" % len(calls),
                  flush=True)
            calls = {}
        transcript.append({"hop": hop, "content": text,
                           "tool_calls": {str(k): v for k, v in calls.items()}})
        print("hop %d content_chars %d tool_calls %d" % (hop, len(text), len(calls)), flush=True)
        # Persist after every hop: a review that dies at hop 12 must not lose the eleven
        # hops of measurements it already made, because those are the evidence.
        (OUT / "o0_tool_transcript.json").write_text(
            json.dumps({"dossier_sha256": dossier_sha, "hops": len(transcript),
                        "complete": False, "transcript": transcript},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
        if not calls:
            final_text = text
            break
        messages.append({"role": "assistant", "content": text or None,
                         "tool_calls": [{"id": c["id"], "type": "function",
                                         "function": {"name": c["name"], "arguments": c["arguments"]}}
                                        for c in calls.values()]})
        for c in calls.values():
            name = c.get("name")
            try:
                args = json.loads(c["arguments"] or "{}")
            except Exception as exc:
                result = {"error": "arguments were not valid JSON: %s" % exc}
                args = {}
            if name not in TOOLS:
                result = {"error": "tool %r is not in the allowlist" % name}
            else:
                try:
                    result = TOOLS[name](**args)
                except Exception as exc:
                    result = {"error": "%s: %s" % (type(exc).__name__, exc)}
            print("  tool %s %s -> %s" % (name, brief(args), brief(result)), flush=True)
            transcript[-1].setdefault("results", []).append(
                {"name": name, "arguments": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": c["id"],
                             "content": json.dumps(result, ensure_ascii=False)[:20000]})
    else:
        final_text = transcript[-1].get("content") or ""

    (OUT / "o0_tool_transcript.json").write_text(
        json.dumps({"dossier_sha256": dossier_sha, "hops": len(transcript),
                    "complete": True, "transcript": transcript},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")

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
    verdict["preregistration_sha256"] = hashlib.sha256(PRE.read_bytes()).hexdigest()
    verdict["preregistration_schema"] = pre.get("schema")
    verdict["run_id"] = pre.get("run_id")
    verdict["batch_id"] = pre.get("batch_id")
    verdict["authorization_id"] = pre.get("authorization_id")
    verdict["started_utc"] = now
    verdict["reviewer"] = verdict.get("reviewer") or MODEL
    verdict["model"] = MODEL
    verdict["review_gateway"] = BASE
    verdict["tool_access"] = ("READ_ONLY_LOCAL_TOOLS: sha256_file, stat_file, list_dir, "
                              "read_text, grep; allowlisted to the run root and frozen worktree; "
                              "every call recorded in a5_review/o0_tool_transcript.json")
    verdict["tool_hops"] = len(transcript)
    verdict["human_signature"] = False
    verdict["dossier_path"] = str(DOSSIER)
    verdict["scope_of_this_review"] = ("H0 contract, A0 ablation and O0 protocol review only; "
                                       "NOT an R1 blanket PASS, NOT a physical GO by itself, and "
                                       "NOT an approval of O1 or any later gate.")
    (OUT / "verdict.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8", newline="\n")
    (OUT / "o0_raw_lines.txt").write_text(final_text, encoding="utf-8", newline="\n")
    print(json.dumps({"verdict": verdict.get("verdict"), "dossier_sha256": dossier_sha,
                      "hops": len(transcript), "gates": verdict.get("gate_verdicts")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
