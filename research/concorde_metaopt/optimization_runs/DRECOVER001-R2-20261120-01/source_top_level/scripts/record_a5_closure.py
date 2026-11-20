import json, hashlib, shutil
from pathlib import Path
WT=Path(r"D:/RCAIDE/.worktrees/drecover001-20261117")
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
src=Path(r"D:/RCAIDE/.recovery-local-restore/a5_reviewer/run_r2_closure_20261120/verdict.json")
dst=WT/"docs/evidence/drecover001/r2_a5_closure_verdict_20261120.json"
shutil.copyfile(src,dst)
meta=json.loads(Path(r"D:/RCAIDE/.recovery-local-restore/a5_reviewer/run_r2_closure_20261120/review_meta.json").read_text(encoding="utf-8"))
gate=json.loads((RUN/"r2_gate_record.json").read_text(encoding="utf-8"))
verdict=json.loads(dst.read_text(encoding="utf-8"))
gate["a5_closure"]={"verdict":verdict["verdict"],"pilot_disposition":verdict["pilot_disposition"],
 "model":verdict["model"],"reviewed_utc":verdict["reviewed_utc"],
 "dossier_sha256":verdict["dossier_sha256"],"tool_access":verdict["tool_access"],
 "human_signature":False,"conditions":verdict["conditions"],
 "verdict_path":str(dst),"verdict_sha256":hashlib.sha256(dst.read_bytes()).hexdigest(),
 "note":"Closure review PASS: C1-C5 closed; 14 matrix starts admissible; MAML only after per-case admission."}
gate["further_starts_blocked_until_a5_closure_review"]=False
gate["maml_started"]=False
gate["next_step"]="Run 14 matrix cases sequentially with per-case ledger, then audit/admit each success; MAML only after admissions."
(RUN/"r2_gate_record.json").write_text(json.dumps(gate,indent=2),encoding="utf-8")
print(json.dumps({"closure_verdict":verdict["verdict"],"closure_sha256":gate["a5_closure"]["verdict_sha256"],"further_starts_blocked":gate["further_starts_blocked_until_a5_closure_review"],"meta":meta},indent=2))
