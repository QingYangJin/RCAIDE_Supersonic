import hashlib, json
from pathlib import Path
root = Path("D:/RCAIDE/.worktrees/drecover001-20261117")
paths = [
 "research/concorde_metaopt/dreal001/meta/real_training.py",
 "research/concorde_metaopt/tests/test_recovery_real_training.py",
 "docs/evidence/drecover001/real_maml_result_20261120.json",
 "docs/evidence/drecover001/real_maml_experiment_20261120.md",
]
files = []
for rel in paths:
    p = root / rel
    files.append({"path": rel, "bytes": p.stat().st_size,
                  "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
payload = {
 "schema": "drecover001.r2_followup_code_freeze.v1",
 "freeze_id": "R2-FOLLOWUP-20261120-MAML",
 "base_commit": "2273024eeb5eae634b11fcebcee16376c82e409e",
 "purpose": "real K=1 FOMAML entry and exploratory nine-label result",
 "files": files,
 "preflight_after_followup": "NOT_RERUN; guard tests 2 passed",
 "a5_review": "NOT_PERFORMED for follow-up entry; disclosed, not claimed as A5-reviewed",
 "physical_solver_starts_actual": 0,
}
out = root / "docs/evidence/drecover001/r2_followup_code_freeze_20261120.json"
out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"out": str(out), "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "files": files}, indent=2))
