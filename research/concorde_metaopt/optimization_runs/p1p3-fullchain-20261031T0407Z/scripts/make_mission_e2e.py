"""Assemble mission_e2e.json for the D-12D-002 full-chain run.

Sources (all read-only):
  * the four RCAIDE single-cruise evaluation records produced in this run
  * the archived P2 smoke run (for a reproduction cross-check)
  * the wave-drag / area-rule deliverable (for the candidate body increment)
  * the budget ledger (for the accounting section)
No solver is started here.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
REPO = Path("D:/RCAIDE")
RUN = REPO / "research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z"

CASES = ["E2E-00", "E2E-01", "LFV-04", "LFV-05"]
CASE_ROLE = {
    "E2E-00": "baseline 12D lifting-surface design through the instrumented RCAIDE single-cruise chain",
    "E2E-01": "W10 tip_twist=+2 deg through the same instrumented chain",
    "LFV-04": "V01 vertical_tail_area +1% (34.2491 m2) sensitivity",
    "LFV-05": "V02 vertical_tail_sweep_delta=+2 deg sensitivity",
}
RESP_KEYS = ["mass_start_kg", "mass_end_kg", "fuel_burn_kg", "max_throttle",
             "max_thrust_x_n", "max_fuel_mass_flow_kg_s", "alpha_end_deg",
             "lift_coefficient_end", "drag_coefficient_end", "residual_max",
             "converged", "solver_converged", "range_span_m", "time_span_s"]


def load_case(case):
    rec = json.loads((EXT / "lf_mission" / (case + ".json")).read_text())
    resp = rec["responses"]
    ledger = resp.get("drag_ledger") or {}
    out = {
        "case_id": case,
        "role": CASE_ROLE[case],
        "status": rec["status"],
        "feasible": rec["feasible"],
        "objective_fuel_burn_kg": rec["objective"],
        "design": rec["design"],
        "design_dim": rec["design_dim"],
        "design_set": rec["design_set"],
        "task_id": rec["task_id"],
        "task_fingerprint": rec["task_fingerprint"],
        "physical_call_count": rec.get("physical_call_count"),
        "call_accounting": rec.get("call_accounting"),
        "responses": {k: resp.get(k) for k in RESP_KEYS},
        "propulsors": resp.get("propulsors"),
        "constraints": rec["constraints"],
        "geometry_cross_check": rec.get("geometry_cross_check"),
        "drag_ledger": ledger,
    }
    return out


def main():
    cases = {c: load_case(c) for c in CASES}
    baseline = cases["E2E-00"]["objective_fuel_burn_kg"]
    for c in CASES:
        cases[c]["delta_vs_E2E_00_kg"] = cases[c]["objective_fuel_burn_kg"] - baseline
        cases[c]["delta_vs_E2E_00_pct"] = 100.0 * (cases[c]["objective_fuel_burn_kg"] - baseline) / baseline

    archive_summary = json.loads((REPO / "research/concorde_metaopt/optimization_runs/"
                                  "smoke-p2-20261029T1612/summary.json").read_text())
    smoke = archive_summary["smoke"]
    pert = {p["label"]: p for p in smoke.get("perturbations", [])}
    archive = {
        "path": "research/concorde_metaopt/optimization_runs/smoke-p2-20261029T1612",
        "baseline_fuel_burn_kg": smoke["baseline"]["objective"],
        "W10_plus_2deg_fuel_burn_kg": pert.get("W10_plus_2deg", {}).get("objective"),
        "W01_plus_1pct_fuel_burn_kg": pert.get("W01_plus_1pct", {}).get("objective"),
        "best_feasible_fuel_kg": archive_summary.get("best_feasible_fuel_kg"),
        "note": "archived run used the 15D config and the RCAIDE tutorial vehicle; E2E-00/01 "
                "reproduce its baseline and W10 numbers to the last digit because the 12D design "
                "expands to the same 15D baseline vector",
    }

    wave = json.loads((RUN / "wave_drag_area_rule.json").read_text())
    inc = wave["fuselage_zero_lift_volume_wave_drag_increment"]["baseline_pair"]
    delta_cd = inc["delta_CD_on_Sref"]
    q_frozen = wave["frozen_conditions"]["q_inf_pa"]
    q_mission = cases["E2E-00"]["drag_ledger"]["dynamic_pressure_pa"]
    sref = cases["E2E-00"]["drag_ledger"]["reference_area_m2"]
    total_drag = cases["E2E-00"]["drag_ledger"]["total_drag_magnitude_n"]
    delta_drag_n = delta_cd * q_mission * sref
    drag_fraction = delta_drag_n / total_drag
    est_fuel = baseline * (1.0 + drag_fraction)
    offline_estimate = {
        "candidate_delta_CD": delta_cd,
        "q_used_pa": q_mission,
        "delta_drag_N": delta_drag_n,
        "total_drag_N": total_drag,
        "relative_drag_fraction": drag_fraction,
        "naive_linear_fuel_estimate_kg": est_fuel,
        "fuel_loaded_kg": 46800.0,
        "max_throttle_at_baseline": cases["E2E-00"]["responses"]["max_throttle"],
        "feasible_if_injected": False,
        "why": "a +48 percent drag increment would push the required thrust far past the "
               "0.945 throttle needed at baseline; the naive linear fuel estimate already exceeds "
               "the 46800 kg fuel load, so the mission would be infeasible. This is an order-of-"
               "magnitude warning, NOT a validated correction."
    }

    ledger = json.loads((RUN / "approval_and_budget_ledger.json").read_text())
    events = [e for e in ledger["numerical_analysis_events"]]
    used = {cat: sum(1 for e in events if e.get("category") == cat) for cat in
            ["VSPAERO_LF", "RCAIDE_LF", "SU2_HF", "WAVE_AREA_RULE"]}

    doc = {
        "schema_version": 1,
        "component": "MISSION_E2E",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "approval": "Issue #4 / D-12D-002 (comment 6538481816)",
        "run_id": RUN.name,
        "chain": {
            "backend": "research/concorde_metaopt/evaluation/low_fidelity.py::SingleCruiseBackend",
            "task": "concorde-fixed-cruise-p2-v1 (frozen mass contract, 136000 kg start mass)",
            "design_set": "12d_lifting_surfaces (W01-W10 + V01-V02; F01-F03 fixed)",
            "mission": "single constant-Mach constant-altitude cruise segment, Mach 2.02, 18288 m, 3028020 m",
            "aerodynamics": "RCAIDE Vortex_Lattice_Method with default use_surrogate=True "
                            "(11 Mach x 7 AoA training grid, Mach 2.02 inside the 2.0-2.5 interval)",
        },
        "frozen_conditions_from_approval": {
            "mach": 2.02, "altitude_m": 18288.0, "range_m": 3028020.0,
            "start_mass_kg": 136000.0, "Sref_m2": 358.25, "cref_m": 18.489893,
            "bref_m": 25.604638,
            "dynamic_pressure_pa_isa": q_frozen,
        },
        "observed_mission_dynamic_pressure_pa": q_mission,
        "dynamic_pressure_note": (
            "The RCAIDE/SUAVE mission atmosphere gives q = %.3f Pa at 18288 m / Mach 2.02, "
            "0.83%% above the %.3f Pa used to freeze the LF/HF solver inputs (implied density "
            "%.6f vs %.6f kg/m3). The two chains are therefore consistent to within 0.83%% in q; "
            "this is recorded as a caveat, not corrected." % (q_mission, q_frozen,
                                                             q_mission / (0.5 * 596.0373972278921 ** 2),
                                                             0.1153178340089936)),
        "archive_reproduction_check": {
            "archived_run": archive["path"],
            "archived_baseline_fuel_burn_kg": archive["baseline_fuel_burn_kg"],
            "archived_W10_plus_2deg_fuel_burn_kg": archive["W10_plus_2deg_fuel_burn_kg"],
            "archived_best_feasible_fuel_kg": archive["best_feasible_fuel_kg"],
            "E2E_00_fuel_burn_kg": baseline,
            "E2E_01_fuel_burn_kg": cases["E2E-01"]["objective_fuel_burn_kg"],
            "baseline_abs_difference_kg": abs(baseline - archive["baseline_fuel_burn_kg"]),
            "W10_abs_difference_kg": abs(cases["E2E-01"]["objective_fuel_burn_kg"]
                                         - archive["W10_plus_2deg_fuel_burn_kg"]),
            "match": (abs(baseline - archive["baseline_fuel_burn_kg"]) < 1e-6
                      and abs(cases["E2E-01"]["objective_fuel_burn_kg"]
                              - archive["W10_plus_2deg_fuel_burn_kg"]) < 1e-6),
            "note": "E2E-00 and E2E-01 reproduce the archived baseline (34109.48257123768 kg) and "
                    "W10 tip_twist +2 deg (34117.55529648991 kg) values exactly; the 12D design set "
                    "expands to the same 15D baseline vector, so the archived numbers are not "
                    "overwritten and no new fuel labels are invented.",
        },
        "cases": cases,
        "tail_sensitivity_summary": {
            "V01_plus_1pct_fuel_delta_kg": cases["LFV-04"]["delta_vs_E2E_00_kg"],
            "V01_plus_1pct_fuel_delta_pct": cases["LFV-04"]["delta_vs_E2E_00_pct"],
            "V02_plus_2deg_fuel_delta_kg": cases["LFV-05"]["delta_vs_E2E_00_kg"],
            "V02_plus_2deg_fuel_delta_pct": cases["LFV-05"]["delta_vs_E2E_00_pct"],
            "verdict": "both vertical-tail variables are physically active in the LF chain (nonzero, "
                       "reproducible deltas) but the effect is small; zero-sideslip flight keeps the "
                       "tail lift near zero, so the deltas come from parasite drag / wetted area and "
                       "sweep changes. This satisfies the G1 requirement that V01/V02 not be inert.",
        },
        "external_body_correction": {
            "injected": False,
            "reason": "the area-rule / wave-drag candidate increment is NOT_VALIDATED (see "
                      "wave_drag_area_rule.json: analytic benchmark passes, but the real-geometry "
                      "slice convergence fails and the absolute magnitude contradicts the RCAIDE "
                      "drag level). Injecting it into the mission would fabricate a validated number.",
            "candidate_value": offline_estimate,
        },
        "budget_accounting": {
            "approval": "Issue #4 / D-12D-002",
            "cap_total": ledger["limits"]["max_numerical_analysis_starts"],
            "events_recorded": len(events),
            "used_by_category": used,
            "remaining": ledger["limits"]["max_numerical_analysis_starts"] - len(events),
            "mesh_generation_events": len(ledger.get("mesh_generation_events", [])),
            "note": "every solver process start in this run is recorded, including the failed "
                    "HFS-01 start and the two SU2 configuration attempts; mesh generation is "
                    "recorded separately per the counting contract.",
        },
        "assessment": {
            "mission_data_gate": "PARTIAL",
            "why": "the integration chain is exercised end to end and reproduces archived results, "
                   "but the mission still uses an unvalidated analytic drag build-up; no validated "
                   "wing-body correction exists, Euler wing pressure drag is a different physical "
                   "quantity, and the fuel-burn value remains an algorithm-level LF number.",
            "validated_aircraft_fuel_label": False,
            "caveats": [
                "single cruise segment only (no climb/descent/takeoff/landing, no reserves)",
                "mass/CG/SM status PROVISIONAL_NOT_FROZEN",
                "RCAIDE VLM use_surrogate=True: Mach 2.02 is interpolated inside 2.0-2.5, but the "
                "underlying drag build-up is empirical, not a validated supersonic solver",
                "LF/HF q differs by 0.83% because of the RCAIDE atmosphere state",
                "no validated fuselage/wing interference, no calibrated body correction",
            ],
        },
    }
    out = RUN / "mission_e2e.json"
    out.write_text(json.dumps(doc, indent=2))
    print("wrote", out, out.stat().st_size, "bytes")
    print(json.dumps({
        "baseline": baseline,
        "deltas": {c: cases[c]["delta_vs_E2E_00_kg"] for c in CASES},
        "q_mission": q_mission,
        "delta_drag_N": delta_drag_n,
        "drag_fraction": drag_fraction,
        "naive_fuel": est_fuel,
        "used": used,
    }, indent=1))


if __name__ == "__main__":
    main()
