
"""P0: 12D design-variable wiring and response audit (zero new physical starts).

Part 1 (static, solver-free): perturb every one of the 15 design variables and
show what changes in the geometry contract, i.e. in the quantities that
openvsp_model.geometry_component_specs() writes into the VSPAERO model.

Part 2 (existing raw data only): for design pairs the G2 stage-1 batch already
solved at the same task/Mach (d00 baseline vs d01 area+1%, d02/d04 sweep_1
+/-0.5 deg, d05 vertical-tail area +2%, d06 sweep_2 +0.5 deg, d07 fuselage
length -1%), compare the real CLtot/CDo/CDi/CDtot rows at identical alpha and
also prove the deck really changed (geometry/SHA).  V02
(vertical_tail_sweep_delta) has no existing perturbed raw case, so its response
is reported as pending a P1 probe instead of being inferred.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.concorde_metaopt.aircraft.geometry_model import build_geometry  # noqa: E402
from research.concorde_metaopt.dreal001.geometry.polar_rows import read_polar_rows  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
G2_RUN = Path("D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01")

NAMES = ["wing_area", "aspect_ratio", "sweep_1", "sweep_2", "sweep_3",
         "span_location_2", "span_location_3", "chord_ratio_2", "chord_ratio_3",
         "tip_twist", "vertical_tail_area", "vertical_tail_sweep_delta",
         "fuselage_length", "fuselage_fineness", "fuselage_height_width_ratio"]
BASELINE = [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284,
            0.130178, 0.0, 33.91, 0.0, 61.66, 4.30, 1.152778]

DESIGNS = {
    "d00": (None, "baseline"),
    "d01": (0, "wing_area +1%"),
    "d02": (2, "sweep_1 +0.5 deg"),
    "d03": (0, "wing_area -1%"),
    "d04": (2, "sweep_1 -0.5 deg"),
    "d05": (10, "vertical_tail_area +2%"),
    "d06": (3, "sweep_2 +0.5 deg"),
    "d07": (12, "fuselage_length -1%"),
}
PARTITION = {"d00": "support", "d01": "support", "d02": "support", "d03": "support",
             "d04": "query", "d05": "query", "d06": "query", "d07": "query"}
PERTURB = {"angle": 0.5, "delta": 0.02, "ratio": 0.01}
ANGLE_INDICES = {2, 3, 4, 9}


def perturbed_vector(index: int) -> list[float]:
    values = BASELINE[:]
    if index in ANGLE_INDICES:
        values[index] += PERTURB["angle"]
    elif index == 11:
        values[index] += PERTURB["delta"]
    else:
        values[index] = values[index] * (1.0 + PERTURB["ratio"])
    return values


def geometry_snapshot(values: list[float]) -> dict:
    as_dict = build_geometry(NAMES, values).to_dict()
    wing = as_dict["main_wing"]
    tail = as_dict["vertical_stabilizer"]
    fuselage = as_dict["fuselage"]

    def sections(component):
        return [[s["percent_span_location"], s["chord_m"],
                 s["quarter_chord_sweep_deg"], s["twist_deg"],
                 s["leading_edge_x_m"]] for s in component["sections"]]

    stations = [[s["percent_x_location"], s["width_m"], s["height_m"]]
                for s in fuselage.get("stations", [])]
    return {
        "wing_area_m2": wing["area_m2"],
        "wing_span_m": wing.get("span_m"),
        "wing_sections": sections(wing),
        "vertical_tail_area_m2": tail["area_m2"],
        "vertical_tail_span_m": tail.get("span_m"),
        "vertical_tail_sections": sections(tail),
        "fuselage_length_m": fuselage.get("length_m"),
        "fuselage_width_m": fuselage.get("width_m"),
        "fuselage_height_m": fuselage.get("max_height_m"),
        "fuselage_stations": stations,
        "mass_kg": as_dict.get("mass_kg"),
        "cg_x_m": as_dict.get("cg_x_m"),
        "sref_m2": wing["area_m2"],
    }


def relative_change(new, old):
    if old is None or new is None:
        return None
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        if old == 0:
            return None if new == 0 else float("inf")
        return (new - old) / old
    return None


def static_audit() -> list[dict]:
    base = geometry_snapshot(BASELINE)
    out = []
    for index, name in enumerate(NAMES):
        snap = geometry_snapshot(perturbed_vector(index))
        changes = {}
        for key in base:
            if base[key] != snap[key]:
                changes[key] = {"baseline": base[key], "perturbed": snap[key],
                                "relative": relative_change(snap[key], base[key])}
        out.append({
            "index": index,
            "variable": name,
            "perturbation": ("+0.5 deg" if index in ANGLE_INDICES
                             else "+0.02" if index == 11 else "+1% relative"),
            "changed_geometry_fields": sorted(changes),
            "changes": changes,
            "wired_into_solver_model": bool(changes),
        })
    return out


def load_case(case_id: str):
    case_dir = G2_RUN / "cases" / case_id
    polar = case_dir / ("%s.polar" % case_id)
    if not polar.exists():
        return None, None
    task_path = case_dir / "task_spec.json"
    mach = float(json.loads(task_path.read_text(encoding="utf-8"))["mach"])
    rows = read_polar_rows(polar, mach=mach)
    inputs = {}
    inputs_path = case_dir / "case_inputs.json"
    if inputs_path.exists():
        inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    return rows, {"geometry_sha256": inputs.get("geometry_sha256"),
                  "vspaero_input_sha256": inputs.get("vspaero_input_sha256")}


def response_audit() -> list[dict]:
    tags = sorted({p.name.split("-")[1] for p in (G2_RUN / "cases").iterdir()
                   if p.is_dir() and p.name.startswith("g2-m")
                   and p.name.endswith("-s1")})
    out = []
    for tag in tags:
        for design, (index, description) in DESIGNS.items():
            if index is None:
                continue
            base_id = "g2-%s-d00-support-s1" % tag
            variant_id = "g2-%s-%s-%s-s1" % (tag, design, PARTITION[design])
            base_rows, base_meta = load_case(base_id)
            var_rows, var_meta = load_case(variant_id)
            entry = {
                "task_tag": tag,
                "design": design,
                "variable": NAMES[index],
                "variation": description,
                "baseline_case": base_id,
                "variant_case": variant_id,
                "baseline_geometry_sha256": (base_meta or {}).get("geometry_sha256"),
                "variant_geometry_sha256": (var_meta or {}).get("geometry_sha256"),
                "deck_changed": bool(base_meta and var_meta
                                     and base_meta.get("geometry_sha256")
                                     != var_meta.get("geometry_sha256")),
                "status": "NO_EXISTING_RAW_PAIR",
            }
            if base_rows and var_rows:
                base_map = {round(r.alpha_deg, 6): r for r in base_rows}
                var_map = {round(r.alpha_deg, 6): r for r in var_rows}
                common = sorted(set(base_map) & set(var_map))
                if common:
                    def mean_delta(attr):
                        values = [getattr(var_map[a], attr) - getattr(base_map[a], attr)
                                  for a in common]
                        return sum(values) / len(values)
                    entry.update({
                        "matched_alpha_rows": len(common),
                        "alpha_min_deg": common[0],
                        "alpha_max_deg": common[-1],
                        "delta_cl_total_mean": mean_delta("cl"),
                        "delta_cl_total_max_abs": max(abs(getattr(var_map[a], "cl")
                                                         - getattr(base_map[a], "cl"))
                                                      for a in common),
                        "delta_cdo_mean": mean_delta("cdo"),
                        "delta_cdi_mean": mean_delta("cdi"),
                        "delta_cdi_max_abs": max(abs(getattr(var_map[a], "cdi")
                                                     - getattr(base_map[a], "cdi"))
                                                 for a in common),
                        "delta_cdtot_mean": mean_delta("cdtot"),
                        "status": "RESPONSE_MEASURED_ON_EXISTING_RAW_ROWS",
                    })
            out.append(entry)
    out.append({
        "task_tag": "ALL",
        "design": "V02_probe",
        "variable": "vertical_tail_sweep_delta",
        "variation": "+0.02 (not present in any existing case; geometry wiring verified statically)",
        "baseline_case": None,
        "variant_case": None,
        "deck_changed": None,
        "matched_alpha_rows": 0,
        "delta_cl_total_mean": None,
        "delta_cdo_mean": None,
        "delta_cdi_mean": None,
        "delta_cdtot_mean": None,
        "status": "RESPONSE_PENDING_P1_PROBE",
    })
    return out


def summarize_v01(responses: list[dict]) -> dict:
    rows = [r for r in responses if r["variable"] == "vertical_tail_area"
            and r["status"] == "RESPONSE_MEASURED_ON_EXISTING_RAW_ROWS"]
    if not rows:
        return {"status": "NO_EXISTING_V01_PAIR"}
    return {
        "status": "MEASURED",
        "tasks": len(rows),
        "deck_changed_all_tasks": all(r["deck_changed"] for r in rows),
        "delta_cl_total_mean_abs": sum(abs(r["delta_cl_total_mean"]) for r in rows) / len(rows),
        "delta_cdi_mean_abs": sum(abs(r["delta_cdi_mean"]) for r in rows) / len(rows),
        "delta_cdi_exactly_zero_all_tasks": all(r["delta_cdi_max_abs"] == 0.0 for r in rows),
        "delta_cdo_mean": sum(r["delta_cdo_mean"] for r in rows) / len(rows),
        "interpretation": (
            "V01 (+2% vertical-tail area) changes the VSPAERO deck (geometry SHA differs) "
            "and the parasitic drag (CDo) by a small positive amount, but at zero sideslip "
            "the vertical tail is unloaded, so CDi stays exactly constant and CLtot moves "
            "only ~1e-6 (relative ~3e-6). V01 therefore cannot move the primary endpoint "
            "Di_N = q*Sref*CDi under the current beta=0 task condition."),
        "recommendation": (
            "Treat V01/V02 as passive geometry variables for the current beta=0 tasks: keep "
            "them in the 12D contract for geometry validity but do not count them as active "
            "optimization dimensions in P2/P3, OR add a beta != 0 (tail-loaded) task family "
            "in P1/P2 before claiming a 12D response for them. V02 still needs a direct probe."),
    }


def main() -> int:
    static = static_audit()
    responses = response_audit()
    measured = [r for r in responses if r["status"] == "RESPONSE_MEASURED_ON_EXISTING_RAW_ROWS"]
    payload = {
        "schema": "dreal004.p0.variable_response_audit.v1",
        "design_variable_count": len(NAMES),
        "static_wiring_all_variables_connected": all(s["wired_into_solver_model"] for s in static),
        "static": static,
        "raw_response_pairs_measured": len(measured),
        "raw_response_pairs_unavailable": len(responses) - len(measured),
        "vertical_tail_area_analysis": summarize_v01(responses),
        "vertical_tail_sweep_delta_response": "RESPONSE_PENDING_P1_PROBE",
        "physical_solver_starts_used": 0,
        "responses": responses,
    }
    (OUT_DIR / "12d_variable_response_audit.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    with (OUT_DIR / "12d_variable_response_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["task_tag", "design", "variable", "variation", "status", "deck_changed",
                  "matched_alpha_rows", "delta_cl_total_mean", "delta_cdo_mean",
                  "delta_cdi_mean", "delta_cdtot_mean"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in responses:
            writer.writerow(row)
    print(json.dumps({
        "all_variables_wired": payload["static_wiring_all_variables_connected"],
        "raw_response_pairs_measured": payload["raw_response_pairs_measured"],
        "v01": {k: payload["vertical_tail_area_analysis"].get(k) for k in
                ("status", "tasks", "deck_changed_all_tasks",
                 "delta_cdi_exactly_zero_all_tasks")},
        "v02": payload["vertical_tail_sweep_delta_response"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
