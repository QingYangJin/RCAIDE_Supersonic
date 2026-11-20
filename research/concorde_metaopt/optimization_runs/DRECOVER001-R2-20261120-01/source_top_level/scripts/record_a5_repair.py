import json, pathlib, hashlib, shutil
src=pathlib.Path(r"D:/RCAIDE/.recovery-local-restore/a5_reviewer/run_r2_repair2_20261120/verdict.json")
dst=pathlib.Path(r"D:/RCAIDE/.worktrees/drecover001-20261117/docs/evidence/drecover001/r2_a5_repair_verdict_20261120.json")
shutil.copyfile(src,dst)
v=json.loads(dst.read_text())
print(json.dumps({k:v[k] for k in ("verdict","repair_starts_authorized","k_shot_authorized","reviewed_utc","dossier_sha256")},indent=2))
print("verdict_sha256", hashlib.sha256(dst.read_bytes()).hexdigest())
# update gate record
gr=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/r2_gate_record.json")
g=json.loads(gr.read_text())
g["a5_repair_authorization"]={
  "verdict":"PASS","repair_starts_authorized":True,"k_shot_authorized":"K=1",
  "reviewed_utc":v["reviewed_utc"],"model":v["model"],
  "dossier_path":v["dossier_path"],"dossier_sha256":v["dossier_sha256"],
  "verdict_path":str(dst),"verdict_sha256":hashlib.sha256(dst.read_bytes()).hexdigest(),
  "scope":"only the seven B01R repair case ids; total physical starts 24/24; no retries; K=1 exploratory MAML",
  "nonhuman_signature":True,"tool_access":v["tool_access"]}
g["further_starts_blocked_until_a5_closure_review"]=False
g["maml_started"]=False
gr.write_text(json.dumps(g,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print("gate_record_sha256", hashlib.sha256(gr.read_bytes()).hexdigest())
