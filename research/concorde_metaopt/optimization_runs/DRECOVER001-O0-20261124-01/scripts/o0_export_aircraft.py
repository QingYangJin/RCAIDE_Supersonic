"""Export the real aircraft geometry for O0 (and O1 later) as openable files.

Everything here is derived from the frozen geometry model, so the exported .vsp3/.stl/.step
come from the same code path that produces the solver geometry. No solver is started.

Two geometries are exported for each side of the comparison:

  * full     - main wing + vertical tail + fuselage, i.e. the whole aircraft;
  * solver   - main wing + vertical tail only, which is what the VSPAERO evaluation in
               this project actually meshes (the fuselage is not in the solver model).

The difference is disclosed rather than hidden: a reader can open either file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(RUN / "scripts"))

from research.concorde_metaopt.aircraft import openvsp_geometry as worker  # noqa: E402
from research.concorde_metaopt.aircraft.geometry_model import (  # noqa: E402
    TAIL_ORIGIN_X_M,
    WING_ORIGIN_X_M,
    build_geometry,
)
from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0  # noqa: E402

OPENVSP_ROOT = Path(r"D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64")
OUT = RUN / "final_aircraft"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def component_list(geometry, include_fuselage: bool = True) -> List[Dict[str, Any]]:
    components = []
    for name, part, location, rotation in (
        ("main_wing", geometry.wing, [WING_ORIGIN_X_M, 0.0, -0.8], [0.0, 0.0, 0.0]),
        ("vertical_tail", geometry.vertical_tail, [TAIL_ORIGIN_X_M, 0.0, 1.0],
         [90.0, 0.0, 0.0]),
    ):
        components.append({
            "kind": "wing", "name": name, "symmetric": part.symmetric,
            "span_m": part.span_m, "location": location, "rotation": rotation,
            "thickness_to_chord": part.thickness_to_chord,
            "sections": [{"percent_span_location": section.percent_span_location,
                          "chord_m": section.chord_m,
                          "leading_edge_x_m": section.leading_edge_x_m,
                          "twist_deg": section.twist_deg}
                         for section in part.sections],
        })
    if include_fuselage:
        components.append({"kind": "fuselage", "name": "fuselage",
                           "length_m": geometry.fuselage.length_m,
                           "location": [0.0, 0.0, 0.0],
                           "stations": [station.to_dict()
                                        for station in geometry.fuselage.stations]})
    return components


def build_native(vsp, components):
    vsp.ClearVSPModel()
    handles = {}
    for component in components:
        _kind, geom = worker._add_component(vsp, component)
        handles[component["name"]] = geom
    vsp.Update()
    return handles


def export_one(vsp, geometry, basename: str, include_fuselage: bool) -> Dict[str, Any]:
    directory = OUT / "geometry"
    components = component_list(geometry, include_fuselage=include_fuselage)
    handles = build_native(vsp, components)
    metrics = {}
    for name, geom in handles.items():
        if name == "fuselage":
            metrics[name] = {
                "length_m": float(vsp.GetParmVal(vsp.GetParm(geom, "Length", "Design"))),
                "bbox_m": [float(vsp.GetParmVal(geom, key, "BBox"))
                           for key in ("X_Len", "Y_Len", "Z_Len")],
            }
        else:
            metrics[name] = {
                "total_area_m2": float(vsp.GetParmVal(geom, "TotalArea", "WingGeom")),
                "total_span_m": float(vsp.GetParmVal(geom, "TotalSpan", "WingGeom")),
                "bbox_m": [float(vsp.GetParmVal(geom, key, "BBox"))
                           for key in ("X_Len", "Y_Len", "Z_Len")],
            }
    spec = {"directory": str(directory), "basename": basename,
            "formats": ["vsp3", "stl", "step"]}
    exports = worker._export_assembly(vsp, spec)
    component_stls = worker._export_component_stls(vsp, spec, components)
    out = {"basename": basename, "includes_fuselage": include_fuselage,
           "components": [c["name"] for c in components], "metrics": metrics,
           "exports": {fmt: {"path": str(Path(row["path"])), "bytes": row["bytes"],
                             "sha256": sha_file(Path(row["path"]))}
                       for fmt, row in exports.items()},
           "component_stls": {name: {"path": str(Path(row["path"])), "bytes": row["bytes"],
                                     "sha256": sha_file(Path(row["path"]))}
                              for name, row in component_stls.items()}}
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--x12", type=float, nargs=12, required=True)
    parser.add_argument("--prefix", required=True,
                        help="basename prefix, e.g. baseline or optimized")
    parser.add_argument("--manifest", default=None,
                        help="optional JSON file to merge the result into")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "geometry").mkdir(parents=True, exist_ok=True)
    x12 = [float(v) for v in args.x12]
    identity = o0.design_identity(x12)
    geometry = build_geometry(list(o0.PHYSICAL_15_NAMES), o0.physical_15(x12))
    vsp = worker.import_openvsp(str(OPENVSP_ROOT))
    record = {
        "prefix": args.prefix,
        "design": identity,
        "x12": x12,
        "physical_15": list(o0.physical_15(x12)),
        "frozen_non_active_match": True,
        "model_metrics": {
            "wing_area_m2": float(geometry.wing.area_m2),
            "wing_span_m": float(geometry.wing.span_m),
            "wing_mac_m": float(geometry.wing.mean_aerodynamic_chord_m),
            "tail_area_m2": float(geometry.vertical_tail.area_m2),
            "tail_span_m": float(geometry.vertical_tail.span_m),
            "fuselage_length_m": float(geometry.fuselage.length_m),
        },
        "full": export_one(vsp, geometry, args.prefix, include_fuselage=True),
        "solver": export_one(vsp, geometry, args.prefix + "_solver", include_fuselage=False),
        "note": ("full includes the fuselage; solver is the main wing plus vertical tail, "
                 "which is exactly what this project's VSPAERO evaluation meshes"),
    }
    target = Path(args.manifest) if args.manifest else (OUT / (args.prefix + "_geometry.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps({"manifest": str(target), "sha256": sha_file(target),
                      "design_id": identity["design_id"],
                      "is_baseline": identity["is_baseline"],
                      "full_exports": record["full"]["exports"],
                      "solver_exports": record["solver"]["exports"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
