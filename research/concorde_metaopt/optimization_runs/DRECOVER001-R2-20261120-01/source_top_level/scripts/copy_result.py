import json, shutil, hashlib
from pathlib import Path
src = Path("D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/real_maml_result.json")
dst = Path("D:/RCAIDE/.worktrees/drecover001-20261117/docs/evidence/drecover001/real_maml_result_20261120.json")
dst.write_bytes(src.read_bytes())
print(hashlib.sha256(dst.read_bytes()).hexdigest(), dst.stat().st_size)
