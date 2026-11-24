import json,urllib.request,os
tok=None
for line in open(r"C:/Users/pc/.dsh/.credentials.yaml",encoding="utf-8",errors="replace"):
    s=line.strip()
    if s.startswith("GITHUB_TOKEN:"):
        tok=s.split(":",1)[1].strip().strip('"').strip("'")
def get(u):
    r=urllib.request.Request(u,headers={"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","User-Agent":"dsh"})
    return json.load(urllib.request.urlopen(r,timeout=60))
cs=get("https://api.github.com/repos/QingYangJin/RCAIDE_Supersonic/issues/15/comments?per_page=100")
open(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/scripts/_i15_comment.txt","w",encoding="utf-8").write(cs[0]["body"])
print("written",len(cs[0]["body"]))
