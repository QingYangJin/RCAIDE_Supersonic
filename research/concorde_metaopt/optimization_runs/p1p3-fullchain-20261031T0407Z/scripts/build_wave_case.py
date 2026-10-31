
import json, os, sys
from pathlib import Path
REPO = Path("D:/RCAIDE")
os.chdir(REPO)
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.aircraft.design_space import load_design_space
from research.concorde_metaopt.aircraft.geometry_builder import build_geometry_from_design_space
from research.concorde_metaopt.aircraft.openvsp_check import build_openvsp_request

EXT = Path("C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
CONFIG = "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"

def geom_for(overrides):
    space = load_design_space(CONFIG)
    vec = list(space.baseline_vector())
    names = list(space.variable_ids) if hasattr(space, "variable_ids") else [v.id for v in space.variables]
    for k, v in overrides.items():
        idx = names.index(k)
        vec[idx] = float(v)
    return space, build_geometry_from_design_space(space, vec)

cases = {"baseline": {}, "w03_plus1deg": {"W03": 68.0}}
out = {}
for name, ov in cases.items():
    space, geom = geom_for(ov)
    for variant, components in (("wing", ("main_wing",)), ("wingbody", ("main_wing", "fuselage"))):
        case_id = name if variant == "wing" else name + "_wingbody"
        d = EXT / "wave" / case_id
        d.mkdir(parents=True, exist_ok=True)
        req = build_openvsp_request(geom, d, basename=case_id, formats=("stl", "vsp3"))
        req["components"] = [c for c in req["components"] if c["name"] in components]
        req["openvsp_root"] = "D:/Program Files/OpenVSP/OpenVSP-3.26.1-win64-Python3.9/OpenVSP-3.26.1-win64"
        (d / "request.json").write_text(json.dumps(req, indent=2), encoding="utf-8")
        out[case_id] = {"components": [c["name"] for c in req["components"]],
                        "wing_area": geom.wing.area_m2,
                        "wing_span": geom.wing.span_m,
                        "fuselage_length": geom.fuselage.length_m,
                        "sections": len(geom.wing.sections), "stations": len(geom.fuselage.stations)}
print(json.dumps(out, indent=2))
