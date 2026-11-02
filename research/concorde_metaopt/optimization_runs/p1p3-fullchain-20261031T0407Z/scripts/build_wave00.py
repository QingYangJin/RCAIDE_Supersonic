
import json, math
from pathlib import Path
EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/wave")
L, V = 10.0, 5.0
C = 16.0 * V / (3.0 * math.pi * L)
n = 81
xs = [round(L * i / (n - 1), 9) for i in range(n)]
areas = [round(C * (4.0 * (x / L) * (1.0 - x / L)) ** 1.5, 12) for x in xs]
d = EXT / "WAVE-00"
d.mkdir(parents=True, exist_ok=True)
req = {
    "openvsp_root": "D:/Program Files/OpenVSP/OpenVSP-3.26.1-win64-Python3.9/OpenVSP-3.26.1-win64",
    "components": [],
    "analysis": {"name": "EmintonLord", "inputs": {"Area_vec": areas, "X_vec": xs}},
    "benchmark": {"body": "sears_haack", "L_m": L, "V_m3": V, "theory_D_over_q": 128.0 * V * V / (math.pi * L ** 4),
                  "S_max_m2": max(areas), "n_points": n},
}
(d / "request.json").write_text(json.dumps(req, indent=2), encoding="utf-8")
print("wrote", d / "request.json")
