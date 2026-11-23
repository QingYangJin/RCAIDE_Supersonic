import json
from pathlib import Path
p=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01/p2_dataset/p2_dataset.json")
d=json.loads(p.read_text(encoding="utf-8"))
for t in d["tasks"]:
    print(t["task_id"], t["split"], "support", t["support"], "query", t["query"])
print("---")
for aid,src in sorted(d["sources"].items()):
    print(aid, "|", src["run_id"], "|", src["historical_task_id"], "|", Path(src["case_dir"]).name)
