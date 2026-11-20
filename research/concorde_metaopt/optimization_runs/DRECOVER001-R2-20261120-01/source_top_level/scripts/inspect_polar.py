import json, sys
from pathlib import Path
REPO = Path(r"D:/RCAIDE/.worktrees/drecover001-20261117")
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.dreal001.geometry import polar_parser
p = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases/baseline-coarse/baseline_coarse.polar")
rec = polar_parser.parse_polar_file(p)
print("header", rec["header"])
print("invalid_indices", rec["invalid_row_indices"])
for i,row in enumerate(rec["rows"]):
    print(i, {k: row.get(k) for k in ("Mach","AoA","Beta","CLtot","CDtot","CDi","CLi","CMtot")}, "invalid", row.get("_invalid_tokens"))
