
import glob, json, sys, urllib.request
from pathlib import Path

def load_token():
    for f in sorted(glob.glob(r"C:/Users/pc/.dsh/workbuddy-vault/cn/*.json")):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        tok = dom = None
        def walk(o):
            nonlocal tok, dom
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("accessToken","access_token") and isinstance(v,str) and len(v)>200: tok=v
                    elif k in ("domain","Domain") and isinstance(v,str): dom=v
                    else: walk(v)
        walk(d)
        if tok: return tok, dom or "www.workbuddy.cn", f
    raise SystemExit("no token")
token, domain, vf = load_token()
url = "https://copilot.tencent.com/v2/chat/completions"
tools = [{"type":"function","function":{"name":"sha256_file","description":"Return sha256 hex of a file on disk.",
          "parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}}]
body = {"model":"deepseek-v4.1-flash","stream":True,"max_tokens":500,"temperature":0.1,
    "messages":[{"role":"user","content":"Call sha256_file on path D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/o0_a5_dossier.md and then answer with the hash only."}],
    "tools":tools,"tool_choice":"auto"}
req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
    headers={"Authorization":"Bearer "+token,"Content-Type":"application/json",
             "Accept":"text/event-stream","x-client-platform":"web","X-Domain":domain})
try:
    with urllib.request.urlopen(req, timeout=240) as r:
        raw = r.read().decode("utf-8","replace")
except Exception as e:
    print("ERR", type(e).__name__, str(e)[:300]); sys.exit(0)
tc = [ln for ln in raw.splitlines() if '"tool_calls"' in ln]
print("total_sse_lines", len(raw.splitlines()), "tool_call_lines", len(tc))
print("\n".join(tc[:3])[:800])
print("TAIL", raw[-500:])
