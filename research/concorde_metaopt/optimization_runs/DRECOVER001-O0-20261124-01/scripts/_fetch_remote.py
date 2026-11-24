import os,subprocess,sys
sys.path.insert(0,r"D:/RCAIDE/.recovery-local-restore")
env=dict(os.environ); env["GIT_CWD"]=r"D:/RCAIDE/.worktrees/dreal005-20261124"; env["GITHUB_IP"]="140.82.114.4"
p=subprocess.run([r"D:/Anaconda/envs/RCAIDE/python.exe", r"D:/RCAIDE/.recovery-local-restore/git_via_proxy.py", "fetch", "{URL}", "refs/heads/research/dreal005-conditional-meta-real-optimization:refs/remotes/origin/research/dreal005-conditional-meta-real-optimization"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=900)
print(p.returncode); print(p.stdout[-1500:]); print(p.stderr[-1500:])
