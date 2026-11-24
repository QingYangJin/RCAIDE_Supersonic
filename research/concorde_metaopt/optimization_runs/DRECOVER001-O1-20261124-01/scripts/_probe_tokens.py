import glob, json, urllib.request, urllib.error
from pathlib import Path

def walk(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("accessToken", "access_token") and isinstance(v, str) and len(v) > 200:
                out["tok"] = v
            elif k in ("domain", "Domain") and isinstance(v, str):
                out["dom"] = v
            else:
                walk(v, out)
    elif isinstance(o, list):
        for v in o:
            walk(v, out)

for f in sorted(glob.glob(r"C:/Users/pc/.dsh/workbuddy-vault/cn/*.json")):
    d = json.loads(Path(f).read_text(encoding="utf-8"))
    out = {}
    walk(d, out)
    tok = out.get("tok")
    dom = out.get("dom") or "www.workbuddy.cn"
    if not tok:
        print(f, "NO TOKEN")
        continue
    payload = {"model": "deepseek-v4.1-flash",
               "messages": [{"role": "user", "content": "reply with the single word ok"}],
               "max_tokens": 8, "stream": True}
    req = urllib.request.Request("https://copilot.tencent.com/v2/chat/completions",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json",
                 "Accept": "text/event-stream", "x-client-platform": "web", "X-Domain": dom})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            print(f, dom, "HTTP", resp.status, len(resp.read()))
    except urllib.error.HTTPError as exc:
        print(f, dom, "HTTPError", exc.code, exc.read()[:200])
    except Exception as exc:
        print(f, dom, "ERR", type(exc).__name__, str(exc)[:200])
