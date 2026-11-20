import re, subprocess
from pathlib import Path
cred=Path(r"C:/Users/pc/.dsh/.credentials.yaml").read_text(encoding="utf-8")
tok=re.search(r"GITHUB_TOKEN:\s*([^\s]+)",cred).group(1).strip().strip('"').strip("'")
url="https://x-access-token:%s@github.com/QingYangJin/RCAIDE_Supersonic.git"%tok
root=r"D:/RCAIDE/.worktrees/drecover001-20261117"
for cmd in [
 ["git","-c","credential.helper=","-c","http.sslBackend=openssl","fetch","--depth=1",url,"recovery/drecover001-20261117"],
 ["git","update-ref","refs/heads/recovery/drecover001-20261117","FETCH_HEAD"],
 ["git","reset","--mixed","HEAD"],
]:
    p=subprocess.run(cmd,cwd=root,capture_output=True,text=True)
    print(" ".join(cmd[:3]),"exit",p.returncode)
    if p.stdout: print(p.stdout[:500])
    if p.stderr: print("ERR",p.stderr[:500])
    if p.returncode: raise SystemExit(p.returncode)
head=subprocess.run(["git","rev-parse","HEAD"],cwd=root,capture_output=True,text=True,check=True).stdout.strip()
status=subprocess.run(["git","status","--porcelain"],cwd=root,capture_output=True,text=True,check=True).stdout.strip()
print("HEAD",head); print("DIRTY",repr(status))
