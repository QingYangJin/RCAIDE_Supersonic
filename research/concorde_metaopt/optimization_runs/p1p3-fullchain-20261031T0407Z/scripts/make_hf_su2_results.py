"""Assemble hf_su2_results.json + the HF mesh-convergence CSV for D-12D-002.

Reads the SU2 history/surface outputs through the per-case analysis JSONs, the wedge
benchmark analysis and the mesh metadata. No solver is started.
"""
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
REPO = Path("D:/RCAIDE")
RUN = REPO / "research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z"
Q_FROZEN = 20483.94023343017
SREF = 358.25
AOA_DEG = 2.8398297488947493


def load(p):
    return json.loads(Path(p).read_text())


def wing_case(case):
    p = EXT / "hf" / "wing" / (case.lower().replace("-", "") + "_analysis.json")
    if not p.exists():
        return None
    d = load(p)
    c = d["final"]
    stab = d["stability_last_200"]
    return {
        "case_id": case,
        "iterations": d["iterations"],
        "CL": c["CL"], "CD": c["CD"], "CMy": c["CMy"], "CMx": c["CMx"], "CMz": c["CMz"],
        "CEff": c["CEff"],
        "CD_N_on_Sref": c["CD"] * Q_FROZEN * SREF,
        "CL_N_on_Sref": c["CL"] * Q_FROZEN * SREF,
        "force_stability_last_200": stab,
        "force_converged": d["force_converged"],
        "residual": {
            "rms_rho_final": d["final_rms_rho"],
            "rms_rho_min": d["rms_rho_min"],
            "plateau_first_iter": d["rms_plateau_first_iter"],
            "note": "rms[Rho] plateaus near 1e-1 because of the sharp leading-edge singularity; "
                    "the integrated forces are nevertheless stationary to 1e-9 relative over the "
                    "last 200 iterations (see force_stability_last_200)",
        },
        "pressure_integration_cross_check": d["pressure_integration"],
        "verdict": "FORCE_CONVERGED_2_LEVEL_ONLY",
    }


def mesh_info(level):
    p = EXT / "hf" / "wing" / ("wing_" + level + "_mesh.json")
    if not p.exists():
        return None
    d = load(p)
    return {"nodes": d["nodes"], "tets": d["tets"], "wall_triangles": d["wall_triangles"],
            "mesh_domain_volume_m3": d["total_tet_volume"],
            "mesh_body_volume_m3": d["wall_volume_abs_by_divergence"],
            "wall_surface_area": d["wall_surface_area"],
            "negative_tet_volumes": d["negative_tet_volumes"]}


def main():
    wedge = load(EXT / "hf" / "wedge" / "hfs00_analysis.json")
    cases = {c: wing_case(c) for c in ("HFS-02", "HFS-03")}
    meshes = {lv: mesh_info(lv) for lv in ("coarse", "medium", "fine")}

    analytic_volume = 129.4516
    analytic_wetted = 717.57475
    for lv, m in meshes.items():
        if not m:
            continue
        m["volume_error_vs_analytic"] = (m["mesh_body_volume_m3"] - analytic_volume) / analytic_volume
        m["wall_area_error_vs_analytic"] = (m["wall_surface_area"] - analytic_wetted) / analytic_wetted

    mc = None
    if cases["HFS-02"] and cases["HFS-03"]:
        med, fine = cases["HFS-02"], cases["HFS-03"]
        r_vol = (meshes["fine"]["tets"] / meshes["medium"]["tets"]) ** (1.0 / 3.0)
        r_lcw = 0.30 / 0.135  # coarse/fine background size ratio for reference
        deltas = {k: fine[k] - med[k] for k in ("CD", "CL", "CMy")}
        rel = {k: 100.0 * deltas[k] / abs(med[k]) for k in deltas}
        rich = {}
        for k in deltas:
            # Richardson extrapolation with assumed orders 1 and 2, refinement ratio by cell count
            est1 = fine[k] + deltas[k] / (r_vol - 1.0)
            est2 = fine[k] + deltas[k] / (r_vol ** 2 - 1.0)
            rich[k] = {"assumed_order_1_estimate": est1,
                       "assumed_order_2_estimate": est2,
                       "spread_between_orders": abs(est1 - est2),
                       "note": "only two grids exist, so the observed order cannot be measured; "
                               "the two assumed orders bracket the estimate, they do not prove it"}
        mc = {
            "medium": {"CD": med["CD"], "CL": med["CL"], "CMy": med["CMy"]},
            "fine": {"CD": fine["CD"], "CL": fine["CL"], "CMy": fine["CMy"]},
            "absolute_delta": deltas,
            "relative_delta_pct": rel,
            "cell_count_refinement_ratio": r_vol,
            "richardson_estimates": rich,
            "note": "HFS-01 (coarse level) failed at the mesh-format stage and consumed its budget "
                    "slot, so only two levels exist; a three-level verification is NOT available and "
                    "no order of accuracy can be claimed",
        }

    ledger = load(RUN / "approval_and_budget_ledger.json")
    su2_events = [e for e in ledger["numerical_analysis_events"] if e.get("category") == "SU2_HF"]
    wall_by_case = {e.get("case_id"): e.get("wall_seconds") for e in su2_events}

    doc = {
        "schema_version": 1,
        "component": "HF_SU2",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "approval": "Issue #4 / D-12D-002 (comment 6538481816)",
        "run_id": RUN.name,
        "solver": {
            "name": "SU2",
            "version": "v8.5.0 Harrier (win64-mpi build)",
            "binary": "D:/Program Files/SU2/SU2-v8.5.0-win64-mpi/win64-mpi/bin/SU2_CFD.exe",
            "launcher": "MS-MPI mpiexec -n 4",
            "mesh_generator": "Gmsh 4.15.2 (gmsh.exe)",
            "physics": "EULER (inviscid), ROE scheme, MUSCL + VENKATAKRISHNAN limiter, CFL 10",
            "note": "Euler contains no viscosity; the whole computation is an inviscid pressure-only "
                    "solve and can never be described as an aircraft fuel-burn fidelity claim",
        },
        "frozen_conditions": {
            "mach": 2.02, "altitude_m": 18288.0,
            "static_pressure_pa": 7171.544888256813, "static_temperature_k": 216.65,
            "density_kg_m3": 0.1153178340089936, "speed_of_sound_m_s": 295.0680184,
            "velocity_m_s": 596.0373972278921, "dynamic_pressure_pa": Q_FROZEN,
            "reynolds_number_cref": 89397005.8767656,
            "reference_area_m2": SREF, "reference_chord_m": 18.489893,
            "reference_span_m": 25.604638,
            "moment_reference_x_m": 16.821978259514246,
            "alpha_deg": AOA_DEG,
            "alpha_note": "AoA was taken from the archived RCAIDE LF baseline alpha_end; it is a "
                          "documented choice, not an independently optimised or trimmed condition",
        },
        "wedge_benchmark": {
            "case_id": "HFS-00",
            "purpose": "SU2 Euler verification against oblique-shock theory before using the wing mesh",
            "geometry": {"mach": 2.0, "half_angle_deg": 10.0, "wedge_length_m": 8.0,
                         "domain": "x in [-10, 40], y in [-20, 20]"},
            "mesh": {"nodes": 7130, "triangles": 13923},
            "theory": wedge["theory"],
            "measured": {
                "wall_pressure_ratio_mean": 1.699422,
                "wall_pressure_ratio_error_percent": 100.0 * (1.699422 / wedge["theory"]["p2_over_p1"] - 1.0),
                "wall_cp_mean": 0.244872,
                "wall_cp_error_percent": 100.0 * (0.244872 / wedge["theory"]["Cp_surface"] - 1.0),
                "postshock_pressure_ratio_mean": wedge["postshock_ppinf"],
                "shock_angle_pressure_mean_deg": wedge["beta_pressure_mean_deg"],
                "shock_angle_pressure_diff_deg": wedge["beta_pressure_diff_deg"],
                "shock_angle_origin_fit_deg": wedge["beta_originfit_deg"],
                "shock_angle_origin_fit_diff_deg": wedge["beta_originfit_diff_deg"],
                "shock_angle_density_mean_deg": wedge["beta_density_mean_deg"],
            },
            "acceptance": {"shock_angle_abs_tolerance_deg": 1.0,
                           "wall_pressure_ratio_note": "pressure ratio within 0.4% on the wall"},
            "verdict": "PARTIAL",
            "why": "the wall pressure ratio matches theory to -0.42%, but the measured shock angle "
                   "is 40.9-41.4 deg in the far field (origin fit 41.9 deg) versus the theoretical "
                   "39.31 deg: the deviation of +1.6 to +2.1 deg exceeds the pre-declared 1 deg "
                   "tolerance. A single coarse mesh cannot separate discretisation error from the "
                   "sharp-tip singularity, so the wedge benchmark is PARTIAL, not PASS.",
            "convergence_note": "rms[Rho] plateaued at -1.905 and mesh refinement (HFS-00R) was not "
                                "run because the SU2 budget slot was consumed by mesh-format failures",
            "wall_seconds": wall_by_case.get("HFS-00"),
        },
        "wing_cases": {
            "HFS-01": {"status": "FAILED",
                       "why": "SU2 rejected the ASCII mesh because the boundary faces were written "
                              "with VTK type 3 (line) instead of 5 (triangle) - a harness defect in "
                              "our own converter, fixed afterwards; the failing process still counts "
                              "as one numerical-analysis start per D-12D-002",
                       "mesh": "coarse (61,436 tets)",
                       "wall_seconds": wall_by_case.get("HFS-01")},
            "HFS-02": dict(cases["HFS-02"] or {}, mesh="medium", wall_seconds=wall_by_case.get("HFS-02")),
            "HFS-03": dict(cases["HFS-03"] or {}, mesh="fine", wall_seconds=wall_by_case.get("HFS-03")),
        },
        "mesh_summary": {
            "geometry": "isolated 12D main wing (span 25.604638 m, Sref 358.25 m2, NACA65-203 sections)",
            "analytic_volume_m3": analytic_volume,
            "analytic_wetted_area_m2": analytic_wetted,
            "levels": meshes,
            "note": "mesh volumes by the divergence theorem converge monotonically to the analytic "
                    "wing volume; the wall area is 0.66-0.72% above the analytic wetted area, which "
                    "is the expected faceting bias of a tetrahedral surface mesh",
        },
        "mesh_convergence": mc,
        "not_run": {
            "HFS-00R": "wedge mesh-refinement verification - SU2 category cap (6) exhausted",
            "HFS-04": "W10 tip_twist +2 deg Euler recompute - SU2 category cap (6) exhausted",
            "why": "D-12D-002 forbids raising a category cap; the failures above consumed slots that "
                   "otherwise would have been available for these runs",
        },
        "budget": {
            "category": "SU2_HF", "cap": 6, "used": 6,
            "events": [e.get("id") for e in su2_events],
            "note": "HFS-SETUP-01 (invalid CONV_CRITERIA key), HFS-SETUP-02 (no MARKER_MONITORING, "
                    "forces zero), HFS-00 wedge, HFS-01 mesh-format failure, HFS-02 medium, HFS-03 fine",
        },
        "verdict": {
            "HF_M2_02": "PARTIAL",
            "what_is_supported": [
                "SU2 8.5.0 Euler runs on this machine with MS-MPI and converges the integrated "
                "forces of an isolated 12D main wing at Mach 2.02",
                "two mesh levels give a measured grid sensitivity of the Euler force coefficients",
                "the wall-pressure integration reproduces the solver's own CD/CL to machine "
                "precision, so the post-processing chain is verified",
                "the wedge benchmark reproduces the wall pressure ratio to 0.4%",
            ],
            "what_is_not_supported": [
                "no three-level grid convergence and no order-of-accuracy estimate",
                "the residual plateau at rms[Rho] ~ 1e-1 means the requested convergence level was "
                "never reached; force stationarity is the only convergence evidence",
                "Euler is inviscid: no friction drag, so no high-fidelity aircraft drag or fuel claim",
                "the wing alone is modelled: no fuselage, vertical tail, nacelles or interference",
                "the wedge shock angle misses the pre-declared 1 deg tolerance by 1.6-2.1 deg",
                "no CL-matched comparison with the LF chain exists (Euler CL 0.0928 vs mission CL 0.1334)",
            ],
            "validated_aircraft_fuel_label": False,
            "may_be_described_as_full_aircraft_high_fidelity": False,
        },
    }
    out = RUN / "hf_su2_results.json"
    out.write_text(json.dumps(doc, indent=2))
    print("wrote", out, out.stat().st_size)

    rows = []
    for level in ("coarse", "medium", "fine"):
        m = meshes.get(level) or {}
        row = {"level": level, "nodes": m.get("nodes"), "tets": m.get("tets"),
               "wall_triangles": m.get("wall_triangles"),
               "mesh_body_volume_m3": m.get("mesh_body_volume_m3"),
               "volume_error_vs_analytic": m.get("volume_error_vs_analytic"),
               "wall_area_m2": m.get("wall_surface_area"),
               "wall_area_error_vs_analytic": m.get("wall_area_error_vs_analytic"),
               "case": {"coarse": "HFS-01", "medium": "HFS-02", "fine": "HFS-03"}[level],
               "CL": None, "CD": None, "CMy": None}
        if level == "medium" and cases["HFS-02"]:
            row.update(CL=cases["HFS-02"]["CL"], CD=cases["HFS-02"]["CD"], CMy=cases["HFS-02"]["CMy"])
        elif level == "fine" and cases["HFS-03"]:
            row.update(CL=cases["HFS-03"]["CL"], CD=cases["HFS-03"]["CD"], CMy=cases["HFS-03"]["CMy"])
        rows.append(row)
    cols = ["level", "case", "nodes", "tets", "wall_triangles", "mesh_body_volume_m3",
            "volume_error_vs_analytic", "wall_area_m2", "wall_area_error_vs_analytic",
            "CL", "CD", "CMy"]
    csv_path = RUN / "mesh_convergence.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("wrote", csv_path, csv_path.stat().st_size)
    print(json.dumps({
        "su2_CD": {k: (v["CD"] if v else None) for k, v in cases.items()},
        "mesh_convergence_rel_pct": mc["relative_delta_pct"] if mc else None,
        "verdict": doc["verdict"]["HF_M2_02"],
    }, indent=1))


if __name__ == "__main__":
    main()
