"""Assemble drag_component_ledger.json for the D-12D-002 full-chain run.

Reads (read-only) the LF mission ledger, the SU2 wing analyses, the VSPAERO density
study and the area-rule deliverable, converts everything to newtons on the frozen
reference area, records the deduplication rules / overlap risks and states what is
still missing. No solver is started; no number is fabricated: anything not measured
stays None.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
REPO = Path("D:/RCAIDE")
RUN = REPO / "research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z"

Q_FROZEN = 20483.94023343017
SREF = 358.25


def load(p):
    return json.loads(Path(p).read_text())


def main():
    e2e = load(RUN / "mission_e2e.json")
    base_case = e2e["cases"]["E2E-00"]
    rc_ledger = base_case["drag_ledger"]
    q_mission = rc_ledger["dynamic_pressure_pa"]
    rc_components_cd = rc_ledger["component_cd"]
    rc_components_n = rc_ledger["component_drag_magnitude_n"]
    rc_total_n = rc_ledger["total_drag_magnitude_n"]

    su2 = {}
    for case in ("HFS-02", "HFS-03"):
        p = EXT / "hf" / "wing" / (case.lower().replace("-", "") + "_analysis.json")
        if p.exists():
            d = load(p)
            c = d["final"]
            su2[case] = {
                "mesh": "medium" if case == "HFS-02" else "fine",
                "CL": c["CL"], "CD": c["CD"], "CMy": c["CMy"],
                "CD_N_on_Sref": c["CD"] * Q_FROZEN * SREF,
                "CL_N_on_Sref": c["CL"] * Q_FROZEN * SREF,
                "iterations": d["iterations"],
                "force_converged": d["force_converged"],
                "residual_plateau_rms_rho": d["final_rms_rho"],
                "pressure_integration_CD": d["pressure_integration"]["CD_integrated"],
                "pressure_integration_CL": d["pressure_integration"]["CL_integrated"],
            }

    vsp = load(RUN / "lf_vspaero_results.json")
    wave = load(RUN / "wave_drag_area_rule.json")
    wave_cases = wave["cases"] if isinstance(wave.get("cases"), dict) else {}
    if isinstance(wave.get("cases"), list):
        wave_cases = {c["case_id"]: c for c in wave["cases"]}

    def wave_cd(case):
        c = wave_cases.get(case) or {}
        for key in ("cd_on_Sref_358_25", "cdwave_output", "donq_avg_m2"):
            v = c.get(key)
            if v is None:
                continue
            return v if key == "cd_on_Sref_358_25" else (v / SREF if key == "donq_avg_m2" else v)
        return None

    wave_wing_alone_cd = wave_cd("WAVE-01")
    wave_wing_body_cd = wave_cd("WAVE-02")
    inc = wave["fuselage_zero_lift_volume_wave_drag_increment"]["baseline_pair"]

    doc = {
        "schema_version": 1,
        "component": "DRAG_COMPONENT_LEDGER",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "approval": "Issue #4 / D-12D-002 (comment 6538481816)",
        "run_id": RUN.name,
        "reference_quantities": {
            "Sref_m2": SREF,
            "cref_m": 18.489893,
            "bref_m": 25.604638,
            "q_inf_frozen_pa": Q_FROZEN,
            "q_mission_observed_pa": q_mission,
            "moment_reference_x_m": 16.821978259514246,
            "note": "all drag values are positive wind-axis magnitudes in newtons; CD = D/(q Sref). "
                    "SU2 values use the frozen q; the RCAIDE mission uses its own atmosphere state "
                    "q = %.3f Pa (+0.83%% vs frozen). Converting between the two without stating the "
                    "q used is not allowed." % q_mission,
        },
        "rcAide_lf_component_ledger": {
            "source": "evaluation/low_fidelity.py -> evaluation/mission.py -> drag_ledger.py, "
                      "E2E-00 single cruise at Mach 2.02 / 18288 m",
            "status": rc_ledger["status"],
            "model_validated": rc_ledger["model_validated"],
            "total_cd": rc_ledger["total_cd"],
            "total_drag_n": rc_total_n,
            "component_cd": rc_components_cd,
            "component_drag_n": rc_components_n,
            "diagnostic_subcomponents_cd_not_additive": rc_ledger["diagnostic_subcomponents_cd_not_additive"],
            "missing_additive_components": rc_ledger["missing_additive_components"],
            "closure": {
                "numerical_closure_passed": rc_ledger["numerical_closure_passed"],
                "numerical_closure_residual_cd": rc_ledger["numerical_closure_residual_cd"],
                "why": "the additive increment term is missing on this RCAIDE build, so the "
                       "ledger reports PARTIAL_DATA_NOT_VALIDATED and cannot claim closure",
            },
        },
        "su2_hf_wing_ledger": {
            "source": "SU2 8.5.0 Euler, isolated 12D main wing, medium/fine tetrahedral meshes, "
                      "Mach 2.02, AoA 2.8398 deg",
            "cases": su2,
            "physics": "inviscid pressure force only: no skin friction, no fuselage, no vertical "
                       "tail, no nacelles, no interference",
            "note": "Euler pressure drag already contains the lift-induced and wave parts of the "
                    "isolated wing; it must not be added to the RCAIDE induced/compressible terms "
                    "as if they were disjoint.",
        },
        "area_rule_ledger": {
            "source": "OpenVSP 3.26.1 WaveDrag (Eminton-Lord) with an independent Python port of "
                      "wavedragEL as cross-check",
            "CDWave_normalization": "D/q in m^2 divided by OpenVSP internal reference area 100 m^2, "
                                    "empirically confirmed to 2e-6",
            "wing_alone_CD": wave_wing_alone_cd,
            "wing_plus_fuselage_CD": wave_wing_body_cd,
            "candidate_fuselage_zero_lift_volume_increment": inc,
            "predicted_increment_n": inc["delta_D_N"],
            "verdict": wave["verdict"],
            "why_not_usable": wave["fuselage_zero_lift_volume_wave_drag_increment"]["why_not_usable"],
        },
        "vspaero_lf_ledger": {
            "source": "VSPAERO 6.2.0 thin-surface, isolated 12D main wing",
            "verdict": (vsp.get("assessment") or {}).get("verdict") or vsp.get("verdict"),
            "note": "the density study (SENS-A/medium/SENS-B) showed the induced drag changing sign "
                    "and growing about 65x with refinement at Mach 2.02, so the VSPAERO drag split "
                    "is not usable as a drag component at all; only the CL trend is reported as a "
                    "sanity check",
            "alpha_2deg_CDtot": {
                "coarse": 0.005420316,
                "medium": 0.004188608,
                "fine": -0.01743937,
            },
        },
        "cross_tool_comparison_not_additive": {
            "warning": "the values below are different physical/model quantities measured at "
                       "different CL; the table exists to expose the size of the gap, not to sum it",
            "rcAide_wing_attributed_inviscid_like_terms_cd": {
                "induced": rc_components_cd["induced"],
                "compressible": rc_components_cd["compressible"],
                "sum": rc_components_cd["induced"] + rc_components_cd["compressible"],
            },
            "su2_wing_euler_cd": {k: v["CD"] for k, v in su2.items()},
            "su2_over_rcAide_inviscid_like_ratio": (
                su2["HFS-02"]["CD"] / (rc_components_cd["induced"] + rc_components_cd["compressible"])
                if "HFS-02" in su2 else None),
            "area_rule_wing_alone_over_su2_ratio": (
                wave_wing_alone_cd / su2["HFS-02"]["CD"]
                if wave_wing_alone_cd is not None and "HFS-02" in su2 else None),
            "observations": [
                "SU2 isolated-wing Euler CD (0.0068 medium) is about half of the RCAIDE "
                "induced+compressible sum (0.0130) at a different CL (0.0928 Euler vs 0.111 "
                "isolated-wing VLM, because the mission CL includes a 1.20 fuselage lift factor).",
                "the absolute area-rule level (wing alone CD = %.4f coarse, not converged) is already "
                "5x the SU2 wing pressure drag and 2x the RCAIDE total aircraft drag, so the "
                "area-rule absolute level cannot be calibrated into the mission." % wave_wing_alone_cd,
                "the paired wing-body area-rule increment (%.5f CD = %.0f N) would be 48%% of the "
                "RCAIDE total drag at this q; injecting it makes the cruise infeasible, which is "
                "itself a warning that the increment is not a usable correction." % (
                    inc["delta_CD_on_Sref"], inc["delta_D_N"]),
            ],
        },
        "deduplication_rules_proposed": {
            "rule_1": "never add a coefficient from two different q/Sref systems; convert to N with "
                      "the q actually used and only then partition",
            "rule_2": "RCAIDE induced (VLM Trefftz, incompressible far field) must not be added to a "
                      "supersonic lift-dependent wave term without an overlap study; the archived "
                      "compression of wave_lift+wave_volume into the compressible component is a "
                      "build-up, not a disjoint decomposition",
            "rule_3": "Euler isolated-wing pressure drag must not be combined with the empirical "
                      "RCAIDE wing drag terms; it is a replacement candidate only after a grid-"
                      "converged CL-matched comparison exists",
            "rule_4": "the area-rule volume-wave increment is zero-lift only and does not include "
                      "lift-dependent wave drag, fuselage friction or all wing-body interference",
            "rule_5": "the increment additive slot in the RCAIDE ledger must stay null until an "
                      "independently calibrated correction exists",
        },
        "missing_terms": [
            "calibrated wing-body interference / body correction (BODY-CORR BLOCKED)",
            "fuselage and vertical-tail pressure drag at supersonic speed (not measured)",
            "viscous drag at Reynolds number 8.94e7 (no RANS, Euler is inviscid)",
            "nacelle/pylon/boom drag and propulsion-airframe interference",
            "validated lift-dependent wave drag (RCAIDE empirical JAXA correlation unvalidated)",
            "trim drag in a trimmed mission (the cruise segment uses a fixed alpha control)",
            "decomposed parasite drag per component (the RCAIDE ledger reports only the aggregate)",
            "CL-matched comparison between LF and HF (the two chains ran at different CL)",
        ],
        "verdict": {
            "drag_ledger": "NOT_VALIDATED",
            "body_correction_gate": "BODY-CORR BLOCKED",
            "why": "no measured quantity in this run can be promoted to a validated aircraft drag "
                   "correction: LF VSPAERO drag is non-physical, HF Euler covers only the isolated "
                   "wing and is not grid-converged, and the area-rule increment is non-converged and "
                   "contradicts the independent RCAIDE drag level. All values are reported as "
                   "diagnostics with their uncertainties.",
            "no_number_may_be_read_as_a_validated_correction": True,
        },
    }
    out = RUN / "drag_component_ledger.json"
    out.write_text(json.dumps(doc, indent=2))
    print("wrote", out, out.stat().st_size)
    print(json.dumps({"su2_cases": list(su2), "verdict": doc["verdict"],
                      "su2_CD": {k: v["CD"] for k, v in su2.items()}}, indent=1))


if __name__ == "__main__":
    main()
