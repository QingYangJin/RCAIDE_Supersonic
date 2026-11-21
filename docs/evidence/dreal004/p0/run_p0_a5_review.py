
"""P0 independent A5 review request (deepseek-flash single-shot, read-only, no tools).

Not a human signature.  The verdict gates P1 only if it is P0_CODE_AND_PROTOCOL_PASS;
even then Lead must issue a separate P1 GO.
"""
from __future__ import annotations

import hashlib, json, sys, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
DOSSIER = ROOT / "docs/evidence/dreal004/p0/p0_a5_dossier.md"
OUT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P1-20261122-01/a5_review_p0")
OUT.mkdir(parents=True, exist_ok=True)

dossier = DOSSIER.read_text(encoding="utf-8")
cred = yaml.safe_load(Path(r"C:/Users/pc/.dsh/.credentials.yaml").read_text(encoding="utf-8"))
key = cred["refs"]["SUB2_API_KEY"]
BASE = cred.get("refs", {}).get("SUB2_API_BASE") or "https://concept-generated-visitors-trackbacks.trycloudflare.com/v1"
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
prompt = """You are A5, an independent read-only reviewer for a research repository. No tools. Do not invent file contents. Do not sign as a human.
Review the P0 dossier of Issue #14 (D-REAL-EXP-002). Return ONLY one valid compact JSON object, no markdown, ending with }:
{"reviewer":"deepseek-flash","review_type":"independent_single_shot_dossier_review","reviewed_utc":"YYYY-MM-DDTHH:MM:SSZ","dossier_sha256":"<dossier sha>","verdict":"P0_CODE_AND_PROTOCOL_PASS"|"P0_CHANGES_REQUIRED"|"P0_REJECT","gate_verdicts":{"P0_CODE_PASS":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P0_ZERO_PHYSICAL_REPLAY_PASS":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P0_12D_RESPONSE_AUDIT_PASS":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P0_A2_ENDPOINT_ANALYZER_PASS":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P0_PROTOCOL_FREEZE_PASS":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P0_ZERO_PHYSICAL":"PASS"|"FAIL"},"evidence_checked":["..."],"findings":[{"severity":"critical|major|minor|info","finding":"...","evidence":"..."}],"limitations":["..."],"scope":"...","signature":"deepseek-flash independent A5 review; not a human signature"}
The current UTC timestamp is NOWUTC; use it for reviewed_utc and do not discuss or question dates.
Hard limits: at most 10 findings, each finding and evidence <= 240 characters; at most 6 limitations; scope <= 400 characters. JSON must be complete.
Decide strictly whether P0 (code, zero-physical replay, 12D audit, A2 analyzer, protocol freeze) is acceptable, and whether it authorises ANY new physics. It must NOT authorise P1; P1 needs a separate A5 review of a batch plan and a fresh Lead GO. tol_CL=1e-3 must not be relaxed and interpolated estimates must never be counted as raw hits. Prior G1/G2 results must not be re-graded. V01/V02 are passive at beta=0 and must not be claimed as active 12D response dimensions.

DOSSIER:
""".replace("NOWUTC", now) + dossier
payload = {"model": "deepseek-flash",
           "messages": [{"role": "system", "content": "You are a strict independent reviewer. Output only valid compact JSON."},
                        {"role": "user", "content": prompt}],
           "max_tokens": 20000, "temperature": 0.1, "stream": True,
           "chat_template_kwargs": {"thinking": False}}
body = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(BASE + "/chat/completions", data=body, method="POST",
                             headers={"Authorization": "Bearer " + key,
                                      "Content-Type": "application/json",
                                      "Accept": "text/event-stream"})
started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
print("stream request started", started, "prompt_chars", len(prompt), flush=True)
chunks, reasoning, raw, status = [], [], [], 0
try:
    with urllib.request.urlopen(req, timeout=600) as resp:
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
except Exception as e:
    print("EXC", type(e).__name__, str(e)[:2000], flush=True)
text = "".join(chunks)
(OUT / "p0_raw_lines.txt").write_text("\n".join(raw), encoding="utf-8")
(OUT / "p0_reasoning_raw.txt").write_text("".join(reasoning), encoding="utf-8")
(OUT / "p0_verdict_raw.txt").write_text(text, encoding="utf-8")
print("http_status", status, "content_chars", len(text), "reasoning_chars", len(reasoning), flush=True)
if not text:
    (OUT / "review_error.json").write_text(json.dumps({"error": "no content", "http_status": status}, indent=2), encoding="utf-8")
    sys.exit(3)
start = text.find("{"); end = text.rfind("}")
cand = text[start:end + 1] if start >= 0 and end > start else text
try:
    verdict = json.loads(cand)
except Exception as e:
    print("JSON_ERROR", e, flush=True); print("RAW_FULL", text[:4000], flush=True); sys.exit(2)
sha = hashlib.sha256(dossier.encode("utf-8")).hexdigest()
verdict["model"] = "deepseek-flash"; verdict["reviewer"] = "deepseek-flash"
verdict["dossier_path"] = str(DOSSIER); verdict["dossier_sha256"] = sha
verdict["started_utc"] = started
verdict["reviewed_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
verdict["tool_access"] = "NONE_SINGLE_SHOT_DOSSIER_STREAM"
verdict["human_signature"] = False
(OUT / "verdict.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
meta = {"model": "deepseek-flash", "endpoint": BASE, "dossier": str(DOSSIER),
        "dossier_sha256": sha, "verdict": verdict.get("verdict"),
        "reviewed_utc": verdict["reviewed_utc"],
        "findings": len(verdict.get("findings", [])), "tool_access": verdict["tool_access"]}
(OUT / "review_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(meta, indent=2, ensure_ascii=False), flush=True)
print(json.dumps(verdict, indent=2, ensure_ascii=False)[:8000], flush=True)
