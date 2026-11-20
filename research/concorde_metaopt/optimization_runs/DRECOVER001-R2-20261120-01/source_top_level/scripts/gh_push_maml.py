import base64, hashlib, json, os, re, subprocess, time, urllib.request
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
s,ref=req("/repos/%s/%s/git/ref/heads/%s"%(OWNER,REPO,BRANCH)); assert s==200,(s,ref)
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
 "R2 真实标签与 K=1 FOMAML：9 条准入标签、真实训练入口与探索性结果",
 "",
 "- 真实 VSPAERO 批次封顶：24/24 starts（23 完成 + 1 次 m240-d01 外层超时中断），645 internal cases，0 retries，parallel 1。",
 "- 10 张准入证书；去重后 9 行真实 MetaDataset（4 任务：M160/M202 train、M180 val、M240 test），标签仍为 LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED。",
 "- 新增 real_training.py：RealFOMALMTrainer 只接受铸造证书数据，RealAdaptationRunner 只接受真实 support；守卫测试 2 passed；未重跑全量 preflight。",
 "- 一次 K=1 探索性 FOMAML（2 train tasks，20 steps）：val adapted MSE 1.945e8 vs zero-shot 1.720e8（更差）；test 单次 MSE 2.495e9 vs 3.031e9（更好）；n=1 query/task，不宣称泛化。",
 "- 本入口在 A5 repair 冻结之后新增，未经 A5 审查；solver_runner.build_evaluation 的 baseline-q 缺陷尚未修复，已在证据中披露。",
])
s,b=req("/repos/%s/%s/git/commits"%(OWNER,REPO),"POST",{"message":msg,"tree":NEW_TREE,"parents":[BASE],"author":ident,"committer":ident}); assert s==201,(s,b)
NEW=b["sha"]
s,b=req("/repos/%s/%s/git/refs/heads/%s"%(OWNER,REPO,BRANCH),"PATCH",{"sha":NEW,"force":False}); assert s==200,(s,b)
print("PUSHED",NEW,"tree",NEW_TREE,"base",BASE,"files",len(tree),flush=True)
json.dump({"base":BASE,"base_tree":BASE_TREE,"new_commit":NEW,"new_tree":NEW_TREE,"files":len(tree),"paths":[e["path"] for e in entries]},open(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/gh_push_maml.json","w"),indent=2)
