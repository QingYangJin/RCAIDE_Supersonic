"""Fresh real OpenVSP surface diagnostic. No aero analysis or solver invocation."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
import traceback
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from research.concorde_metaopt.aircraft import openvsp_geometry as worker
from research.concorde_metaopt.aircraft.geometry_model import build_geometry, WING_ORIGIN_X_M, TAIL_ORIGIN_X_M


def main():
    out = Path(__file__).resolve().parent
    install = Path("D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64")
    receipt = {"scope": "REAL_OPENVSP_SURFACE_DIAGNOSTIC_ONLY", "status": "NOT_READY",
               "physical_solver_starts_actual": 0, "internal_solver_cases_actual": 0,
               "aerodynamic_active_mask": "NOT_VALIDATED", "freeze_issued": False,
               "real_admission": False, "generated_utc": datetime.now(timezone.utc).isoformat()}
    try:
        vsp = worker.import_openvsp(install)
        receipt["import_recipe"] = "production worker.import_openvsp; 3.55 package roots + retained DLL handles"
        receipt["module_path"] = vsp.__file__
        receipt["python"] = sys.executable
        receipt["python_version"] = sys.version
        receipt["runtime_root"] = str(install)
        receipt["runtime_binary_sha256"] = hashlib.sha256((install / "python/openvsp/openvsp/_vsp.pyd").read_bytes()).hexdigest()
        config_path = ROOT / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"
        config = yaml.safe_load(config_path.read_text())
        variables = config["variables"] + config["fixed_variables"]
        model = build_geometry([v["name"] for v in variables], [float(v["baseline"]) for v in variables])
        from research.concorde_metaopt.aircraft.openvsp_check import build_openvsp_request
        components = build_openvsp_request(model, out, formats=("vsp3",))["components"]
        receipt["request"] = components
        receipt["request_sha256"] = hashlib.sha256(json.dumps(components, sort_keys=True).encode()).hexdigest()
        receipt["config_sha256"] = hashlib.sha256(config_path.read_bytes()).hexdigest()
        vsp.ClearVSPModel()
        handles = {c["name"]: worker._add_component(vsp, c)[1] for c in components}
        vsp.Update()
        surface_rows = {}
        for component in components:
            name, geom = component["name"], handles[component["name"]]
            count = vsp.GetTotalNumSurfs(geom)
            points = []
            # Surface coordinates returned by native API, not transformed request echoes.
            for surf in range(count):
                for u in np.linspace(0., 1., 17):
                    for w in np.linspace(0., 1., 17):
                        p = vsp.CompPnt01(geom, surf, float(u), float(w))
                        points.append([p.x(), p.y(), p.z()])
            points = np.asarray(points, dtype=np.float64)
            if not len(points) or not np.isfinite(points).all():
                raise RuntimeError("native surface points missing/nonfinite")
            transform = {key: vsp.GetParmVal(vsp.GetParm(geom, key, "XForm"))
                         for key in ("Abs_Or_Relitive_flag", "X_Location", "Y_Location", "Z_Location",
                                     "X_Rotation", "Y_Rotation", "Z_Rotation")}
            surface_rows[name] = {"native_surface_count": count, "sample_count": len(points),
                                  "min_xyz_m": points.min(axis=0).tolist(),
                                  "max_xyz_m": points.max(axis=0).tolist(),
                                  "extent_xyz_m": np.ptp(points, axis=0).tolist(),
                                  "sample_sha256": hashlib.sha256(points.astype("<f8").tobytes()).hexdigest(),
                                  "xform_readback": transform}
        receipt["surfaces"] = surface_rows
        airfoils = {}
        for name in ("main_wing", "vertical_tail"):
            geom = handles[name]
            surf = vsp.GetXSecSurf(geom, 0)
            values = []
            for index in range(vsp.GetNumXSec(surf)):
                xsec = vsp.GetXSec(surf, index)
                parm = vsp.GetXSecParm(xsec, "ThickChord")
                values.append(None if not parm else float(vsp.GetParmVal(parm)))
            expected = model.wing.thickness_to_chord if name == "main_wing" else model.vertical_tail.thickness_to_chord
            airfoils[name] = {"model_thickness_to_chord": expected, "native_section_thickness_to_chord": values,
                              "matches_model": all(value is not None and abs(value - expected) < 1e-8 for value in values)}
        receipt["airfoil_readback"] = airfoils
        tail = surface_rows["vertical_tail"]
        wing = surface_rows["main_wing"]
        ex, ey, ez = tail["extent_xyz_m"]
        checks = {"tail_height_over_1m": ez > 1., "tail_height_exceeds_width": ez > 5 * ey,
                  "tail_aft_of_wing_origin": tail["min_xyz_m"][0] > WING_ORIGIN_X_M,
                  "tail_above_wing_plane": tail["min_xyz_m"][2] > wing["min_xyz_m"][2],
                  "tail_single_native_surface": tail["native_surface_count"] == 1,
                  "wing_span_over_10m": wing["extent_xyz_m"][1] > 10.,
                  "airfoil_thickness_matches_model": all(row["matches_model"] for row in airfoils.values())}
        receipt["checks"] = checks
        path = out / "real_openvsp_geometry_probe.vsp3"
        vsp.WriteVSPFile(str(path), vsp.SET_ALL)
        receipt["vsp3_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt["vsp3_bytes"] = path.stat().st_size
        receipt["status"] = "SURFACE_DIAGNOSTIC_PASS_NOT_FREEZE" if all(checks.values()) else "SURFACE_DIAGNOSTIC_FAIL"
        receipt["limitations"] = "Sparse native surface samples, not STL/solver mesh or full 12D response; no Sref/AC/mass validation or aerodynamic evidence."
    except Exception as error:
        receipt["status"] = "ERROR"
        receipt["error"] = type(error).__name__ + ": " + str(error)
        receipt["traceback"] = traceback.format_exc()
    receipt["source_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (Path(__file__), Path(worker.__file__), ROOT / "research/concorde_metaopt/aircraft/openvsp_check.py", ROOT / "research/concorde_metaopt/aircraft/geometry_model.py")}
    (out / "real_openvsp_geometry_probe.json").write_text(json.dumps(receipt, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "SURFACE_DIAGNOSTIC_PASS_NOT_FREEZE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
