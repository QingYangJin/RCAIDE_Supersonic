
import json,urllib.request,ssl,glob
tok_files=glob.glob(r"C:/Users/pc/.dsh/workbuddy-vault/cn/*.json")
ctx=ssl.create_default_context()
def post(url,key,body,extra=None):
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":"Bearer "+key,**(extra or {})})
    try:
        with urllib.request.urlopen(req,timeout=60,context=ctx) as r: return r.status, r.read().decode("utf-8","replace")
    except Exception as e:
        m=str(e)
        try: m+=" BODY="+e.read().decode("utf-8","replace")[:300]
        except Exception: pass
        return None,m
for f in tok_files:
    d=json.load(open(f,encoding="utf-8"))
    keys=list(d.keys())
    tok=None; domain=None
    def walk(o):
        global tok,domain
        if isinstance(o,dict):
            for k,v in o.items():
                if k in ("accessToken","access_token") and isinstance(v,str): tok=v
                elif k in ("domain","Domain") and isinstance(v,str): domain=v
                else: walk(v)
    walk(d)
    print(f.split(chr(92))[-1], "keys",keys[:8],"tok_len",len(tok or ""),"domain",domain)
    if not tok: continue
    st,body=post("https://copilot.tencent.com/v2/chat/completions",tok,{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"reply with the single word OK"}],"max_tokens":16,"stream":False})
    print("  ->",st,(body or "")[:220].replace(chr(10)," "))
