"""Issue zero-physical geometry freeze v2.

Builds the frozen 12D geometry contract from the current absolute-XForm OpenVSP
worker, exports a real OpenVSP model, checks one-variable-at-a-time boundary
perturbations in the real OpenVSP API, and writes geometry_freeze_v2.json.

No VSPAERO analysis is started: physical_solver_starts_actual stays 0.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.concorde_metaopt.aircraft import openvsp_geometry as worker  # noqa: E402
from research.concorde_metaopt.aircraft.geometry_model import (  # noqa: E402
    GEOMETRY_MODEL_VERSION,
    TAIL_ORIGIN_X_M,
    WING_ORIGIN_X_M,
    build_geometry,
)

OPENVSP_ROOT = Path("D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64")
CONFIG_PATH = ROOT / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"
OUT_DIR = Path(__file__).resolve().parent
EXPORT_DIR = OUT_DIR / "geometry_freeze_v2_artifacts"
SOURCE_FILES = (
    "research/concorde_metaopt/aircraft/geometry_model.py",
    "research/concorde_metaopt/aircraft/openvsp_geometry.py",
    "research/concorde_metaopt/dreal001/optimizers/constants.py",
    "research/concorde_metaopt/dreal001/optimizers/task.py",
    "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml",
)
REFERENCE = {
    "sref_m2": 358.25,
    "cref_m": 18.489893,
    "bref_m": 25.604638,
    "reference_frame": "WING_AC",
    "xcg_m": 16.821978259514246,
    "lift_reference_N": 1333704.4,
    "q_pa": 20483.940233430174,
    "lift_tol_rel": 1e-3,
}
FORCE_AXIS = {
    "frame": "WIND_AXIS_WITH_BODY_ALIGNED_AT_ZERO_SIDESLIP",
    "x_positive": "downstream freestream direction (drag positive +X)",
    "y_positive": "right wing (starboard)",
    "z_positive": "up (lift positive +Z at zero bank)",
    "lift_component": "CLtot * q * Sref",
    "drag_components": ["CDo (parasite)", "CDi (induced)", "CDtot = CDo + CDi"],
    "moment_reference_point": "WING_AC reference station specified by xcg_m; see reference_point_ambiguity",
    "status": "DEFINED_NOT_SOLVER_VALIDATED",
    "note": "Sign convention still requires R2 VSPAERO force/moment readback; no aerodynamic result is implied by this freeze.",
}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def canonical_sha(payload) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha_bytes(text.encode("utf-8"))


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def rounded(value: float, digits: int = 12) -> float:
    return float(round(float(value), digits))


def component_list(geometry):
    components = []
    for name, part, location, rotation in (
        ("main_wing", geometry.wing, [WING_ORIGIN_X_M, 0.0, -0.8], [0.0, 0.0, 0.0]),
        ("vertical_tail", geometry.vertical_tail, [TAIL_ORIGIN_X_M, 0.0, 1.0], [90.0, 0.0, 0.0]),
    ):
        components.append({
            "kind": "wing",
            "name": name,
            "symmetric": part.symmetric,
            "span_m": part.span_m,
            "location": location,
            "rotation": rotation,
            "thickness_to_chord": part.thickness_to_chord,
            "sections": [
                {
                    "percent_span_location": section.percent_span_location,
                    "chord_m": section.chord_m,
                    "leading_edge_x_m": section.leading_edge_x_m,
                    "twist_deg": section.twist_deg,
                }
                for section in part.sections
            ],
        })
    components.append({
        "kind": "fuselage",
        "name": "fuselage",
        "length_m": geometry.fuselage.length_m,
        "location": [0.0, 0.0, 0.0],
        "stations": [station.to_dict() for station in geometry.fuselage.stations],
    })
    return components


def stl_bounds(path: Path):
    data = path.read_bytes()
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    triangles = 0
    header = data[:5].lower()
    if header == b"solid":
        text = data.decode("ascii", errors="strict")
        vertices = 0
        for line in text.splitlines():
            parts = line.split()
            if not parts or parts[0].lower() != "vertex":
                continue
            if len(parts) != 4:
                raise ValueError("malformed ASCII STL vertex line in %s: %r" % (path, line))
            for axis in range(3):
                value = float(parts[1 + axis])
                lo[axis] = min(lo[axis], value)
                hi[axis] = max(hi[axis], value)
            vertices += 1
        if vertices == 0 or vertices % 3:
            raise ValueError("ASCII STL vertex count is not a positive multiple of 3: %s (%d)" % (path, vertices))
        triangles = vertices // 3
    else:
        if len(data) < 84:
            raise ValueError("STL too short: %s" % path)
        triangles = struct.unpack_from("<I", data, 80)[0]
        expected = 84 + 50 * triangles
        if len(data) != expected:
            raise ValueError("STL is not binary or is truncated: %s (%d != %d)" % (path, len(data), expected))
        for index in range(triangles):
            values = struct.unpack_from("<12f", data, 84 + 50 * index)
            for offset in (0, 3, 6):
                for axis in range(3):
                    value = values[offset + axis]
                    lo[axis] = min(lo[axis], value)
                    hi[axis] = max(hi[axis], value)
    return {
        "triangles": triangles,
        "min_xyz_m": [rounded(value) for value in lo],
        "max_xyz_m": [rounded(value) for value in hi],
        "extent_xyz_m": [rounded(hi[axis] - lo[axis]) for axis in range(3)],
    }


def read_xform(vsp, geom):
    return {
        key: float(vsp.GetParmVal(vsp.GetParm(geom, key, "XForm")))
        for key in ("Abs_Or_Relitive_flag", "X_Location", "Y_Location", "Z_Location",
                    "X_Rotation", "Y_Rotation", "Z_Rotation")
    }


def expected_xform(component):
    location = component.get("location", [0.0, 0.0, 0.0])
    rotation = component.get("rotation", [0.0, 0.0, 0.0])
    return {
        "Abs_Or_Relitive_flag": 0.0,
        "X_Location": float(location[0]),
        "Y_Location": float(location[1]),
        "Z_Location": float(location[2]),
        "X_Rotation": float(rotation[0]),
        "Y_Rotation": float(rotation[1]),
        "Z_Rotation": float(rotation[2]),
    }


def build_native(vsp, components):
    vsp.ClearVSPModel()
    handles = {}
    for component in components:
        _kind, geom = worker._add_component(vsp, component)
        handles[component["name"]] = geom
    vsp.Update()
    return handles


def check_native_case(vsp, case_id, components, geometry):
    checks = []
    result = {"case_id": case_id, "openvsp_build_ok": False, "checks": checks, "errors": []}
    try:
        handles = build_native(vsp, components)
        result["openvsp_build_ok"] = True
        for component in components:
            expected = expected_xform(component)
            actual = read_xform(vsp, handles[component["name"]])
            for key, value in expected.items():
                ok = math.isfinite(actual[key]) and math.isclose(actual[key], value, rel_tol=0.0, abs_tol=1.0e-8)
                checks.append({"check": "xform_%s_%s" % (component["name"], key), "ok": ok,
                               "expected": rounded(value), "actual": rounded(actual[key])})
        wing_area = float(vsp.GetParmVal(handles["main_wing"], "TotalArea", "WingGeom"))
        wing_span = float(vsp.GetParmVal(handles["main_wing"], "TotalSpan", "WingGeom"))
        tail_area = float(vsp.GetParmVal(handles["vertical_tail"], "TotalArea", "WingGeom"))
        fuselage_length = float(vsp.GetParmVal(vsp.GetParm(handles["fuselage"], "Length", "Design")))
        for label, actual, expected, rel_tol in (
            ("wing_area_m2", wing_area, geometry.wing.area_m2, 1.0e-9),
            ("wing_span_m", wing_span, geometry.wing.span_m, 1.0e-9),
            ("tail_area_m2", tail_area, geometry.vertical_tail.area_m2, 1.0e-9),
            ("fuselage_length_m", fuselage_length, geometry.fuselage.length_m, 1.0e-9),
        ):
            ok = math.isfinite(actual) and math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=1.0e-9)
            checks.append({"check": label, "ok": ok, "expected": rounded(expected), "actual": rounded(actual)})
        for name, expected_thickness in (("main_wing", geometry.wing.thickness_to_chord),
                                         ("vertical_tail", geometry.vertical_tail.thickness_to_chord)):
            surf = vsp.GetXSecSurf(handles[name], 0)
            values = []
            for index in range(vsp.GetNumXSec(surf)):
                parm = vsp.GetXSecParm(vsp.GetXSec(surf, index), "ThickChord")
                values.append(float(vsp.GetParmVal(parm)) if parm else None)
            ok = all(value is not None and math.isclose(value, expected_thickness, abs_tol=1.0e-8)
                     for value in values)
            checks.append({"check": "thickness_%s" % name, "ok": ok,
                           "expected": rounded(expected_thickness), "actual": values})
    except Exception as error:
        result["errors"].append(type(error).__name__ + ": " + str(error))
    result["all_checks_ok"] = bool(result["openvsp_build_ok"]) and all(item["ok"] for item in checks)
    return result


def contract_payload(config, geometry):
    variables = config["variables"] + config["fixed_variables"]
    names = [item["name"] for item in variables]
    baseline = [float(item["baseline"]) for item in variables]
    twelve = [float(item["baseline"]) for item in config["variables"]]
    wing_ac_local = float(geometry.wing.aerodynamic_center_x_m)
    wing_ac_global = WING_ORIGIN_X_M + wing_ac_local
    total_mass = float(geometry.mass_kg["total_takeoff"])
    cl_target = REFERENCE["lift_reference_N"] / (REFERENCE["q_pa"] * REFERENCE["sref_m2"])
    force_axis = dict(FORCE_AXIS)
    force_axis["moment_reference_point"] = {
        "name": "WING_AC",
        "p2a_xcg_m": REFERENCE["xcg_m"],
        "geometry_model_wing_ac_local_x_m": rounded(wing_ac_local),
        "geometry_model_wing_ac_global_x_m": rounded(wing_ac_global),
        "status": "AMBIGUOUS_LOCAL_VERSUS_GLOBAL_ORIGIN_NOT_RESOLVED",
        "note": ("P2A xcg_m equals the geometry model wing-local AC exactly; the "
                 "global AC adds WING_ORIGIN_X_M=14.0 m. No moment or trim claim is made "
                 "until R2 reads the solver moment reference back."),
    }
    source_hashes = {relative: sha_file(ROOT / relative) for relative in SOURCE_FILES}
    return {
        "schema": "drecover001.geometry_contract.v2",
        "design_space_config_sha256": sha_file(CONFIG_PATH),
        "design_variables": [
            {
                "id": item["id"], "name": item["name"], "unit": item["unit"],
                "baseline": float(item["baseline"]), "lower": float(item["lower"]),
                "upper": float(item["upper"]),
            }
            for item in config["variables"]
        ],
        "fixed_variables": [
            {"id": item["id"], "name": item["name"], "unit": item["unit"],
             "baseline": float(item["baseline"])}
            for item in config["fixed_variables"]
        ],
        "model_version": GEOMETRY_MODEL_VERSION,
        "origins_m": {"main_wing_x": WING_ORIGIN_X_M, "vertical_tail_x": TAIL_ORIGIN_X_M,
                      "fuselage_x": 0.0},
        "placement_contract": "OpenVSP XForm Abs_Or_Relitive_flag=ABS for every component; write/readback checked",
        "baseline_geometry": geometry.to_dict(),
        "sref_policy": "Sref(x) equals the W01 wing_area design variable; no normalization or hidden scale",
        "reference": REFERENCE,
        "cl_target_baseline": rounded(cl_target),
        "force_axis": force_axis,
        "mass_contract": {
            "status": "PROVISIONAL_NOT_FROZEN",
            "component_mass_kg": {key: rounded(value) for key, value in geometry.mass_kg.items()},
            "total_takeoff_kg": rounded(total_mass),
            "operating_empty_kg": rounded(float(geometry.mass_kg["operating_empty"])),
            "cg_x_m": rounded(geometry.cg_x_m),
            "cg_status": "PROVISIONAL_GEOMETRY_MODEL_ESTIMATE_NOT_A_WEIGHT_AND_BALANCE_VALIDATION",
            "wing_ac_x_m": rounded(wing_ac_global),
            "static_margin": rounded(geometry.static_margin),
            "static_margin_status": "GEOMETRY_MODEL_ESTIMATE_NOT_HTAIL_TRIM_OR_STABILITY_VALIDATION",
            "lift_reference_mass_kg": 136000.0,
            "lift_reference_note": ("L_ref is a contractual lift target, not the takeoff mass; "
                                    "total_takeoff_kg differs and must not be claimed as a trim or "
                                    "performance result."),
        },
        "source_sha256": source_hashes,
    }


def main() -> int:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    variables = config["variables"] + config["fixed_variables"]
    names = [item["name"] for item in variables]
    baseline = [float(item["baseline"]) for item in variables]
    twelve = [float(item["baseline"]) for item in config["variables"]]
    geometry = build_geometry(names, baseline)

    wing_area = float(geometry.wing.area_m2)
    wing_ac_local = float(geometry.wing.aerodynamic_center_x_m)
    wing_ac_global = WING_ORIGIN_X_M + wing_ac_local
    total_mass = float(geometry.mass_kg["total_takeoff"])
    operating_empty = float(geometry.mass_kg["operating_empty"])
    mass_sum = sum(
        float(value)
        for key, value in geometry.mass_kg.items()
        if key not in ("total_takeoff", "operating_empty")
    )
    cl_target = REFERENCE["lift_reference_N"] / (REFERENCE["q_pa"] * REFERENCE["sref_m2"])
    force_axis = dict(FORCE_AXIS)
    force_axis["moment_reference_point"] = {
        "name": "WING_AC",
        "p2a_xcg_m": REFERENCE["xcg_m"],
        "geometry_model_wing_ac_local_x_m": rounded(wing_ac_local),
        "geometry_model_wing_ac_global_x_m": rounded(wing_ac_global),
        "status": "AMBIGUOUS_LOCAL_VERSUS_GLOBAL_ORIGIN_NOT_RESOLVED",
        "note": ("P2A xcg_m equals the geometry model wing-local AC exactly; the "
                 "global AC adds WING_ORIGIN_X_M=14.0 m. No moment or trim claim is made "
                 "until R2 reads the solver moment reference back."),
    }

    source_hashes = {relative: sha_file(ROOT / relative) for relative in SOURCE_FILES}
    config_sha = sha_file(CONFIG_PATH)
    contract = contract_payload(config, geometry)
    geometry_contract_sha = canonical_sha(contract)
    freeze_id = "GBFREEZE2-" + geometry_contract_sha[:16]

    boundary_cases = []
    for index, item in enumerate(config["variables"]):
        for bound_name in ("lower", "upper"):
            vector = list(baseline)
            vector[index] = float(item[bound_name])
            case = {"case_id": "%s_%s" % (item["id"], bound_name), "variable_id": item["id"],
                    "bound": bound_name, "value": rounded(vector[index])}
            try:
                perturbed = build_geometry(names, vector)
                finite = all(math.isfinite(value) for value in perturbed.vector)
                case.update({
                    "model_ok": finite,
                    "sref_m2": rounded(perturbed.wing.area_m2),
                    "tail_area_m2": rounded(perturbed.vertical_tail.area_m2),
                    "span_m": rounded(perturbed.wing.span_m),
                    "cg_x_m": rounded(perturbed.cg_x_m),
                    "wing_ac_global_x_m": rounded(WING_ORIGIN_X_M + perturbed.wing.aerodynamic_center_x_m),
                    "geometry": perturbed.to_dict(include_sections=False),
                })
            except Exception as error:
                case.update({"model_ok": False, "error": type(error).__name__ + ": " + str(error)})
            boundary_cases.append(case)

    vsp = worker.import_openvsp(str(OPENVSP_ROOT))
    runtime_binary = OPENVSP_ROOT / "python/openvsp/openvsp/_vsp.pyd"
    native_boundary = []
    for case in boundary_cases:
        if not case.get("model_ok"):
            native_boundary.append({"case_id": case["case_id"], "skipped": "geometry model rejected"})
            continue
        vector = list(baseline)
        item = next(entry for entry in config["variables"] if entry["id"] == case["variable_id"])
        index = [entry["id"] for entry in config["variables"]].index(case["variable_id"])
        vector[index] = float(item[case["bound"]])
        perturbed = build_geometry(names, vector)
        native_boundary.append(check_native_case(vsp, case["case_id"], component_list(perturbed), perturbed))

    components = component_list(geometry)
    handles = build_native(vsp, components)
    baseline_xform = {name: read_xform(vsp, handles[name]) for name in handles}
    baseline_metrics = {
        "main_wing": {
            "total_area_m2": rounded(vsp.GetParmVal(handles["main_wing"], "TotalArea", "WingGeom")),
            "total_span_m": rounded(vsp.GetParmVal(handles["main_wing"], "TotalSpan", "WingGeom")),
            "bbox_m": [rounded(vsp.GetParmVal(handles["main_wing"], key, "BBox")) for key in ("X_Len", "Y_Len", "Z_Len")],
        },
        "vertical_tail": {
            "total_area_m2": rounded(vsp.GetParmVal(handles["vertical_tail"], "TotalArea", "WingGeom")),
            "total_span_m": rounded(vsp.GetParmVal(handles["vertical_tail"], "TotalSpan", "WingGeom")),
            "bbox_m": [rounded(vsp.GetParmVal(handles["vertical_tail"], key, "BBox")) for key in ("X_Len", "Y_Len", "Z_Len")],
        },
        "fuselage": {
            "length_m": rounded(vsp.GetParmVal(vsp.GetParm(handles["fuselage"], "Length", "Design"))),
            "bbox_m": [rounded(vsp.GetParmVal(handles["fuselage"], key, "BBox")) for key in ("X_Len", "Y_Len", "Z_Len")],
        },
    }
    export_spec = {"directory": str(EXPORT_DIR), "basename": "concorde_geometry_freeze_v2",
                   "formats": ["vsp3", "stl", "step"]}
    exports = worker._export_assembly(vsp, export_spec)
    component_exports = worker._export_component_stls(vsp, export_spec, components)
    exports_out = {}
    for fmt, row in exports.items():
        path = Path(row["path"])
        exports_out[fmt] = {"path": rel(path), "bytes": path.stat().st_size, "sha256": sha_file(path)}
    component_out = {}
    for name, row in component_exports.items():
        path = Path(row["path"])
        bounds = stl_bounds(path)
        component_out[name] = {"path": rel(path), "bytes": path.stat().st_size,
                               "sha256": sha_file(path), "bounds": bounds}
    wing_bounds = component_out["main_wing"]["bounds"]["extent_xyz_m"]
    tail_bounds = component_out["vertical_tail"]["bounds"]["extent_xyz_m"]
    fuselage_bounds = component_out["fuselage"]["bounds"]["extent_xyz_m"]
    stl_checks = []
    for label, actual, expected, rel_tol in (
        ("wing_stl_span_m", wing_bounds[1], geometry.wing.span_m, 1.0e-3),
        ("tail_stl_span_m", tail_bounds[2], geometry.vertical_tail.span_m, 1.0e-3),
        ("fuselage_stl_length_m", fuselage_bounds[0], geometry.fuselage.length_m, 1.0e-3),
    ):
        ok = math.isfinite(actual) and math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=1.0e-6)
        stl_checks.append({"check": label, "ok": ok, "expected": rounded(expected), "actual": rounded(actual)})
    assembly_bounds = stl_bounds(Path(exports_out["stl"]["path"]))

    consistency = [
        {"check": "sref_equals_wing_area", "ok": math.isclose(wing_area, REFERENCE["sref_m2"], rel_tol=0.0, abs_tol=1.0e-9),
         "sref_m2": rounded(wing_area), "expected_sref_m2": REFERENCE["sref_m2"]},
        {"check": "cref_equals_mac", "ok": math.isclose(geometry.wing.mean_aerodynamic_chord_m, REFERENCE["cref_m"], rel_tol=0.0, abs_tol=1.0e-6),
         "cref_m": rounded(geometry.wing.mean_aerodynamic_chord_m), "expected_cref_m": REFERENCE["cref_m"]},
        {"check": "bref_equals_span", "ok": math.isclose(geometry.wing.span_m, REFERENCE["bref_m"], rel_tol=0.0, abs_tol=1.0e-6),
         "bref_m": rounded(geometry.wing.span_m), "expected_bref_m": REFERENCE["bref_m"]},
        {"check": "mass_components_sum_to_total", "ok": math.isclose(mass_sum, total_mass, rel_tol=0.0, abs_tol=1.0e-6),
         "component_sum_kg": rounded(mass_sum), "total_kg": rounded(total_mass)},
        {"check": "cg_inside_fuselage", "ok": 0.0 < geometry.cg_x_m < geometry.fuselage.length_m,
         "cg_x_m": rounded(geometry.cg_x_m), "fuselage_length_m": rounded(geometry.fuselage.length_m)},
        {"check": "baseline_cl_target_finite_positive", "ok": math.isfinite(cl_target) and cl_target > 0.0,
         "cl_target": rounded(cl_target)},
        {"check": "nacelle_not_in_export", "ok": True,
         "note": "worker exports main wing, vertical tail and fuselage; nacelle remains reference data only"},
    ]
    all_checks = [item["ok"] for item in consistency] + [item["ok"] for item in stl_checks]
    all_checks += [case.get("model_ok", False) for case in boundary_cases]
    all_checks += [case.get("all_checks_ok", False) for case in native_boundary]
    status = "GEOMETRY_FREEZE_V2_ISSUED_ZERO_PHYSICAL" if all(all_checks) else "GEOMETRY_FREEZE_V2_FAILED"

    payload = {
        "schema": "drecover001.geometry_freeze_v2.v1",
        "freeze_id": freeze_id,
        "geometry_contract_sha256": geometry_contract_sha,
        "status": status,
        "freeze_issued": status == "GEOMETRY_FREEZE_V2_ISSUED_ZERO_PHYSICAL",
        "scope": "GEOMETRY_AND_REFERENCE_CONTRACT_ONLY_NO_AERODYNAMIC_VALIDATION",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "base_commit": "01c9274801474c113a2c488e375d451bcd0297c3",
            "config_path": rel(CONFIG_PATH),
            "config_sha256": config_sha,
            "source_sha256": source_hashes,
            "openvsp_runtime_root": str(OPENVSP_ROOT),
            "openvsp_runtime_binary_sha256": sha_file(runtime_binary),
            "python": sys.executable,
            "python_version": sys.version,
        },
        "design_contract": {
            "design_variables": contract["design_variables"],
            "fixed_variables": contract["fixed_variables"],
            "baseline_x12": [rounded(value) for value in twelve],
            "baseline_physical_15": {name: rounded(value) for name, value in zip(names, baseline)},
            "bounds_status": config.get("bounds_status"),
            "config_frozen": bool(config.get("frozen")),
        },
        "baseline_geometry": geometry.to_dict(),
        "reference_contract": {
            **REFERENCE,
            "cl_target": rounded(cl_target),
            "sref_policy": "Sref(x) is the W01 wing_area variable; no normalization or hidden scale",
            "cref_source": "main wing MAC at baseline",
            "bref_source": "main wing projected span at baseline",
        },
        "mass_cg_ac_contract": contract["mass_contract"],
        "force_axis_contract": force_axis,
        "consistency_checks": consistency,
        "boundary_perturbation": {
            "method": "one variable at a time at its declared lower and upper bound; baseline otherwise",
            "cases": boundary_cases,
            "native_openvsp_cases": native_boundary,
            "model_cases_ok": sum(1 for case in boundary_cases if case.get("model_ok")),
            "native_cases_ok": sum(1 for case in native_boundary if case.get("all_checks_ok")),
            "native_cases_total": len(native_boundary),
            "all_ok": all(case.get("all_checks_ok", False) for case in native_boundary),
        },
        "real_openvsp_export": {
            "components": components,
            "xform_readback": baseline_xform,
            "expected_xform": {component["name"]: expected_xform(component) for component in components},
            "metrics": baseline_metrics,
            "exports": exports_out,
            "component_stls": component_out,
            "assembly_stl_bounds": assembly_bounds,
            "stl_placement_checks": stl_checks,
            "export_scope": "REAL_OPENVSP_GEOMETRY_EXPORT_ONLY_NO_SOLVER",
        },
        "open_items": [
            "Mass and CG are the geometry model's PROVISIONAL estimate; this is not a weight-and-balance validation.",
            "WING_AC moment-reference origin is ambiguous: P2A xcg_m equals the wing-local AC; applying WING_ORIGIN_X_M gives a different global station.",
            "Force-axis signs are defined here but not read back from VSPAERO; R2 must validate signs and moment reference.",
            "Nacelle is not exported by the current worker; it remains reference geometry only.",
            "Lift reference 136,000 kg differs from the provisional 184,880 kg takeoff mass; L_ref is contractual, not a performance result.",
        ],
        "limitations": [
            "No VSPAERO process was launched; physical_solver_starts_actual=0.",
            "No aerodynamic coefficients, lift matching, mesh convergence or control-surface effect are validated.",
            "Export success proves the current OpenVSP build accepts and writes this geometry; it does not prove solver mesh quality.",
        ],
        "physical_solver_starts_actual": 0,
        "internal_solver_cases_actual": 0,
        "aerodynamic_active_mask": "NOT_VALIDATED",
    }
    json_path = OUT_DIR / "geometry_freeze_v2.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    json_sha = sha_file(json_path)

    md = [
        "# Geometry Freeze V2 (zero physical)",
        "",
        "- freeze_id: " + chr(96) + freeze_id + chr(96),
        "- geometry_contract_sha256: " + chr(96) + geometry_contract_sha + chr(96),
        "- geometry_freeze_v2.json SHA256: " + chr(96) + json_sha + chr(96),
        "- status: " + chr(96) + status + chr(96),
        "- base_commit: " + chr(96) + "01c9274801474c113a2c488e375d451bcd0297c3" + chr(96),
        "- physical_solver_starts_actual: 0; internal_solver_cases_actual: 0",
        "",
        "## Frozen 12D design",
        "",
        "| id | name | baseline | lower | upper | unit |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for item in contract["design_variables"]:
        md.append("| %s | %s | %.9g | %.9g | %.9g | %s |" % (
            item["id"], item["name"], item["baseline"], item["lower"], item["upper"], item["unit"]))
    md += [
        "",
        "Fixed fuselage: F01 length %.6f m, F02 fineness %.6f, F03 height/width %.6f." % (
            contract["fixed_variables"][0]["baseline"], contract["fixed_variables"][1]["baseline"],
            contract["fixed_variables"][2]["baseline"]),
        "",
        "## Reference contract",
        "",
        "- Sref = %.6f m2 (W01), Cref = %.6f m, Bref = %.6f m." % (
            REFERENCE["sref_m2"], REFERENCE["cref_m"], REFERENCE["bref_m"]),
        "- q = %.9f Pa, L_ref = %.3f N, CL_target = %.9f." % (
            REFERENCE["q_pa"], REFERENCE["lift_reference_N"], cl_target),
        "- reference_frame = WING_AC; P2A xcg_m = %.12f m." % REFERENCE["xcg_m"],
        "- Force axis: wind/body-aligned, +X downstream, +Y starboard, +Z up; status " + chr(96) + FORCE_AXIS["status"] + chr(96) + ".",
        "- Moment-reference origin is **ambiguous** between wing-local AC %.12f m and global AC %.12f m; see open items." % (wing_ac_local, wing_ac_global),
        "",
        "## Mass / CG / AC (provisional)",
        "",
        "- total_takeoff = %.3f kg; cg_x = %.9f m; wing AC global = %.9f m; static margin = %.9f." % (
            total_mass, geometry.cg_x_m, wing_ac_global, geometry.static_margin),
        "- status: " + chr(96) + "PROVISIONAL_NOT_FROZEN" + chr(96) + "; no weight-and-balance, trim or stability claim.",
        "",
        "## Real OpenVSP export",
        "",
        "| artifact | bytes | SHA256 |",
        "| --- | ---: | --- |",
    ]
    for fmt, row in exports_out.items():
        md.append("| " + row["path"] + " | %d | " % row["bytes"] + chr(96) + row["sha256"] + chr(96) + " |")
    md += [
        "",
        "- Absolute XForm readback: " + chr(96) + json.dumps(baseline_xform, sort_keys=True) + chr(96) + ".",
        "- STL placement: wing span %.6f m, tail span %.6f m, fuselage length %.6f m (all checks %s)." % (
            wing_bounds[1], tail_bounds[2], fuselage_bounds[0],
            "PASS" if all(item["ok"] for item in stl_checks) else "FAIL"),
        "",
        "## Boundary perturbation",
        "",
        "- 24 one-variable-at-a-time model cases: %d/24 ok." % sum(1 for case in boundary_cases if case.get("model_ok")),
        "- 24 real OpenVSP construction/readback cases: %d/%d ok." % (
            sum(1 for case in native_boundary if case.get("all_checks_ok")), len(native_boundary)),
        "",
        "## Open items",
        "",
    ]
    for item in payload["open_items"]:
        md.append("- " + item)
    md += ["", "No VSPAERO solver was started. This freeze is a geometry/reference contract, not aerodynamic evidence.", ""]
    md_path = OUT_DIR / "geometry_freeze_v2.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "freeze_id": freeze_id,
        "geometry_contract_sha256": geometry_contract_sha,
        "json_sha256": json_sha,
        "json_bytes": json_path.stat().st_size,
        "native_cases_ok": sum(1 for case in native_boundary if case.get("all_checks_ok")),
        "native_cases_total": len(native_boundary),
        "export_checks_ok": all(item["ok"] for item in stl_checks),
        "physical_solver_starts_actual": 0,
    }, indent=2))
    return 0 if status == "GEOMETRY_FREEZE_V2_ISSUED_ZERO_PHYSICAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
