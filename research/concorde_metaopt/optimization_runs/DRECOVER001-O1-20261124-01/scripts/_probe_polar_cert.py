
import json
from pathlib import Path
P = Path("D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/cases/O0F")
def parse_polar(path):
    rows=[]; cols=None
    for line in path.read_text(encoding="utf-8",errors="replace").splitlines():
        f=line.split()
        if cols is None:
            if f and f[0]=="Beta" and "AoA" in f and "CDi" in f:
                cols=f
            continue
        if len(f)==len(cols):
            try: rows.append(dict(zip(cols,[float(x) for x in f])))
            except ValueError: pass
    return rows
for name in ["o0-final-baseline-r1b-final","o0-final-best-r1-final"]:
    d=P/name
    pol=sorted(d.glob("*.polar"))
    rows=parse_polar(pol[0])
    print(name, "rows", len(rows), "alpha", rows[0]["AoA"], rows[-1]["AoA"])
    cert=json.loads((d/"admission_certificate.json").read_text(encoding="utf-8"))
    print("  cert keys", list(cert.keys())[:20])
    for k in ("alpha_deg","cl","cdi","q_pa","sref_m2","di_n","lift_n","lift_target_n"):
        if k in cert: print("   ",k,cert[k])
