
import json
from pathlib import Path
BASE = Path("D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
def parse_polar(path):
    rows=[]; cols=None
    for line in path.read_text(encoding="utf-8",errors="replace").splitlines():
        f=line.split()
        if cols is None:
            if f and f[0]=="Beta" and "AoA" in f and "CDi" in f: cols=f
            continue
        if len(f)==len(cols):
            try: rows.append(dict(zip(cols,[float(x) for x in f])))
            except ValueError: pass
    return rows
for case in ["o0-d00-coarse","o0-d00-refine","o0-d10-coarse","o0-d10-refine"]:
    d = BASE/"cases/B02"/case
    pols = sorted(d.glob("*.polar"))
    if not pols:
        print(case, "NO POLAR", [p.name for p in d.iterdir()][:12]); continue
    rows = parse_polar(pols[0])
    print(case, "rows", len(rows), "AoA", round(rows[0]["AoA"],4), "->", round(rows[-1]["AoA"],4),
          "CL", round(rows[0]["CLtot"],4), "->", round(rows[-1]["CLtot"],4))
# O1 arm polars
O1 = Path("D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190")
for arm in ["SUPPORT","ARM_SOBOL_BO","ARM_COND_SUPERVISED_KSHOT_BO","ARM_COND_FOMAML_KSHOT_BO"]:
    for d in sorted((O1/arm).iterdir()):
        if not d.is_dir(): continue
        pols = sorted(d.glob("*.polar"))
        if pols:
            rows = parse_polar(pols[0])
            print(arm, d.name, len(rows), round(rows[0]["AoA"],3), round(rows[-1]["AoA"],3))
