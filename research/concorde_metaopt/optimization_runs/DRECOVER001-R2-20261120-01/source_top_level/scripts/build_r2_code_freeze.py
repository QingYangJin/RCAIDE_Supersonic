import json, hashlib, subprocess
from pathlib import Path
from datetime import datetime, timezone

WT = Path(r"D:/RCAIDE/.worktrees/drecover001-20261117")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rec(p): return {"path": str(p), "bytes": Path(p).stat().st_size, "sha256": sha(p)}
source = [
 WT/"research/concorde_metaopt/dreal001/geometry/openvsp_model.py",
 WT/"research/concorde_metaopt/dreal001/meta/raw_verification.py",
 WT/"research/concorde_metaopt/tests/test_recovery_real_admission.py",
]
scripts = [
 RUN/"scripts/build_task_case.py", RUN/"scripts/build_matrix_inputs.py",
 RUN/"scripts/verify_matrix_inputs.py", RUN/"scripts/verify_flow_default_equivalence.py",
 RUN/"scripts/build_pilot_ledger.py", RUN/"scripts/build_pilot_label_status.py",
 RUN/"scripts/audit_real_case.py", RUN/"scripts/admit_case.py",
]
evidence = [
 RUN/"authorization.json", RUN/"pilot_ledger.json", RUN/"pilot_label_status.json",
 RUN/"matrix_input_verification.json", RUN/"flow_default_equivalence/verification.json",
 RUN/"preflight_r2/recovery_preflight_receipt.json",
 WT/"docs/evidence/drecover001/r2_a5_review_dossier_20261120.md",
 Path(r"D:/RCAIDE/.recovery-local-restore/a5_reviewer/run_r2_20261120/verdict.json"),
]
files = [rec(p) for p in source+scripts+evidence]
canon = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
freeze_id = "R2FREEZE-" + hashlib.sha256(canon).hexdigest()[:16]
head = subprocess.run(["git","-C",str(WT),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
dirty = subprocess.run(["git","-C",str(WT),"status","--porcelain=v1","--untracked-files=all"],capture_output=True,text=True,check=True).stdout.splitlines()
push = json.loads((RUN/"gh_push_r2_code_freeze.json").read_text(encoding="utf-8"))
freeze = {"schema":"drecover001.r2_code_freeze.v1","freeze_id":freeze_id,
 "generated_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
 "git_head":head,"git_head_at_freeze":"0effd7628774c8ee61468627c7af446b21591705",
 "remote_commit":push["new_commit"],"remote_tree":push["new_tree"],
 "remote_parent":push["base"],"remote_branch":"recovery/drecover001-20261117",
 "dirty_paths":len(dirty),"dirty_list":dirty,
 "files":files,"file_count":len(files),
 "physical_solver_starts":0,
 "note":"Freeze binds exact source, scripts, authorization and A5 evidence bytes used for the R2 batch. The three source files and the A5 dossier were committed as the remote commit above; the worktree is clean at that commit."}
(RUN/"r2_code_freeze.json").write_text(json.dumps(freeze,indent=2),encoding="utf-8")
print(json.dumps({"freeze_id":freeze_id,"git_head":head,"remote_commit":push["new_commit"],"remote_tree":push["new_tree"],"dirty_paths":len(dirty),"file_count":len(files)},indent=2))
