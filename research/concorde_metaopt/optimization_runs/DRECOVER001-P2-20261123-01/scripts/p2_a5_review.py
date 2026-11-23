
"""A5 independent single-shot read-only review of the P2 protocol dossier (deepseek-flash; not a human signature)."""
import hashlib, json, sys, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path
import yaml

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
DOSSIER = RUN / "p2_a5_dossier.md"
OUT = RUN / "a5_review"
BASE = "https://concept-generated-visitors-trackbacks.trycloudflare.com/v1"
PRE = RUN / "p2_preregistration.json"

dossier = DOSSIER.read_text(encoding="utf-8")
pre = json.loads(PRE.read_text(encoding="utf-8"))
key = yaml.safe_load(Path(r"C:/Users/pc/.dsh/.credentials.yaml").read_text(encoding="utf-8"))["refs"]["SUB2_API_KEY"]
OUT.mkdir(parents=True, exist_ok=True)

prompt = """You are A5, an independent read-only reviewer. No tools. Do not invent file contents. Do not sign as a human.
Return ONLY one valid compact JSON object, no markdown, ending with }:
{"reviewer":"deepseek-flash","review_type":"independent_single_shot_dossier_review","reviewed_utc":"YYYY-MM-DDTHH:MM:SSZ","dossier_sha256":"<dossier sha>","verdict":"P2_PROTOCOL_AND_CODE_REVIEW_PASS"|"P2_CHANGES_REQUIRED"|"P2_REJECT","gate_verdicts":{"P2_PREREGISTRATION":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P2_DATASET_MATRIX":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P2_BRACKET_PROVENANCE":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P2_ALPHA_PROTOCOL":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P2_ADMISSION":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P2_ACCOUNTING_CONTROLS":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P2_CAPS":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P2_ZERO_PHYSICAL_UNTIL_GO":"PASS"|"FAIL"},"evidence_checked":["..."],"findings":[{"severity":"critical|major|minor|info","finding":"...","evidence":"..."}],"limitations":["..."],"scope":"...","signature":"deepseek-flash independent A5 review; not a human signature"}
The current UTC timestamp is 2026-11-23T15:25:00Z; use it for reviewed_utc and do not discuss or question dates.
Hard limits: at most 8 findings, each finding and evidence <= 240 characters; at most 6 limitations; scope <= 400 characters. JSON must be complete.
Decide strictly whether this protocol authorizes only ONE frozen supplement batch of at most 16 real solver starts that fills only the missing slots of the frozen eight-task family (M140/M160/M180/M200/M202/M220/M240/M260): tasks already holding 3 independent supports (M160, M200) get 0 starts, tasks with zero labels (M140, M220, M260) get 3 support plus 1 independent query design (d03), and M180/M202/M240 get support only; 3 alpha probes per start, 48 internal cases max (= 16 x 3), wall-clock stop 9600 s (= 16 x 600 s worst case), tolerance 1e-3 not relaxed, no retries, parallelism 1, upload/readback every <=8 starts, and then four-arm meta-learning with K=1 and K=3 at seeds 7/19/43 using only admitted real labels (train-only normalization, validation-only selection, test scored once). P3 online optimization is NOT authorized and no start may occur before a separate Lead GO record.

DOSSIER:
""" + "\n\nDOSSIER_BYTE_IDENTITY: the harness computed sha256 of the exact dossier bytes below BEFORE this request: " + hashlib.sha256(dossier.encode("utf-8")).hexdigest() + "\n\n" + dossier

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
print("stream request started", started, "prompt_chars", len(prompt), "dossier_sha", hashlib.sha256(dossier.encode()).hexdigest(), flush=True)
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
(OUT / "p2_raw_lines.txt").write_text("\n".join(raw), encoding="utf-8", newline="\n")
(OUT / "p2_reasoning_raw.txt").write_text("".join(reasoning), encoding="utf-8", newline="\n")
(OUT / "p2_verdict_raw.txt").write_text(text, encoding="utf-8", newline="\n")
print("http_status", status, "content_chars", len(text), "reasoning_chars", len(reasoning), flush=True)
if not text:
    (OUT / "review_error.json").write_text(json.dumps({"error": "no content", "http_status": status}, indent=2) + "\n", encoding="utf-8")
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
v["scope_of_this_review"] = "P2 protocol and code review only; NOT an R1 blanket PASS, NOT a physical-GO by itself, and NOT an approval of P3."
(OUT / "verdict.json").write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
meta = {"model": "deepseek-flash", "endpoint": BASE, "dossier": str(DOSSIER), "dossier_sha256": dh,
        "verdict": v.get("verdict"), "reviewed_utc": v["reviewed_utc"],
        "findings": len(v.get("findings", [])), "tool_access": v["tool_access"]}
(OUT / "review_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(meta, ensure_ascii=False, indent=2), flush=True)
print(json.dumps(v, ensure_ascii=False, indent=2)[:8000], flush=True)