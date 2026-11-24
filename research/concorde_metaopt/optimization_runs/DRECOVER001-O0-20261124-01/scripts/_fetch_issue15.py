
import json,sys,urllib.request
tok=None
for line in open(r"C:/Users/pc/.dsh/.credentials.yaml",encoding="utf-8",errors="replace"):
    s=line.strip()
    if s.startswith("GITHUB_TOKEN:"):
        tok=s.split(":",1)[1].strip().strip('"').strip("'")
import os
if not tok: tok=os.environ.get("GITHUB_TOKEN")
def get(u):
    r=urllib.request.Request(u,headers={"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","User-Agent":"dsh"})
    return json.load(urllib.request.urlopen(r,timeout=60))
cs=get("https://api.github.com/repos/QingYangJin/RCAIDE_Supersonic/issues/15/comments?per_page=100")
print("n_comments",len(cs))
for c in cs:
    print("----",c["id"],c["created_at"],c["user"]["login"],len(c["body"]))
    print(c["body"][:1200])
