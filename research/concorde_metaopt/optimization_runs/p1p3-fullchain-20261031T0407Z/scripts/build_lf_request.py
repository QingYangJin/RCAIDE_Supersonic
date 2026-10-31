"""Build wing-only LF (thin surface) OpenVSP requests from the 12D design set."""
import json
import sys
from pathlib import Path

REPO = Path("D:/RCAIDE")
sys.path.insert(0, str(REPO))

from research.concorde_metaopt.aircraft.design_space import load_design_space
from research.concorde_metaopt.aircraft.geometry_builder import build_geometry_from_design_space

OPENVSP_ROOT = "D:/Program Files/OpenVSP/OpenVSP-3.26.1-win64-Python3.9/OpenVSP-3.26.1-win64"
CFG = REPO / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"


def main():
    out_root = Path(sys.argv[1])
    space = load_design_space(CFG)
    names = list(space.names)
    base = list(space.baseline_vector())
    tip = names.index("tip_twist")
    print("design_set", space.design_set, "dim", space.design_dim)
    print("names", names)
    cases = {}
    cases["baseline"] = base
    w10 = list(base)
    w10[tip] = 2.0
    cases["w10_plus2"] = w10
    summary = {}
    for cname, vec in cases.items():
        geom = build_geometry_from_design_space(space, vec)
        wing = geom.wing
        secs = [
            {
                "percent_span_location": float(s.percent_span_location),
                "chord_m": float(s.chord_m),
                "leading_edge_x_m": float(s.leading_edge_x_m),
                "twist_deg": float(s.twist_deg),
            }
            for s in wing.sections
        ]
        cdir = out_root / "lf" / cname
        cdir.mkdir(parents=True, exist_ok=True)
        request = {
            "openvsp_root": OPENVSP_ROOT,
            "export": {
                "directory": str(cdir),
                "basename": "main_wing_" + cname,
                "formats": ["vsp3", "stl"],
            },
            "components": [
                {
                    "kind": "wing",
                    "name": "main_wing",
                    "symmetric": True,
                    "span_m": float(wing.span_m),
                    "location": [14.0, 0.0, -0.8],
                    "rotation": [0.0, 0.0, 0.0],
                    "sections": secs,
                }
            ],
        }
        (cdir / "request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
        summary[cname] = {
            "span_m": float(wing.span_m),
            "sections": secs,
            "design_vector": vec,
        }
        print(cname, "span", round(wing.span_m, 6), "twists", [round(s["twist_deg"], 6) for s in secs],
              "chords", [round(s["chord_m"], 6) for s in secs])
    (out_root / "lf" / "lf_geometry_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
