import base64, hashlib, json, os, re, subprocess, time, urllib.request, urllib.error
ROOT=r"D:/RCAIDE/.worktrees/drecover001-20261117"
OWNER,REPO="QingYangJin","RCAIDE_Supersonic"
BRANCH="recovery/drecover001-20261117"
cred=open(r"C:/Users/pc/.dsh/.credentials.yaml",encoding="utf-8").read()
TOK=re.search(r"GITHUB_TOKEN:\s*([^\s]+)",cred).group(1).strip().strip('"').strip("'")
API="https://api.github.com"
def req(path,method="GET",body=None):
    data=None if body is None else json.dumps(body).encode()
    r=urllib.request.Request(API+path,data=data,method=method,headers={"Authorization":"Bearer "+TOK,"Accept":"application/vnd.github+json","User-Agent":"rcaide-r2","Content-Type":"application/json"})
    with urllib.request.urlopen(r,timeout=180) as resp:
        raw=resp.read().decode(); return resp.status,(json.loads(raw) if raw else {})
s,ref=req("/repos/%s/%s/git/ref/heads/%s"%(OWNER,REPO,BRANCH))
assert s==200,(s,ref)
BASE=ref["object"]["sha"]
s,base=req("/repos/%s/%s/commits/%s"%(OWNER,REPO,BASE)); assert s==200,(s,base)
BASE_TREE=base["commit"]["tree"]["sha"]
local_head=subprocess.run(["git","-C",ROOT,"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
assert local_head==BASE,(local_head,BASE)
z=subprocess.run(["git","status","--porcelain=v1","-z","--untracked-files=all"],cwd=ROOT,capture_output=True).stdout.split(b"\x00")
entries=[]
for item in z:
    if not item: continue
    line=item.decode("utf-8","surrogateescape"); code,path=line[:2],line[3:]
    fp=os.path.join(ROOT,path.replace("/",os.sep))
    if not os.path.isfile(fp): continue
    if code.strip()=="M":
        ls=subprocess.run(["git","ls-files","-s","--",path],cwd=ROOT,capture_output=True,text=True).stdout.strip()
        mode=ls.split()[0] if ls else "100644"
    else: mode="100644"
    entries.append({"path":path,"mode":mode,"file":fp})
print("ENTRIES",len(entries),[e["path"] for e in entries],flush=True)
tree=[]
for e in entries:
    data=open(e["file"],"rb").read()
    local=hashlib.sha1(b"blob %d\x00"%len(data)+data).hexdigest()
    s,b=req("/repos/%s/%s/git/blobs"%(OWNER,REPO),"POST",{"content":base64.b64encode(data).decode(),"encoding":"base64"})
    assert s==201 and b.get("sha")==local,(e["path"],s,b)
    tree.append({"path":e["path"],"mode":e["mode"],"type":"blob","sha":local})
    print("BLOB",e["path"],local,len(data),flush=True)
s,b=req("/repos/%s/%s/git/trees"%(OWNER,REPO),"POST",{"base_tree":BASE_TREE,"tree":tree}); assert s==201,(s,b)
NEW_TREE=b["sha"]
now=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
ident={"name":"QingYangJin","email":"118662522+QingYangJin@users.noreply.github.com","date":now}
msg="\n".join([
 "R2 代码冻结：flow_conditions 与 Ew=inf 准入修复、全量零物理预检 248 项通过",
 "",
 "- code freeze R2FREEZE-6bdfe74e7f41b664（19 文件）；full preflight run_id=DRECOVER001-SOFTWARE-20261120T065735Z，248 tests / 0 failed / 0 error / 0 skipped，physical_solver_starts_actual=0。",
 "- openvsp_model.py 新增可选 flow_conditions（默认路径与 baseline 逐字节等价，14 个 matrix deck 168 项检查 0 失败）。",
 "- raw_verification.py 仅容忍诊断列 Ew 的 ±inf；Ew NaN 与所有核心非有限值仍 fatal，新增回归测试。",
 "- A5 deepseek-flash 对 3 个 pilot starts 给出 CHANGES_REQUIRED / RATIFIED_WITH_CONDITIONS；条件 C1–C5 已在 r2_gate_record.json 闭合，待 closure review 后恢复真实 starts。",
 "- 未启动 MAML；未宣称泛化；未覆盖旧 Issue #9/#10 数据。",
])
s,b=req("/repos/%s/%s/git/commits"%(OWNER,REPO),"POST",{"message":msg,"tree":NEW_TREE,"parents":[BASE],"author":ident,"committer":ident}); assert s==201,(s,b)
NEW=b["sha"]
s,b=req("/repos/%s/%s/git/refs/heads/%s"%(OWNER,REPO,BRANCH),"PATCH",{"sha":NEW,"force":False}); assert s==200,(s,b)
print("PUSHED",NEW,"tree",NEW_TREE,"base",BASE,"files",len(tree),flush=True)
json.dump({"base":BASE,"base_tree":BASE_TREE,"new_commit":NEW,"new_tree":NEW_TREE,"files":len(tree),"paths":[e["path"] for e in entries]},open(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/gh_push_r2_code_freeze.json","w"),indent=2)
