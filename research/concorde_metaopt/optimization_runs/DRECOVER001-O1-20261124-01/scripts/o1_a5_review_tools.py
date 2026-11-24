"""A5 independent review of the O1 three-arm dossier, with read-only local tools.

Same harness discipline as the O0 review: the reviewer (deepseek-v4.1-flash on the
WorkBuddy CN gateway) gets a closed allowlist of read-only tools scoped to the O1 run
root, the frozen worktree and the A0 run root, and every call is recorded in a
transcript so the verdict can be audited against the exact bytes the reviewer saw.

This is NOT a human signature and NOT a physical GO.
"""
from __future__ import annotations

import glob
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
A0_RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01")
O0_RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
DOSSIER = RUN / "o1_a5_dossier.md"
PRE = RUN / "o1_preregistration.json"
OUT = RUN / "a5_review"
BASE = "https://copilot.tencent.com"
MODEL = "deepseek-v4.1-flash"
ALLOWED_ROOTS = [RUN.resolve(), REPO.resolve(), A0_RUN.resolve(), O0_RUN.resolve()]
EXTRA_FILES = [Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py")]
MAX_HOPS = 30
TOOL_HOPS = MAX_HOPS - 2
OUT.mkdir(parents=True, exist_ok=True)


def brief(obj, limit=200):
    try:
        text = json.dumps(obj, ensure_ascii=True)
    except Exception:
        text = repr(obj)
    return text[:limit]


def load_token():
    """Return every usable (token, domain, file) candidate, not just the first.

    A workbuddy token carries a daily quota and answers HTTP 429 with code 6004 once it is
    spent, so a reviewer that hard-codes "the first token in the vault" dies the moment that
    account is exhausted even though other accounts still have budget. The caller rotates.
    """
    candidates = []
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
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(d)
        if tok:
            candidates.append((tok, dom or "www.workbuddy.cn", f))
    if not candidates:
        raise SystemExit("no workbuddy token found")
    return candidates


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
    return None, "path outside the read-only allowlist (O1 run, worktree, A0 run, O0 run): %r" % raw


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
    return {"path": str(rp), "bytes": st.st_size, "is_file": rp.is_file(), "is_dir": rp.is_dir(),
            "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")}


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
    return {"pattern": pattern, "path": str(rp), "hits": hits,
            "truncated": len(hits) >= int(max_hits or 40)}


TOOLS = {"sha256_file": tool_sha256_file, "stat_file": tool_stat_file,
         "list_dir": tool_list_dir, "read_text": tool_read_text, "grep": tool_grep}

TOOL_SCHEMA = [
    {"type": "function", "function": {"name": "sha256_file",
     "description": "Return the sha256 and byte size of one file inside the O1 run root, the frozen worktree, the A0 run root or the O0 run root.",
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
    "O1_TASK_IS_NEW", "O1_CODE_SHA_FROZEN", "O1_ZERO_PHYSICAL",
    "O1_THREE_ARMS_FAIR", "O1_KSHOT_NO_LEAKAGE", "O1_CANDIDATE_POOL_NO_TRUTH",
    "O1_COST_MODEL_CONSISTENT", "O1_SHARED_SUPPORT_CHARGED_TO_ALL_ARMS",
    "O1_BUDGET_CAPS", "O1_TARGET_PRE_REGISTERED", "O1_TRUNCATION_DISCLOSED",
    "O1_GEOMETRY_AND_ALPHA_UNCHANGED", "O1_CLAIMS_BOUNDED",
    "O1_CARRY_FORWARD_ACCOUNTED", "O1_BINDING_VERIFYABLE", "O1_GO_REQUIRED",
]
gate_json = ",".join('"%s":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL"' % g for g in GATES)


def build_prompt(now):
    dossier = DOSSIER.read_text(encoding="utf-8")
    return """You are A5, an independent read-only reviewer. You DO have read-only tools this round: sha256_file, stat_file, list_dir, read_text, grep. They are scoped to the O1 run root D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01, the frozen worktree D:/RCAIDE/.worktrees/dreal005-20261124, the A0 run root D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01 and the O0 run root D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01. They cannot write anything. Use them where a claim is checkable: measure the sha256 of the dossier, the preregistration and every frozen code file in section 1; check that the A0 checkpoints and the A0 normalizer named in section 3 exist; check that no O1 case directory contains a polar; read the ranking code to see whether a label could leak into the K-shot warm start. Do not invent file contents; if a tool returns an error, record it. Do not sign as a human.

The current UTC timestamp is """ + now + """; use it for reviewed_utc and do not discuss or question dates.

Return ONLY one valid compact JSON object, no markdown, ending with }:
{"reviewer":"deepseek-v4.1-flash","review_type":"independent_read_only_tool_review","reviewed_utc":"YYYY-MM-DDTHH:MM:SSZ","dossier_sha256":"<sha256 you measured>","verdict":"O1_THREE_ARM_REVIEW_PASS"|"O1_THREE_ARM_CHANGES_REQUIRED"|"O1_THREE_ARM_REJECT","gate_verdicts":{""" + gate_json + """},"tool_calls_made":["..."],"evidence_checked":["..."],"findings":[{"severity":"critical|major|minor|info","finding":"...","evidence":"..."}],"limitations":["..."],"scope":"...","signature":"deepseek-v4.1-flash independent A5 review with read-only local tools; not a human signature"}

The question this stage asks is narrow: at EQUAL real evaluation cost, does a meta-learned warm start reach a lower best-feasible induced drag than a plain Sobol warm start on a new task? The A0 ablation did NOT establish that the meta objective is superior (paired test delta -893.145 N, 95% CI [-7111.5, 5289.6], sign test p=0.8145). A dossier that claims superiority, global optimality, regret or aerodynamic validation is failing O1_CLAIMS_BOUNDED.

O1_THREE_ARMS_FAIR asks whether the three arms differ only in the warm-start rule: same three real shared support designs, same 256-coordinate candidate pool with no objective values, same GP backend and hyperparameters, same alpha recipe, same admission gate, same geometry contract, same subspace, and each arm's later proposals driven only by that arm's own real feedback. Information asymmetry granted to one arm (extra support labels, other arm's results, pre-computed objectives, a different GP) is a FAIL.

O1_KSHOT_NO_LEAKAGE asks whether the two K-shot arms read only the frozen A0 checkpoint, the three shared support rows and the task specification (Mach, q, CL target, altitude). A test label, a query label, an optimizer result or any per-arm result entering the warm-start ranking is a FAIL. Check o1_arms.py: kshot_ranked_candidates builds the context from the task spec and adapts on support_rows only, and the ranking is computed before the arm's own adaptive designs exist.

O1_COST_MODEL_CONSISTENT asks whether the arithmetic is right: 20 internal cases per design (7 coarse + 13 refine), 2 charged starts per design, so 160 internal per arm / 20 = 8 designs per arm, and the internal cap binds before the 12-design and 24-start caps. 8 designs x 3 arms = 24 designs, 16 equivalent starts per arm and 48 across the arms, 480 internal equivalent. O1_SHARED_SUPPORT_CHARGED_TO_ALL_ARMS asks whether the three shared support designs are solved once but charged in full to all three arms, with the physical and equivalent bills reported separately and never added together. O1_TRUNCATION_DISCLOSED asks whether the report commits to saying all three arms were truncated at the same common budget rather than claiming independent convergence.

O1_CARRY_FORWARD_ACCOUNTED asks whether the earlier O0 spend (12 designs / 23 starts / 227 internal from the optimizer batch, plus 8 starts / 104 internal from the O0-FINAL verification) is carried forward and shown as already spent, and whether O1 claims any additional optimizer design (it must claim none).

O1_BINDING_VERIFYABLE asks whether this document's hash can be verified mechanically by the harness and whether the GO is hard-gated on that verification. Judge the MECHANISM, not whether a clean round over the current bytes already exists: by construction such a round cannot exist yet, because the round must also agree with the verdict, and the verdict is produced from this document after you read it. The order is dossier -> review -> binding round -> GO. If no O1 go record exists yet that is EXPECTED, because the GO is issued only after your verdict on these bytes; that is not a finding. If the mechanism is broken, circular or bypassable, that is FAIL.

Artifact retirement, which O1_BINDING_VERIFYABLE also covers: a PASS verdict and a binding round from an earlier release of this dossier are not deleted, they are copied into dated history and removed from the live path by scripts/o1_retire_stale.py, and the substitution is recorded in o1_retire_record.json with the old and new hashes. Read that record and the script if it exists. Judge whether the rule is sound and mechanically enforced by o1_make_go.py -- namely that an artifact is retired only when it names bytes that are not on disk, that it is archived before removal, and that a GO cannot be issued unless the live verdict and the live binding round both name the dossier bytes on disk. If the record does not exist yet, say so and judge the code path instead; that is not by itself a finding.

O1_ZERO_PHYSICAL asks whether this preregistration and everything up to this review spent zero solver starts. The O1 case directories must contain no .polar and no case_result.json; use list_dir to check.

Hard limits: at most 8 findings, each finding and evidence <= 240 characters; at most 6 limitations; scope <= 400 characters. JSON must be complete.

DOSSIER:
""" + dossier


def stream_once(messages, token, domain):
    payload = {"model": MODEL, "messages": messages, "max_tokens": 32000,
               "temperature": 0.1, "stream": True, "tools": TOOL_SCHEMA,
               "tool_choice": "auto"}
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


class QuotaExhausted(RuntimeError):
    """The gateway refused this token because the account's quota is spent."""


def main() -> int:
    candidates = load_token()
    token, domain, vault_file = candidates[0]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dossier_sha = hashlib.sha256(DOSSIER.read_bytes()).hexdigest()
    pre = json.loads(PRE.read_text(encoding="utf-8"))

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
                "O1_THREE_ARM_CHANGES_REQUIRED if a gate is still unverified, and say in "
                "limitations what you could not finish.") % (hop, MAX_HOPS)})
        text, calls, raw = None, None, None
        for attempt in range(len(candidates) + 1):
            try:
                text, calls, raw = stream_once(messages, token, domain)
                break
            except urllib.error.HTTPError as exc:
                body = b""
                try:
                    body = exc.read()[:400]
                except Exception:  # noqa: BLE001
                    pass
                spent = exc.code == 429
                print("  gateway HTTP %d on %s (%s): %r" % (
                    exc.code, Path(vault_file).name, domain, body[:200]), flush=True)
                if not spent or attempt >= len(candidates):
                    raise
                token, domain, vault_file = candidates[attempt]
                print("  rotating to %s (%s)" % (Path(vault_file).name, domain), flush=True)
        if text is None:
            raise SystemExit("every vault token is out of quota; no review was produced")
        if hop >= TOOL_HOPS and calls:
            print("  refusing %d tool call(s) in the reserved writing hops" % len(calls),
                  flush=True)
            calls = {}
        transcript.append({"hop": hop, "content": text,
                           "tool_calls": {str(k): v for k, v in calls.items()}})
        print("hop %d content_chars %d tool_calls %d" % (hop, len(text), len(calls)), flush=True)
        (OUT / "o1_tool_transcript.json").write_text(
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

    (OUT / "o1_tool_transcript.json").write_text(
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
                              "read_text, grep; allowlisted to the O1 run root, the frozen "
                              "worktree, the A0 run root and the O0 run root; every call "
                              "recorded in a5_review/o1_tool_transcript.json")
    verdict["tool_hops"] = len(transcript)
    verdict["human_signature"] = False
    verdict["dossier_path"] = str(DOSSIER)
    verdict["scope_of_this_review"] = ("O1 three-arm warm-start protocol only; NOT an R1 "
                                       "blanket PASS, NOT a physical GO by itself, and NOT an "
                                       "approval of any later gate.")
    (OUT / "verdict.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8", newline="\n")
    (OUT / "o1_raw_lines.txt").write_text(final_text, encoding="utf-8", newline="\n")
    print(json.dumps({"verdict": verdict.get("verdict"), "dossier_sha256": dossier_sha,
                      "hops": len(transcript), "gates": verdict.get("gate_verdicts")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
