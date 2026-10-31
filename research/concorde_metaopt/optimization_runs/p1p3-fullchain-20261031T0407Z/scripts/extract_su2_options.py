import re, json, subprocess
from pathlib import Path
p = Path(r"D:/Program Files/SU2/SU2-v8.5.0-win64-mpi/win64-mpi/bin/SU2_CFD.exe")
data = p.read_bytes()
print("bytes", len(data))
toks = set(re.findall(rb"[A-Z][A-Z0-9_]{3,}", data))
toks = sorted(t.decode() for t in toks)
print("tokens", len(toks))
interesting = [t for t in toks if any(t.startswith(pre) for pre in ("CONV_","INCREMENTAL","CFL_","LINEAR_","OUTPUT_","SCREEN_","HISTORY_","MARKER_","MUSCL","SLOPE","MGLEVEL","MG_","NUM_METHOD","NUM_","TIME_","ITER","MESH_","RESTART_","REF_","SURFACE_","VOLUME_","AERO_","LIFT_","DRAG_","MACH_","AOA","SIDESLIP","FREESTREAM_","REYNOLDS_","GAMMA_","GAS_","FLUID_","REF_DIMENSIONALIZATION"))]
print(json.dumps(interesting, indent=0))
Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/lead/su2_tokens.json").write_text(json.dumps(toks, indent=0))
