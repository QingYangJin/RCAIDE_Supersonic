import json, hashlib
from pathlib import Path
root = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/cases/O0F")
a = root/"o0-final-baseline-r1-final"; b = root/"o0-final-baseline-wake16-final"
def h(p): return hashlib.sha256(p.read_bytes()).hexdigest()
for nm in ["o0-final-baseline-r1-final.polar","o0-final-baseline-wake16-final.polar",
           "o0-final-baseline-r1-final.vspaero","o0-final-baseline-wake16-final.vspaero",
           "o0-final-baseline-r1-final.history","o0-final-baseline-wake16-final.history",
           "o0-final-baseline-r1-final.lod","o0-final-baseline-wake16-final.lod"]:
    d = a if nm.startswith("o0-final-baseline-r1") else b
    p = d/nm
    print(nm, p.stat().st_size, h(p))
print("=== vspaero diff")
ta = (a/"o0-final-baseline-r1-final.vspaero").read_text(errors="replace").splitlines()
tb = (b/"o0-final-baseline-wake16-final.vspaero").read_text(errors="replace").splitlines()
import difflib
for line in difflib.unified_diff(ta, tb, "wake8", "wake16", lineterm="", n=1):
    print(line)
print("=== polar identical?", (a/"o0-final-baseline-r1-final.polar").read_bytes() == (b/"o0-final-baseline-wake16-final.polar").read_bytes())
