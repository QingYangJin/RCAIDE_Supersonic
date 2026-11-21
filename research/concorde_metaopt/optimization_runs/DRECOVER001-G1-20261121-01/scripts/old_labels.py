
import json
from pathlib import Path
for d in Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases").iterdir():
    c=d/"admission_certificate.json"
    if c.exists():
        j=json.loads(c.read_text(encoding="utf-8"))
        print(d.name, j.get("status"), j.get("alpha_deg"), j.get("cl"), j.get("cdi"), j.get("di_n"))
