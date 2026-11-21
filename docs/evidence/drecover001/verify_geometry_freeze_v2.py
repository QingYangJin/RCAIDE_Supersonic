"""Deterministic verifier for geometry_freeze_v2.json.

Recomputes the geometry contract from the current sources and checks the stored
freeze identity, artifact hashes, STL bounds, XForm readback, reference values
and mass contract. Loads the exported .vsp3 with the real OpenVSP runtime.

No VSPAERO analysis is started; physical_solver_starts_actual stays 0.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

SPEC = importlib.util.spec_from_file_location("build_geometry_freeze_v2", HERE / "build_geometry_freeze_v2.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

FREEZE_PATH = HERE / "geometry_freeze_v2.json"
VERIFY_PATH = HERE / "geometry_freeze_v2_verification.json"


def main() -> int:
    payload = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    config = builder.yaml.safe_load(builder.CONFIG_PATH.read_text(encoding="utf-8"))
    names = [item["name"] for item in config["variables"] + config["fixed_variables"]]
    baseline = [float(item["baseline"]) for item in config["variables"] + config["fixed_variables"]]
    geometry = builder.build_geometry(names, baseline)

    checks = []
    failures = []

    def expect(check, ok, detail=None):
        row = {"check": check, "ok": bool(ok)}
        if detail is not None:
            row["detail"] = detail
        checks.append(row)
        if not ok:
            failures.append(row)
        return ok

    expect("schema_is_freeze_v2", payload.get("schema") == "drecover001.geometry_freeze_v2.v1")
    expect("status_issued_zero_physical", payload.get("status") == "GEOMETRY_FREEZE_V2_ISSUED_ZERO_PHYSICAL")
    expect("freeze_issued_true", payload.get("freeze_issued") is True)
    expect("scope_is_geometry_only", payload.get("scope") == "GEOMETRY_AND_REFERENCE_CONTRACT_ONLY_NO_AERODYNAMIC_VALIDATION")
    expect("physical_solver_starts_zero", payload.get("physical_solver_starts_actual") == 0)
    expect("internal_solver_cases_zero", payload.get("internal_solver_cases_actual") == 0)
    expect("aerodynamic_mask_not_validated", payload.get("aerodynamic_active_mask") == "NOT_VALIDATED")

    contract = builder.contract_payload(config, geometry)
    contract_sha = builder.canonical_sha(contract)
    expect("geometry_contract_sha_recomputes", contract_sha == payload.get("geometry_contract_sha256"),
           {"recomputed": contract_sha, "recorded": payload.get("geometry_contract_sha256")})
    expect("freeze_id_derives_from_contract", payload.get("freeze_id") == "GBFREEZE2-" + contract_sha[:16])
    expect("base_commit_recorded", payload["source"].get("base_commit") == "01c9274801474c113a2c488e375d451bcd0297c3")

    for relative, recorded in payload["source"]["source_sha256"].items():
        path = builder.ROOT / relative
        expect("source_sha256_" + relative, path.is_file() and builder.sha_file(path) == recorded,
               {"recorded": recorded})
    expect("config_sha256_matches", builder.sha_file(builder.CONFIG_PATH) == payload["source"]["config_sha256"])
    runtime_binary = Path(payload["source"]["openvsp_runtime_root"]) / "python/openvsp/openvsp/_vsp.pyd"
    expect("openvsp_runtime_binary_sha256_matches",
           runtime_binary.is_file() and builder.sha_file(runtime_binary) == payload["source"]["openvsp_runtime_binary_sha256"])

    design = payload["design_contract"]
    expect("design_variable_count_12", len(design["design_variables"]) == 12)
    expect("fixed_variable_count_3", len(design["fixed_variables"]) == 3)
    expect("baseline_x12_matches_config", design["baseline_x12"] == [
        builder.rounded(float(item["baseline"])) for item in config["variables"]])
    expect("config_frozen_true", design["config_frozen"] is True)
    expect("bounds_status_recorded", design["bounds_status"] == "frozen_for_dreal001_20261110")

    reference = payload["reference_contract"]
    expect("sref_equals_wing_area", math.isclose(reference["sref_m2"], geometry.wing.area_m2, rel_tol=0.0, abs_tol=1.0e-9))
    expect("cref_equals_mac", math.isclose(reference["cref_m"], geometry.wing.mean_aerodynamic_chord_m, rel_tol=0.0, abs_tol=1.0e-6))
    expect("bref_equals_span", math.isclose(reference["bref_m"], geometry.wing.span_m, rel_tol=0.0, abs_tol=1.0e-6))
    expected_cl = reference["lift_reference_N"] / (reference["q_pa"] * reference["sref_m2"])
    expect("cl_target_recomputes", math.isclose(reference["cl_target"], expected_cl, rel_tol=0.0, abs_tol=1.0e-12))
    expect("lift_reference_is_contractual", "not a performance" in payload["mass_cg_ac_contract"]["lift_reference_note"].lower()
           or "not the takeoff mass" in payload["mass_cg_ac_contract"]["lift_reference_note"].lower())

    mass = payload["mass_cg_ac_contract"]
    components = mass["component_mass_kg"]
    structural_keys = ("wing", "fuselage", "vertical_tail", "landing_gear", "propulsion", "systems")
    structural_sum = sum(float(components[key]) for key in structural_keys)
    expect("structural_masses_sum_to_operating_empty", math.isclose(structural_sum, float(mass["operating_empty_kg"]), rel_tol=0.0, abs_tol=1.0e-6),
           {"sum": structural_sum, "operating_empty_kg": mass["operating_empty_kg"]})
    total_sum = structural_sum + float(components["fuel"]) + float(components["payload"]) + float(components["cargo"])
    expect("mass_budget_sums_to_total_takeoff", math.isclose(total_sum, float(mass["total_takeoff_kg"]), rel_tol=0.0, abs_tol=1.0e-6),
           {"sum": total_sum, "total_takeoff_kg": mass["total_takeoff_kg"]})
    expect("total_takeoff_matches_geometry", math.isclose(float(mass["total_takeoff_kg"]), geometry.mass_kg["total_takeoff"], rel_tol=0.0, abs_tol=1.0e-6))
    expect("cg_matches_geometry", math.isclose(float(mass["cg_x_m"]), geometry.cg_x_m, rel_tol=0.0, abs_tol=1.0e-9))
    expect("static_margin_matches_geometry", math.isclose(float(mass["static_margin"]), geometry.static_margin, rel_tol=0.0, abs_tol=1.0e-12))
    expect("mass_status_provisional", mass["status"] == "PROVISIONAL_NOT_FROZEN")
    expect("cg_status_disclaims_validation", "NOT_A_WEIGHT_AND_BALANCE_VALIDATION" in mass["cg_status"])

    force_axis = payload["force_axis_contract"]
    moment = force_axis["moment_reference_point"]
    expect("force_axis_status_unvalidated", force_axis["status"] == "DEFINED_NOT_SOLVER_VALIDATED")
    expect("moment_origin_ambiguity_disclosed", moment["status"] == "AMBIGUOUS_LOCAL_VERSUS_GLOBAL_ORIGIN_NOT_RESOLVED")
    expect("p2a_xcg_is_wing_local_ac", math.isclose(moment["p2a_xcg_m"], geometry.wing.aerodynamic_center_x_m, rel_tol=0.0, abs_tol=1.0e-9))
    expect("global_ac_adds_origin", math.isclose(moment["geometry_model_wing_ac_global_x_m"],
                                                 moment["p2a_xcg_m"] + builder.WING_ORIGIN_X_M, rel_tol=0.0, abs_tol=1.0e-9))

    for item in payload["consistency_checks"]:
        expect("recorded_consistency_" + item["check"], item["ok"] is True)
    boundary = payload["boundary_perturbation"]
    expect("model_boundary_cases_24", len(boundary["cases"]) == 24)
    expect("model_boundary_cases_all_ok", all(case.get("model_ok") is True for case in boundary["cases"]))
    expect("native_boundary_cases_24", len(boundary["native_openvsp_cases"]) == 24)
    expect("native_boundary_cases_all_ok", all(case.get("all_checks_ok") is True for case in boundary["native_openvsp_cases"]))
    expect("native_boundary_cases_count_ok", boundary["native_cases_ok"] == 24 and boundary["native_cases_total"] == 24)

    export = payload["real_openvsp_export"]
    artifact_paths = {}
    for fmt, row in export["exports"].items():
        path = builder.ROOT / row["path"]
        artifact_paths[fmt] = path
        expect("export_%s_exists" % fmt, path.is_file())
        expect("export_%s_bytes" % fmt, path.is_file() and path.stat().st_size == row["bytes"])
        expect("export_%s_sha256" % fmt, path.is_file() and builder.sha_file(path) == row["sha256"])
    for name, row in export["component_stls"].items():
        path = builder.ROOT / row["path"]
        expect("component_stl_%s_exists" % name, path.is_file())
        expect("component_stl_%s_bytes" % name, path.is_file() and path.stat().st_size == row["bytes"])
        expect("component_stl_%s_sha256" % name, path.is_file() and builder.sha_file(path) == row["sha256"])
        expect("component_stl_%s_bounds_recompute" % name, path.is_file() and builder.stl_bounds(path) == row["bounds"])
    expect("assembly_stl_bounds_recompute", builder.stl_bounds(Path(export["exports"]["stl"]["path"])) == export["assembly_stl_bounds"])

    for component in export["components"]:
        expected = builder.expected_xform(component)
        actual = export["xform_readback"][component["name"]]
        for key, value in expected.items():
            expect("xform_%s_%s" % (component["name"], key),
                   math.isfinite(actual[key]) and math.isclose(actual[key], value, rel_tol=0.0, abs_tol=1.0e-8))
    expect("stl_placement_checks_all_ok", all(item["ok"] is True for item in export["stl_placement_checks"]))

    vsp = builder.worker.import_openvsp(str(builder.OPENVSP_ROOT))
    vsp.ReadVSPFile(str(artifact_paths["vsp3"]))
    handles = {vsp.GetGeomName(geom_id): geom_id for geom_id in vsp.FindGeoms()}
    expect("vsp3_has_three_components", set(handles) == {"main_wing", "vertical_tail", "fuselage"}, sorted(handles))
    if "main_wing" in handles:
        expect("vsp3_wing_area_matches", math.isclose(
            float(vsp.GetParmVal(handles["main_wing"], "TotalArea", "WingGeom")), geometry.wing.area_m2,
            rel_tol=1.0e-9, abs_tol=1.0e-9))
        expect("vsp3_wing_span_matches", math.isclose(
            float(vsp.GetParmVal(handles["main_wing"], "TotalSpan", "WingGeom")), geometry.wing.span_m,
            rel_tol=1.0e-9, abs_tol=1.0e-9))
        expect("vsp3_wing_xform_matches", math.isclose(
            float(vsp.GetParmVal(vsp.GetParm(handles["main_wing"], "X_Location", "XForm"))), builder.WING_ORIGIN_X_M,
            rel_tol=0.0, abs_tol=1.0e-8))
    if "vertical_tail" in handles:
        expect("vsp3_tail_area_matches", math.isclose(
            float(vsp.GetParmVal(handles["vertical_tail"], "TotalArea", "WingGeom")), geometry.vertical_tail.area_m2,
            rel_tol=1.0e-9, abs_tol=1.0e-9))
        expect("vsp3_tail_xform_matches", math.isclose(
            float(vsp.GetParmVal(vsp.GetParm(handles["vertical_tail"], "X_Location", "XForm"))), builder.TAIL_ORIGIN_X_M,
            rel_tol=0.0, abs_tol=1.0e-8))
    if "fuselage" in handles:
        expect("vsp3_fuselage_length_matches", math.isclose(
            float(vsp.GetParmVal(vsp.GetParm(handles["fuselage"], "Length", "Design"))), geometry.fuselage.length_m,
            rel_tol=1.0e-9, abs_tol=1.0e-9))

    result = {
        "schema": "drecover001.geometry_freeze_v2_verification.v1",
        "freeze_id": payload["freeze_id"],
        "geometry_contract_sha256": payload["geometry_contract_sha256"],
        "freeze_json_path": builder.rel(FREEZE_PATH),
        "freeze_json_sha256": builder.sha_file(FREEZE_PATH),
        "check_count": len(checks),
        "failure_count": len(failures),
        "failures": failures,
        "checks": checks,
        "status": "GEOMETRY_FREEZE_V2_VERIFIED" if not failures else "GEOMETRY_FREEZE_V2_VERIFICATION_FAILED",
        "physical_solver_starts_actual": 0,
        "internal_solver_cases_actual": 0,
    }
    VERIFY_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "freeze_id": result["freeze_id"],
        "geometry_contract_sha256": result["geometry_contract_sha256"],
        "freeze_json_sha256": result["freeze_json_sha256"],
        "verification_sha256": builder.sha_file(VERIFY_PATH),
        "check_count": result["check_count"],
        "failure_count": result["failure_count"],
        "physical_solver_starts_actual": 0,
    }, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
