"""Build a wing-only LF geometry request for the 12D design set with explicit overrides."""
import json
import sys
from pathlib import Path

REPO = Path("D:/RCAIDE")
import os
os.chdir(REPO)
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.aircraft.design_space import load_design_space
from research.concorde_metaopt.aircraft import geometry_builder

CONFIG = "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"
EXT = Path("C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
OPENVSP_ROOT = r"D:/Program Files/OpenVSP/OpenVSP-3.26.1-win64-Python3.9/OpenVSP-3.26.1-win64"


def main():
    case = sys.argv[1]
    overrides = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    space = load_design_space(CONFIG)
    baseline = dict(zip([v.id for v in space.variables], space.baseline_vector()))
    for var_id, value in overrides.items():
        if var_id not in baseline:
            raise SystemExit("unknown variable id %s" % var_id)
        baseline[var_id] = float(value)
    vector = [baseline[v.id] for v in space.variables]
    geometry = geometry_builder.build_geometry_from_design_space(space, vector)
    wing = geometry.wing
    request = {
        "openvsp_root": OPENVSP_ROOT,
        "components": [{
            "kind": "wing",
            "name": "main_wing",
            "symmetric": True,
            "span_m": wing.span_m,
            "location": [14.0, 0.0, -0.8],
            "rotation": [0.0, 0.0, 0.0],
            "sections": [{
                "percent_span_location": s.percent_span_location,
                "chord_m": s.chord_m,
                "leading_edge_x_m": s.leading_edge_x_m,
                "twist_deg": s.twist_deg,
            } for s in wing.sections],
        }],
        "export": {"directory": str(EXT / "lf" / case), "basename": "main_wing_" + case},
    }
    cdir = EXT / "lf" / case
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
    summary = {
        "case": case,
        "overrides": overrides,
        "design_vector": vector,
        "wing": {"area_m2": wing.area_m2, "span_m": wing.span_m, "root_chord_m": wing.root_chord_m,
                 "mac_m": wing.mean_aerodynamic_chord_m, "ac_x_m": wing.aerodynamic_center_x_m,
                 "sections": [s.to_dict() for s in wing.sections]},
    }
    (cdir / "case_geometry.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"case": case, "overrides": overrides, "wing_area": wing.area_m2,
                      "root_chord": wing.root_chord_m, "span": wing.span_m}, indent=1))


if __name__ == "__main__":
    main()
