"""A5 independent single-shot read-only review of the D-REAL-EXP-003 H0/A0/O0 dossier.

deepseek-flash, no tools, streaming, thinking disabled. This is NOT a human signature and
NOT a physical GO by itself.
"""
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
DOSSIER = RUN / "o0_a5_dossier.md"
PRE = RUN / "o0_preregistration.json"
OUT = RUN / "a5_review"
BASE = "https://concept-generated-visitors-trackbacks.trycloudflare.com/v1"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

dossier = DOSSIER.read_text(encoding="utf-8")
pre = json.loads(PRE.read_text(encoding="utf-8"))
key = yaml.safe_load(Path(r"C:/Users/pc/.dsh/.credentials.yaml").read_text(encoding="utf-8"))["refs"]["SUB2_API_KEY"]
OUT.mkdir(parents=True, exist_ok=True)

GATES = [
    "H0_GEOMETRY_CONTRACT_FROZEN",
    "H0_FREEZE_CONFLICT_DISCLOSED",
    "H0_RESOURCE_ACCOUNTING_INSTRUMENTED",
    "H0_CODE_SHA_FROZEN",
    "H0_ZERO_PHYSICAL",
    "A0_ABLATION_FAIRNESS",
    "A0_CONDITIONAL_SUPERVISION",
    "O0_TASK_AND_SUBSPACE",
    "O0_ALPHA_ALGORITHM",
    "O0_ADMISSION_TOLERANCE",
    "O0_ACCOUNTING_CONTROLS",
    "O0_BUDGET_CAPS",
]
gate_json = ",".join('"%s":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL"' % g for g in GATES)

prompt = """You are A5, an independent read-only reviewer. No tools. Do not invent file contents. Do not sign as a human. Do not assume any run happened that the dossier does not show.
Return ONLY one valid compact JSON object, no markdown, ending with }:
{"reviewer":"deepseek-flash","review_type":"independent_single_shot_dossier_review","reviewed_utc":"YYYY-MM-DDTHH:MM:SSZ","dossier_sha256":"<dossier sha>","verdict":"H0_A0_O0_REVIEW_PASS"|"H0_A0_O0_CHANGES_REQUIRED"|"H0_A0_O0_REJECT","gate_verdicts":{""" + gate_json + """},"evidence_checked":["..."],"findings":[{"severity":"critical|major|minor|info","finding":"...","evidence":"..."}],"limitations":["..."],"scope":"...","signature":"deepseek-flash independent A5 review; not a human signature"}
The current UTC timestamp is """ + NOW + """; use it for reviewed_utc and do not discuss or question dates.
Hard limits: at most 8 findings, each finding and evidence <= 240 characters; at most 6 limitations; scope <= 400 characters. JSON must be complete.
Decide strictly whether this dossier authorizes ONLY the first limited O0 real batch: at most 12 design attempts, at most 36 solver starts, at most 240 internal alpha cases, 2 starts and 20 internal cases per design, lift tolerance 1e-3 never relaxed, no retries, parallelism 1, upload and remote readback after every 8 starts or 60 minutes. O1 warm-start arms, P2/P3, any mission-level claim and any reuse of an older authorization or GO are NOT authorized. No solver start may occur before a separate Lead GO record whose code SHAs match section 1.
Judge specifically: (a) whether the frozen geometry contract is executable and self-consistent while the YAML stays frozen true and main untouched; (b) whether the A0 ablation is a fair five-arm comparison and whether COND_SUPERVISED_16D is genuinely supervised rather than a renamed meta learner; (c) whether the O0 two-start / 20-internal-case alpha strategy can plausibly land a real raw row inside 1e-3 without relaxing the tolerance; (d) whether the accounting cannot silently overspend; (e) whether any claim in the dossier exceeds the evidence.

DOSSIER:
""" + dossier

payload = {
    "model": "deepseek-flash",
    "messages": [
        {"role": "system", "content": "You are a strict independent reviewer. Output only valid compact JSON."},
        {"role": "user", "content": prompt},
    ],
    "max_tokens": 20000,
    "temperature": 0.1,
    "stream": True,
    "chat_template_kwargs": {"thinking": False},
}
body = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    BASE + "/chat/completions", data=body, method="POST",
    headers={"Authorization": "Bearer " + key,
             "Content-Type": "application/json",
             "Accept": "text/event-stream"})
started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
print("stream request started", started, "prompt_chars", len(prompt),
      "dossier_sha", hashlib.sha256(dossier.encode()).hexdigest(), flush=True)
chunks, reasoning, raw, status = [], [], [], 0
try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        status = resp.status
        for line in resp:
            s = line.decode("utf-8", "replace").strip()
            if not s:
                continue
            raw.append(s)
            if not s.startswith("data:"):
                continue
            data = s[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            for ch in obj.get("choices", []):
                d = ch.get("delta", {})
                if d.get("content"):
                    chunks.append(d["content"])
                if d.get("reasoning_content"):
                    reasoning.append(d["reasoning_content"])
except urllib.error.HTTPError as e:
    status = e.code
    print("HTTP_ERROR", e.code, e.read().decode("utf-8", "replace")[:2000], flush=True)
except Exception as e:  # noqa: BLE001
    print("EXC", type(e).__name__, str(e)[:2000], flush=True)

text = "".join(chunks)
(OUT / "o0_raw_lines.txt").write_text("\n".join(raw), encoding="utf-8", newline="\n")
(OUT / "o0_reasoning_raw.txt").write_text("".join(reasoning), encoding="utf-8", newline="\n")
(OUT / "o0_verdict_raw.txt").write_text(text, encoding="utf-8", newline="\n")
print("http_status", status, "content_chars", len(text),
      "reasoning_chars", len(reasoning), flush=True)
if not text:
    (OUT / "review_error.json").write_text(
        json.dumps({"error": "no content", "http_status": status}, indent=2) + "\n", encoding="utf-8")
    sys.exit(3)
start = text.find("{")
end = text.rfind("}")
cand = text[start:end + 1] if start >= 0 and end > start else text
try:
    v = json.loads(cand)
except Exception as e:  # noqa: BLE001
    print("JSON_ERROR", e, flush=True)
    print("RAW_FULL", text[:4000], flush=True)
    sys.exit(2)

dh = hashlib.sha256(dossier.encode("utf-8")).hexdigest()
v["model"] = "deepseek-flash"
v["reviewer"] = "deepseek-flash"
v["dossier_path"] = str(DOSSIER)
v["dossier_sha256"] = dh
v["preregistration_sha256"] = hashlib.sha256(PRE.read_bytes()).hexdigest()
v["preregistration_schema"] = pre.get("schema")
v["run_id"] = pre.get("run_id")
v["batch_id"] = pre.get("batch_id")
v["authorization_id"] = pre.get("authorization_id")
v["started_utc"] = started
v["reviewed_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
v["tool_access"] = "NONE_SINGLE_SHOT_DOSSIER_STREAM"
v["human_signature"] = False
v["scope_of_this_review"] = ("H0 contract, A0 ablation and O0 protocol review only; NOT an R1 blanket "
                             "PASS, NOT a physical GO by itself, and NOT an approval of O1 or any "
                             "later gate.")
(OUT / "verdict.json").write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8", newline="\n")
meta = {"model": "deepseek-flash", "endpoint": BASE, "dossier": str(DOSSIER),
        "dossier_sha256": dh, "verdict": v.get("verdict"),
        "reviewed_utc": v["reviewed_utc"], "findings": len(v.get("findings", [])),
        "tool_access": v["tool_access"]}
(OUT / "review_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8", newline="\n")
print(json.dumps(meta, ensure_ascii=False, indent=2), flush=True)
print(json.dumps(v, ensure_ascii=False, indent=2)[:8000], flush=True)
