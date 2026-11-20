import json, re, sys, urllib.request
from pathlib import Path
cred=Path(r"C:/Users/pc/.dsh/.credentials.yaml").read_text(encoding="utf-8")
tok=re.search(r"GITHUB_TOKEN:\s*([^\s]+)",cred).group(1).strip().strip('"').strip("'")
api="https://api.github.com"; owner,repo="QingYangJin","RCAIDE_Supersonic"
body=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/issue11_link_comment_20261120.md").read_text(encoding="utf-8")
def req(path,method="GET",payload=None):
    data=None if payload is None else json.dumps(payload).encode("utf-8")
    r=urllib.request.Request(api+path,data=data,method=method,headers={"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","User-Agent":"rcaide-r2-link","Content-Type":"application/json"})
    with urllib.request.urlopen(r,timeout=120) as resp:
        raw=resp.read().decode("utf-8"); return resp.status,(json.loads(raw) if raw else {})
s,comments=req("/repos/%s/%s/issues/11/comments?per_page=100"%(owner,repo))
for c in comments:
    if "7034439349" in (c.get("body") or ""):
        print("ALREADY_POSTED",c.get("id"),c.get("html_url")); sys.exit(0)
s,res=req("/repos/%s/%s/issues/11/comments"%(owner,repo),"POST",{"body":body})
print("POSTED",s,res.get("id"),res.get("html_url"),len(res.get("body") or ""))
