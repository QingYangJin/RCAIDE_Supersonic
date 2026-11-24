
import json, glob, sys, urllib.request, yaml
from pathlib import Path
vault = Path(r"C:/Users/pc/.dsh/workbuddy-vault/cn")
cands = sorted(vault.glob("*.json"))
data = json.loads(cands[0].read_text(encoding="utf-8"))
tok = data.get("accessToken") or data.get("access_token")
dom = data.get("domain") or data.get("xDomain")
url = "https://copilot.tencent.com/v2/chat/completions"
tools = [{"type":"function","function":{"name":"sha256_file","description":"sha256 of a file","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}}]
body = {"model":"deepseek-v4.1-flash","stream":True,"max_tokens":400,"temperature":0.1,
        "messages":[{"role":"user","content":"Use the tool sha256_file on path D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/o0_a5_dossier.md, then report the hash."}],
        "tools":tools}
req = urllib.request.Request(url, data=json.dumps(body).encode(),
    headers={"Content-Type":"application/json","Authorization":"Bearer "+str(tok),
             "x-client-platform":"web","X-Domain":str(dom or "")})
print("domain", dom, "vault", cands[0].name)
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read().decode("utf-8", "replace")
except Exception as e:
    print("ERR", type(e).__name__, str(e)[:400]); sys.exit(0)
hits = [ln for ln in raw.splitlines() if '"tool_calls"' in ln or '"function"' in ln or 'sha256' in ln]
print("lines", len(raw.splitlines()))
print("\n".join(hits[:8]))
print("TAIL:", raw[-600:])
