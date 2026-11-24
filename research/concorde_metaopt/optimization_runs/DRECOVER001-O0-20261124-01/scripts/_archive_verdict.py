
import json, shutil
from pathlib import Path
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
H = RUN / "a5_review/history"; H.mkdir(parents=True, exist_ok=True)
v = json.loads((RUN/"a5_review/verdict.json").read_text(encoding="utf-8"))
tag = v["reviewed_utc"].replace("-","").replace(":","")
dest = H / ("verdict_%s.json" % tag)
shutil.copyfile(RUN/"a5_review/verdict.json", dest)
print("archived", dest.name, "dossier", v["dossier_sha256"][:16], "verdict", v["verdict"])
for p in sorted(H.glob("verdict_*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    print(" ", p.name, d["verdict"], d["dossier_sha256"][:16], "findings", len(d.get("findings", [])))
