
import json, hashlib, sys, urllib.request, urllib.error, yaml
from pathlib import Path
from datetime import datetime, timezone
DOSSIER=Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120/docs/evidence/dreal003/g2/g2_a5_dossier.md")
OUT=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01/a5_review"); OUT.mkdir(parents=True,exist_ok=True)
dossier=DOSSIER.read_text(encoding="utf-8")
key=yaml.safe_load(Path(r"C:/Users/pc/.dsh/.credentials.yaml").read_text(encoding="utf-8"))["refs"]["SUB2_API_KEY"]
BASE="https://concept-generated-visitors-trackbacks.trycloudflare.com/v1"
prompt="""You are A5, an independent read-only reviewer. No tools. Do not invent file contents. Do not sign as a human.
Return ONLY one valid compact JSON object, no markdown, ending with }:
{"reviewer":"deepseek-flash","review_type":"independent_single_shot_dossier_review","reviewed_utc":"YYYY-MM-DDTHH:MM:SSZ","dossier_sha256":"<dossier sha>","verdict":"G2_APPROVE"|"G2_CHANGES_REQUIRED"|"G2_REJECT","gate_verdicts":{"G2_PREREGISTRATION":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","G2_TASK_FAMILY_SPLIT":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","G2_TWO_STAGE_ALPHA_METHOD":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","G2_ADMISSION_RULE":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","G2_BATCH_CONTROLS":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","G2_ZERO_PHYSICAL_BEFORE_START":"PASS"|"FAIL"},"evidence_checked":["..."],"findings":[{"severity":"critical|major|minor|info","finding":"...","evidence":"..."}],"limitations":["..."],"scope":"...","signature":"deepseek-flash independent A5 review; not a human signature"}
The current UTC timestamp is 2026-11-22T00:30:00Z; use it for reviewed_utc and do not discuss or question dates.
Hard limits: at most 8 findings, each finding and evidence <= 240 characters; at most 6 limitations; scope <= 400 characters. JSON must be complete.
Decide strictly whether this authorizes only the first mini-batch of at most 24 real solver starts, with 128 planned starts and per-mini-batch upload/readback; G3/R2 not authorized.

DOSSIER:
"""+dossier
payload={"model":"deepseek-flash","messages":[{"role":"system","content":"You are a strict independent reviewer. Output only valid compact JSON."},{"role":"user","content":prompt}],"max_tokens":20000,"temperature":0.1,"stream":True,"chat_template_kwargs":{"thinking":False}}
body=json.dumps(payload).encode("utf-8")
req=urllib.request.Request(BASE+"/chat/completions",data=body,method="POST",headers={"Authorization":"Bearer "+key,"Content-Type":"application/json","Accept":"text/event-stream"})
started=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
print("stream request started",started,"prompt_chars",len(prompt),flush=True)
chunks=[];reasoning=[];raw=[];status=0
try:
    with urllib.request.urlopen(req,timeout=300) as resp:
        status=resp.status
        for line in resp:
            s=line.decode("utf-8","replace").strip()
            if not s: continue
            raw.append(s)
            if not s.startswith("data:"): continue
            data=s[5:].strip()
            if data=="[DONE]": break
            try: obj=json.loads(data)
            except Exception: continue
            for ch in obj.get("choices",[]):
                d=ch.get("delta",{})
                if d.get("content"): chunks.append(d["content"])
                if d.get("reasoning_content"): reasoning.append(d["reasoning_content"])
except urllib.error.HTTPError as e:
    status=e.code; print("HTTP_ERROR",e.code,e.read().decode("utf-8","replace")[:2000],flush=True)
except Exception as e:
    print("EXC",type(e).__name__,str(e)[:2000],flush=True)
text="".join(chunks)
(OUT/"g2_raw_lines.txt").write_text("\n".join(raw),encoding="utf-8")
(OUT/"g2_reasoning_raw.txt").write_text("".join(reasoning),encoding="utf-8")
(OUT/"g2_verdict_raw.txt").write_text(text,encoding="utf-8")
print("http_status",status,"content_chars",len(text),"reasoning_chars",len(reasoning),flush=True)
if not text:
    (OUT/"review_error.json").write_text(json.dumps({"error":"no content","http_status":status},indent=2)+"\n",encoding="utf-8"); sys.exit(3)
start=text.find("{");end=text.rfind("}")
cand=text[start:end+1] if start>=0 and end>start else text
try: v=json.loads(cand)
except Exception as e:
    print("JSON_ERROR",e,flush=True); print("RAW_FULL",text[:4000],flush=True); sys.exit(2)
sha=hashlib.sha256(dossier.encode("utf-8")).hexdigest()
v["model"]="deepseek-flash"; v["reviewer"]="deepseek-flash"; v["dossier_path"]=str(DOSSIER); v["dossier_sha256"]=sha
v["started_utc"]=started; v["reviewed_utc"]=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
v["tool_access"]="NONE_SINGLE_SHOT_DOSSIER_STREAM"; v["human_signature"]=False
(OUT/"verdict.json").write_text(json.dumps(v,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
meta={"model":"deepseek-flash","endpoint":BASE,"dossier":str(DOSSIER),"dossier_sha256":sha,"verdict":v.get("verdict"),"reviewed_utc":v["reviewed_utc"],"findings":len(v.get("findings",[])),"tool_access":v["tool_access"]}
(OUT/"review_meta.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print(json.dumps(meta,indent=2,ensure_ascii=False),flush=True); print(json.dumps(v,indent=2,ensure_ascii=False)[:8000],flush=True)