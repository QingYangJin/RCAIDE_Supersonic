
import json, math
from pathlib import Path
EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/wave")
ROOT = "D:/Program Files/OpenVSP/OpenVSP-3.26.1-win64-Python3.9/OpenVSP-3.26.1-win64"
BASE = {"Mach": 2.02, "NumRotSects": 36, "NumSlices": 200, "Set": 1, "SymmFlag": 1}
cases = {
    "WAVE-01": ("baseline", BASE),
    "WAVE-02": ("baseline_wingbody", BASE),
    "WAVE-03": ("w03_plus1deg", BASE),
    "WAVE-04": ("w03_plus1deg_wingbody", BASE),
    "WAVE-05": ("baseline_wingbody", {"Mach": 2.02, "NumRotSects": 72, "NumSlices": 800, "Set": 1, "SymmFlag": 1}),
}
for case, (src, inputs) in cases.items():
    req = json.loads((EXT / src / "request.json").read_text(encoding="utf-8"))
    req["openvsp_root"] = ROOT
    req["analysis"] = {"name": "WaveDrag", "inputs": inputs}
    d = EXT / case
    d.mkdir(parents=True, exist_ok=True)
    (d / "request.json").write_text(json.dumps(req, indent=2), encoding="utf-8")
    print(case, "components", [c["name"] for c in req["components"]], "inputs", inputs)
