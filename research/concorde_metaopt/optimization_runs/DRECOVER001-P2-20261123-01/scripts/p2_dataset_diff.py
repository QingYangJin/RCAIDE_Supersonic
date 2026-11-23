
"""Itemized diff between the pre-fix (39 rows) and post-fix (44 rows) P2 datasets."""
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
REL = "research/concorde_metaopt/optimization_runs/DRECOVER001-P2-20261123-01/p2_dataset/p2_dataset.json"

old_bytes = subprocess.run(["git", "-C", str(REPO), "show", "b402db4:" + REL],
                           capture_output=True, check=True).stdout
old = json.loads(old_bytes.decode("utf-8"))
new_bytes = (RUN / "p2_dataset" / "p2_dataset.json").read_bytes()
new = json.loads(new_bytes.decode("utf-8"))

def task_map(ds):
    return {t["task_id"]: {"split": t["split"], "support": t["support"], "query": t["query"],
                           "support_designs": list(t.get("support_designs") or []),
                           "query_designs": list(t.get("query_designs") or [])}
            for t in ds["tasks"]}

ot, nt = task_map(old), task_map(new)
added_ids = sorted(set(new["sources"]) - set(old["sources"]))
removed_ids = sorted(set(old["sources"]) - set(new["sources"]))
added_rows = []
for aid in added_ids:
    src = new["sources"][aid]
    hist = src.get("historical_task_id")
    task = next((t for t, v in nt.items() if hist == t or hist in (new.get("task_aliases", {}).get(t) or [])), None)
    partition = None
    if task:
        design = src.get("design_id")
        if design in nt[task]["support_designs"]:
            partition = "support"
        elif design in nt[task]["query_designs"]:
            partition = "query"
    added_rows.append({"admission_id": aid, "run_id": src.get("run_id"),
                       "historical_task_id": hist, "canonical_task": task, "partition": partition})

per_task = []
for task in sorted(set(ot) | set(nt)):
    o = ot.get(task, {}); n = nt.get(task, {})
    if o.get("support") == n.get("support") and o.get("query") == n.get("query"):
        continue
    per_task.append({"task_id": task, "split": n.get("split"),
                     "support_before": o.get("support"), "support_after": n.get("support"),
                     "query_before": o.get("query"), "query_after": n.get("query")})

diff = {
    "schema": "dreal004.p2_dataset_diff.v1",
    "pre_fix": {"source": "git b402db4:" + REL,
                "sha256": hashlib.sha256(old_bytes).hexdigest(),
                "rows": old["rows"], "certificates": old["certificates"],
                "excluded_count": len(old["excluded"])},
    "post_fix": {"source": "working tree p2_dataset/p2_dataset.json",
                 "sha256": hashlib.sha256(new_bytes).hexdigest(),
                 "rows": new["rows"], "certificates": new["certificates"],
                 "excluded_count": len(new["excluded"])},
    "added_admission_ids": added_ids,
    "removed_admission_ids": removed_ids,
    "added_rows": added_rows,
    "per_task_changes": per_task,
    "cause": "R2 low-priority query records for M180 d02 / M202 d02 conflicted with P2 supplement support records on the same design; the old dedupe branch dropped both sides, the fix drops only the lower-priority record",
    "physical_effect": "none: the 16 real starts and 16 admitted labels were already produced before this dataset-builder fix",
}
p = RUN / "p2_dataset" / "p2_dataset_diff.json"
p.write_text(json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({k: diff[k] for k in ("pre_fix", "post_fix", "added_admission_ids", "per_task_changes")}, ensure_ascii=False, indent=1))
print("sha256", hashlib.sha256(p.read_bytes()).hexdigest())
