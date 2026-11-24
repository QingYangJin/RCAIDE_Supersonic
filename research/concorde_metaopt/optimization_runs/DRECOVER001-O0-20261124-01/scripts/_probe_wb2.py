
import json,urllib.request,ssl,glob
ctx=ssl.create_default_context()
f=sorted(glob.glob(r"C:/Users/pc/.dsh/workbuddy-vault/cn/*.json"))[0]
d=json.load(open(f,encoding="utf-8"))
tok=d["auth"]["accessToken"] if isinstance(d.get("auth"),dict) else None
if tok is None:
    tok=[v for v in json.dumps(d).split('"accessToken":"')[1:]][0].split('"')[0]
body={"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"reply with the single word OK"}],"max_tokens":32,"stream":True}
req=urllib.request.Request("https://copilot.tencent.com/v2/chat/completions",data=json.dumps(body).encode(),
  headers={"Content-Type":"application/json","Authorization":"Bearer "+tok,"Accept":"text/event-stream","x-client-platform":"web","X-Domain":d.get("account",{}).get("domain","www.workbuddy.cn")})
try:
    with urllib.request.urlopen(req,timeout=90,context=ctx) as r:
        data=r.read().decode("utf-8","replace")
    print("OK", data[:1500])
except Exception as e:
    m=str(e)
    try: m+=" BODY="+e.read().decode("utf-8","replace")[:500]
    except Exception: pass
    print("FAIL",m[:800])
