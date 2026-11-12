"""Zero-physics freeze of the 12D lifting-surface design space (D-REAL-001 A1).

Builds the baseline geometry and one +10%-of-range perturbation per design variable
through aircraft/geometry_model.build_geometry, checks bounds / cross constraints /
physical legality, and records the geometric effect.  NO OpenVSP model build and NO
solver start: this file is geometric evidence only.  V01/V02 aerodynamic activation is
PENDING_P1 and must be decided by the preregistered P1-07 probe.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

GEOMETRY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GEOMETRY_DIR.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.concorde_metaopt.aircraft.design_space import load_design_space  # noqa: E402
from research.concorde_metaopt.aircraft.geometry_model import build_geometry  # noqa: E402

SCHEMA = "dreal001.design_space_freeze.v1"
CONFIG_REL = "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"
PROBE_FRACTION_OF_RANGE = 0.10
LHS_SAMPLES = 256
SEED = 20261110
VARIABLE_IDS = ["W%02d" % i for i in range(1, 11)] + ["V01", "V02"]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def geometry_metrics(geometry: Any) -> Dict[str, Any]:
    wing = geometry.wing
    tail = geometry.vertical_tail
    return {
        "wing": {
            "area_m2": wing.area_m2, "span_m": wing.span_m,
            "root_chord_m": wing.root_chord_m, "tip_chord_m": wing.tip_chord_m,
            "mac_m": wing.mean_aerodynamic_chord_m,
            "aerodynamic_center_x_m": wing.aerodynamic_center_x_m,
            "exposed_area_m2": wing.exposed_area_m2,
            "wetted_area_m2": wing.wetted_area_m2,
            "sections": [{"span_frac": s.percent_span_location, "chord_m": s.chord_m,
                          "sweep_deg": s.quarter_chord_sweep_deg,
                          "twist_deg": s.twist_deg, "le_x_m": s.leading_edge_x_m}
                         for s in wing.sections],
        },
        "vertical_tail": {
            "area_m2": tail.area_m2, "span_m": tail.span_m,
            "root_chord_m": tail.root_chord_m, "tip_chord_m": tail.tip_chord_m,
            "mac_m": tail.mean_aerodynamic_chord_m,
            "sections": [{"span_frac": s.percent_span_location, "chord_m": s.chord_m,
                          "sweep_deg": s.quarter_chord_sweep_deg,
                          "twist_deg": s.twist_deg, "le_x_m": s.leading_edge_x_m}
                         for s in tail.sections],
        },
        "fuselage_length_m": geometry.fuselage.length_m,
        "total_mass_kg": geometry.mass_kg.get("total_takeoff") if isinstance(geometry.mass_kg, dict) else None,
        "cg_x_m": geometry.cg_x_m,
    }


def build(space: Any, values12: List[float]) -> Any:
    names = [v.name for v in space.variables] + [f.name for f in space.fixed_variables]
    baseline = space.baseline_dict()
    full = dict(baseline)
    for fixed in space.fixed_variables:
        full[fixed.name] = float(fixed.baseline)
    for variable, value in zip(space.variables, values12):
        full[variable.name] = float(value)
    vector = [float(full[name]) for name in names]
    return build_geometry(names, vector)


def main() -> int:
    config_path = REPO_ROOT / CONFIG_REL
    space = load_design_space(str(config_path))
    names = [v.name for v in space.variables]
    baseline_values = [float(v.baseline) for v in space.variables]
    baseline_geometry = build(space, baseline_values)
    baseline_metrics = geometry_metrics(baseline_geometry)
    baseline_physical = dict(space.baseline_dict())
    baseline_issues = {
        "check_bounds": space.check_bounds(baseline_physical),
        "check_cross_constraints": space.check_cross_constraints(baseline_physical),
        "check_physical": space.check_physical(baseline_physical),
    }

    # deterministic unit-space sampling of the full box for cross-constraint legality
    rng = np.random.default_rng(SEED)
    samples = rng.random((LHS_SAMPLES, len(names)))
    violation_count = 0
    violation_examples: List[Dict[str, Any]] = []
    for row in samples:
        physical = space.from_unit_interval(row)
        issues = space.check_physical(physical)
        if issues:
            violation_count += 1
            if len(violation_examples) < 5:
                violation_examples.append({"physical": physical, "issues": issues})

    probes: List[Dict[str, Any]] = []
    for index, variable in enumerate(space.variables):
        low, high = variable.bounds
        step = PROBE_FRACTION_OF_RANGE * (float(high) - float(low))
        probe_value = min(float(high), float(variable.baseline) + step)
        values = list(baseline_values)
        values[index] = probe_value
        probe_geometry = build(space, values)
        probe_metrics = geometry_metrics(probe_geometry)
        physical = dict(space.baseline_dict())
        physical[variable.name] = probe_value
        wing = probe_metrics["wing"]
        tail = probe_metrics["vertical_tail"]
        probes.append({
            "id": VARIABLE_IDS[index], "name": variable.name, "unit": variable.unit,
            "baseline": float(variable.baseline), "probe_value": probe_value,
            "delta": probe_value - float(variable.baseline),
            "delta_fraction_of_range": PROBE_FRACTION_OF_RANGE,
            "bounds": [float(low), float(high)],
            "bounds_ok": space.check_bounds(physical),
            "cross_constraints_ok": space.check_cross_constraints(physical),
            "physical_ok": space.check_physical(physical),
            "geometric_deltas": {
                "wing_area_m2": wing["area_m2"] - baseline_metrics["wing"]["area_m2"],
                "wing_span_m": wing["span_m"] - baseline_metrics["wing"]["span_m"],
                "wing_mac_m": wing["mac_m"] - baseline_metrics["wing"]["mac_m"],
                "wing_sections": wing["sections"],
                "vertical_tail_area_m2": tail["area_m2"] -
                                        baseline_metrics["vertical_tail"]["area_m2"],
                "vertical_tail_span_m": tail["span_m"] -
                                        baseline_metrics["vertical_tail"]["span_m"],
                "vertical_tail_sections": tail["sections"],
            },
        })

    summary = space.config_summary()
    payload = {
        "schema": SCHEMA,
        "generated_utc": utc_now(),
        "source_config": {"path": CONFIG_REL, "sha256": sha256_file(config_path),
                          "frozen": summary.get("frozen"),
                          "stage": summary.get("stage"),
                          "bounds_status": summary.get("bounds_status"),
                          "freeze_note": summary.get("freeze_note")},
        "design_space_status": {
            "geometry_frozen_for_p0": True,
            "bounds_frozen_for_p0": True,
            "aero_activation_pending_p1": True,
            "frozen_flag_in_config": bool(summary.get("frozen")),
            "bounds_status": summary.get("bounds_status"),
            "freeze_note": summary.get("freeze_note"),
            "freeze_decision": {
                "document": "docs/planning/dreal001_lead_decisions_20261110.md",
                "commit": "3624db7",
                "items": ["L-01 Sref 358.25 m^2", "L-02 vertical-tail semi-span 5.009331 m",
                          "L-03 frozen 12D bounds"],
                "date": "2026-11-10",
            },
            "note": "The 12 geometry bounds are frozen for DREAL001 by L-03 after the zero-physics "
                    "P0 checks below. Freezing the geometry contract does not validate the "
                    "aerodynamics: V01/V02 activation remains PENDING_P1_AERO_SENSITIVITY and no "
                    "aero claim is made in this file.",
        },
        "resolved_by_decision": {
            "L-01": {
                "issue": "Sref candidates: 358.25 m^2 exposed main-wing reference vs upstream 326.5 m^2",
                "resolution": "Sref = 358.25 m^2 (exposed main-wing reference area). "
                              "The upstream 326.5 m^2 value is not adopted.",
                "evidence": "baseline_geometry.wing.exposed_area_m2 == 358.25",
            },
            "L-02": {
                "issue": "vertical-tail semi-span: upstream 6.0 m vs derived 5.009331 m",
                "resolution": "The VLM vertical-tail component uses the AR = 0.74 derivation "
                              "sqrt(33.91 * 0.74) = 5.009331 m; the upstream 6.0 m is not used "
                              "for the VLM component.",
                "evidence": "baseline_geometry.vertical_tail.span_m",
            },
            "L-03": {
                "issue": "12 bounds declared frozen:false / bounds_status provisional",
                "resolution": "The 12D config is frozen:true with bounds_status "
                              "frozen_for_dreal001_20261110 and a freeze_note naming L-03.",
                "evidence": "source_config.frozen and source_config.bounds_status",
            },
        },
        "reference_quantities": {
            "Sref_m2": baseline_metrics["wing"]["exposed_area_m2"],
            "Cref_m": baseline_metrics["wing"]["mac_m"],
            "Bref_m": baseline_metrics["wing"]["span_m"],
            "wing_ac_x_m": baseline_metrics["wing"]["aerodynamic_center_x_m"],
            "geometry_cg_x_m": baseline_metrics["cg_x_m"],
            "wing_ac_interpretation": "wing_ac_x_m = main-wing aerodynamic centre (quarter-MAC "
                                      "leading-edge offset). This is the X_cg value injected "
                                      "into VSPAERO (RefFlag=0, reference_frame=WING_AC) and is "
                                      "a wing-only moment reference, not the aircraft CG.",
            "geometry_cg_interpretation": "geometry_cg_x_m = full-aircraft CG of the geometric "
                                          "mass model (OEW 78,700 kg distributed over wing/body/"
                                          "tail). It is the geometric CG used for static-margin "
                                          "diagnostics only; the mass and CG contract is "
                                          "PROVISIONAL_NOT_FROZEN.",
            "wing_ac_is_aircraft_cg": False,
            "cg_ac_offset_m": baseline_metrics["cg_x_m"] -
                              baseline_metrics["wing"]["aerodynamic_center_x_m"],
            "use_rule": "NEVER substitute wing_ac_x_m for the aircraft CG, and never use the "
                        "17-18 m lever arm for trim, static-stability or fuel-burn conclusions.",
            "Sref_rule": "Sref(x) = exposed main-wing planform area, recomputed for every design",
        },
        "variable_ids": VARIABLE_IDS,
        "variables": [{
            "id": VARIABLE_IDS[i], "name": v.name, "unit": v.unit,
            "bounds": [float(b) for b in v.bounds], "baseline": float(v.baseline),
            "range_span": float(v.bounds[1]) - float(v.bounds[0]),
            "range_pct_of_baseline": (100.0 * (float(v.bounds[1]) - float(v.bounds[0]))
                                      / float(v.baseline)) if float(v.baseline) != 0.0 else None,
            "solver_geometry_effect": (
                "Sref(x) = exposed main-wing planform area" if v.name == "wing_area"
                else "vertical-tail planform (solver component vertical_tail)" if
                v.name in ("vertical_tail_area", "vertical_tail_sweep_delta")
                else "main-wing planform / section geometry"),
        } for i, v in enumerate(space.variables)],
        "fixed_variables": [{
            "id": "F%02d" % (i + 1), "name": f.name, "value": float(f.baseline),
            "in_12d": False, "in_solver_geometry": False,
            "note": "fuselage is fixed and excluded from the VSPAERO lifting-surface model",
        } for i, f in enumerate(space.fixed_variables)],
        "cross_constraints": summary.get("cross_constraints") or
                             getattr(space, "cross_constraints", None),
        "derived_rules": summary.get("derived_rules") or getattr(space, "derived_rules", None),
        "baseline_geometry": baseline_metrics,
        "baseline_checks": baseline_issues,
        "unit_space_sampling": {
            "method": "uniform random in unit cube (seed %d)" % SEED,
            "samples": LHS_SAMPLES,
            "violations": violation_count,
            "violation_fraction": violation_count / float(LHS_SAMPLES),
            "violation_examples": violation_examples,
            "note": "check_physical aggregates bounds/cross/positivity; rejects are design-space "
                    "artifacts only, no solver invoked",
        },
        "zero_physics_perturbation_probes": probes,
        "main_wing_twist": {
            "variable": "W10 tip_twist", "unit": "deg", "bounds": [-4.0, 4.0],
            "baseline_deg": baseline_metrics["wing"]["sections"][-1]["twist_deg"],
            "sections_twist_deg": [s["twist_deg"] for s in baseline_metrics["wing"]["sections"]],
            "mapping": "W10 sets the tip (last) wing section twist only; root/intermediate "
                       "sections stay at 0 deg; OpenVSP applies per-section Twist around the "
                       "leading edge in openvsp_geometry._add_wing",
        },
        "vertical_tail_in_lf_solver": {
            "in_solver_geometry": True,
            "components": ["main_wing", "vertical_tail"],
            "fuselage_in_solver": False,
            "evidence": "research/concorde_metaopt/dreal001/geometry/openvsp_model.py "
                        "COMPONENT_DEFS; two components in every .vspgeom",
            "v01_v02_aero_status": "PENDING_P1_AERO_SENSITIVITY",
            "decision_rule": "if P1-07 |delta D_i|/D_i < 0.1% for both V01 and V02 at matched "
                             "lift, label the space 10D_ACTIVE_PLUS_2_INACTIVE; otherwise keep "
                             "12D_ACTIVE. No aero claim before P1.",
        },
        "evidence_scope": {
            "physical_solver_starts": 0,
            "builds_openvsp_or_solver": False,
            "kind": "ZERO_PHYSICS_GEOMETRY_ONLY",
            "claim": "geometry legality and variable identification only; no aerodynamic effect",
        },
    }
    output_path = GEOMETRY_DIR / "design_space_freeze.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({"output": str(output_path),
                      "baseline_issues": baseline_issues,
                      "sampling_violations": violation_count,
                      "probes": len(probes),
                      "config_sha256": payload["source_config"]["sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
