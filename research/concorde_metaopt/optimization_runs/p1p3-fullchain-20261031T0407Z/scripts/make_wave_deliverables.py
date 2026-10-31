
"""Build the WAVE_AREA_RULE deliverables for the D-12D-002 full-chain run.

Inputs (all already produced by earlier steps, no new solver start):
  EXT/wave/area_rule_recompute.json     offline Eminton-Lord re-analysis of archived slice data
  EXT/wave/area_rule_diagnostics.json   EL conditioning / slice-noise diagnostics
  EXT/wave/WAVE-0*/...                  raw OpenVSP WaveDrag outputs

Outputs:
  RUN/wave_drag_area_rule.json
  RUN/wave_per_theta_donq.csv
  RUN/figures/wave_area_rule_validation.png
  RUN/figures/wave_area_rule_results.png
  D:/RCAIDE/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/wave_raw/  (raw copies, ignored)
  .../wave_raw/wave_raw_manifest.json
"""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
WAVE = EXT / "wave"
RUN = Path(r"D:/RCAIDE/research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z")
RAW_OUT = Path(r"D:/RCAIDE/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/wave_raw")

Q_INF = 20483.94023343017
SREF = 358.25
CREF = 18.489893
BREF = 25.604638
RCAIDE_CD_END = 0.01684412229490337
RCAIDE_CL_END = 0.13343292326555833


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_raw(path):
    """Return list of per-theta dicts with theta_deg, start, end, areas(list of (x_norm, area))."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    cases = []
    cur = None
    for ln in lines:
        s = ln.strip()
        if s.startswith("Theta:"):
            if cur is not None:
                cases.append(cur)
            head = s.split("Theta:")[1]
            parts = [p.strip() for p in head.split(",")]
            theta = float(parts[0])
            start = float(parts[1].split(":")[1])
            end = float(parts[2].split(":")[1])
            cur = {"theta_deg": theta, "start": start, "end": end, "areas": []}
        elif s.startswith("CDWave:") or s.startswith("Mach:") or s.startswith("Set Name:"):
            continue
        elif cur is not None and s and (s[0].isdigit() or s[0] in "+-."):
            parts = s.split(",")
            if len(parts) >= 2:
                cur["areas"].append((float(parts[0]), float(parts[1])))
    if cur is not None:
        cases.append(cur)
    for c in cases:
        x = np.array([a[0] for a in c["areas"]], dtype=float)
        s = np.array([a[1] for a in c["areas"]], dtype=float)
        c["x_norm"] = x
        c["area"] = s
        del c["areas"]
    return cases


def theta_grid(n):
    return [180.0 * i / (n - 1) for i in range(n)]


def fig_validation(recompute, diag, area02, area05, out):
    fig, axes = plt.subplots(1, 3, figsize=(16.2, 4.6))
    # (a) benchmark bars
    ax = axes[0]
    b = recompute["WAVE-00R_benchmark"]
    labels = ["Sears-Haack\ntheory", "Eminton-Lord\nPython port", "OpenVSP 3.26.1\nWaveDrag"]
    vals = [b["donq_theory_sears_haack_m2"], b["donq_python_port_m2"], b["donq_openvsp_m2"]]
    colors = ["#4c72b0", "#55a868", "#c44e52"]
    bars = ax.bar(labels, vals, color=colors, width=0.6)
    ax.set_ylim(0.099, 0.1035)
    for bar, v in zip(bars, vals):
        ax.annotate(f"{v:.6f}", (bar.get_x() + bar.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 3), ha="center", fontsize=9)
    ax.set_ylabel("Donq = D/q  [m$^2$]")
    ax.set_title("(a) analytic benchmark: L=10 m, V=5 m$^3$", fontsize=10)
    ax.text(0.5, 0.08,
            f"port vs theory: {b['rel_error_port_vs_theory']:.2e}\nOpenVSP vs theory: {b['rel_error_openvsp_vs_theory']:.2e}",
            transform=ax.transAxes, ha="center", fontsize=8.5,
            bbox=dict(boxstyle="round", fc="white", ec="#999999", alpha=0.9))
    ax.grid(alpha=0.25, axis="y")

    # (b) condition number
    ax = axes[1]
    cn = diag["condition_number_vs_n"]
    ns = sorted(int(k) for k in cn)
    cs = [cn[str(n)] for n in ns]
    ax.loglog(ns, cs, "o-", color="#8172b2", lw=1.6, ms=5)
    for n, c in zip(ns, cs):
        ax.annotate(f"{c:.1e}", (n, c), textcoords="offset points", xytext=(0, 6),
                    ha="center", fontsize=8)
    ax.set_xlabel("Eminton-Lord collocation points (slices)")
    ax.set_ylabel("condition number of pqq matrix")
    ax.set_title("(b) EL system conditioning vs slice count", fontsize=10)
    ax.grid(alpha=0.25, which="both")
    ax.text(0.03, 0.05, "grows ~n$^{3.1}$; slope > 1 means\nslice-level noise is amplified",
            transform=ax.transAxes, fontsize=8.2)

    # (c) theta=0 area distribution coarse vs fine
    ax = axes[2]
    ax.plot(area02["x_norm"], area02["area"], "-", color="#4c72b0", lw=1.2, label="coarse 36/200")
    step = max(1, len(area05["x_norm"]) // 600)
    ax.plot(area05["x_norm"][::step], area05["area"][::step], "-", color="#c44e52", lw=0.8,
            label="fine 72/800 (every %dth point)" % step)
    ax.set_xlabel("normalized Mach-cut station x")
    ax.set_ylabel("slice area S(x)  [m$^2$]")
    ax.set_title("(c) baseline wing+body area distribution, theta=0", fontsize=10)
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.25)
    ax.text(0.03, 0.06, f"rms 2nd difference: coarse {diag['WAVE-02_theta0']['rms_second_difference']:.4f}, "
                        f"fine {diag['WAVE-05_theta0']['rms_second_difference']:.4f}",
            transform=ax.transAxes, fontsize=8.2)
    fig.suptitle("D-12D-002 WAVE_AREA_RULE: tool benchmark passes, but mesh-sliced area data is non-smooth and the EL system is ill-conditioned",
                 fontsize=10.5, y=1.02)
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)


def fig_results(recompute, out):
    per = recompute["per_theta_donq"]
    fig, axes = plt.subplots(1, 2, figsize=(15.2, 4.9))
    ax = axes[0]
    styles = {
        "WAVE-01": ("#4c72b0", "-", "WAVE-01 wing alone"),
        "WAVE-02": ("#c44e52", "-", "WAVE-02 wing+body"),
        "WAVE-03": ("#4c72b0", "--", "WAVE-03 W03+1deg wing alone"),
        "WAVE-04": ("#c44e52", "--", "WAVE-04 W03+1deg wing+body"),
    }
    for cid, (color, ls, label) in styles.items():
        pts = per[cid]
        th = [pt["theta_deg"] for pt in pts]
        vals = [pt["donq_m2"] for pt in pts]
        ax.plot(th, vals, ls, color=color, lw=1.4, label=label)
    ax.set_xlabel("Mach-plane azimuth theta [deg]")
    ax.set_ylabel("per-theta Donq [m$^2$]")
    ax.set_title("(a) coarse runs (36 rot sections, 200 slices)", fontsize=10)
    ax.legend(fontsize=7.6, ncol=2)
    ax.grid(alpha=0.25)
    ax.set_xlim(0, 180)

    ax = axes[1]
    cases = ["WAVE-01", "WAVE-02", "WAVE-03", "WAVE-04"]
    vals = [recompute[c]["donq_avg_m2"] for c in cases]
    labels = ["W1\nwing", "W2\nw+b", "W3\nW03 wing", "W4\nW03 w+b"]
    bars = ax.bar(labels, vals, color=["#4c72b0", "#c44e52", "#4c72b0", "#c44e52"], width=0.6)
    for bar, v in zip(bars, vals):
        ax.annotate(f"{v:.2f}", (bar.get_x() + bar.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 3), ha="center", fontsize=9)
    ax.axhline(recompute["WAVE-05"]["donq_avg_m2"], color="#8172b2", ls=":", lw=1.6)
    ax.annotate(f"WAVE-05 refined wing+body = {recompute['WAVE-05']['donq_avg_m2']:.2f} m$^2$\n"
                f"({recompute['resolution_sensitivity']['ratio_fine_over_coarse']:.2f}x coarse) -- NOT CONVERGED",
                xy=(0.5, recompute["WAVE-05"]["donq_avg_m2"]), xycoords=("axes fraction", "data"),
                xytext=(0.5, 0.96), textcoords="axes fraction", ha="center", va="top", fontsize=8.5,
                color="#8172b2")
    ax.set_ylabel("theta-averaged Donq = D/q [m$^2$]")
    ax.set_title("(b) averaged area-rule drag area per case", fontsize=10)
    ax.grid(alpha=0.25, axis="y")
    ax.text(0.02, 0.04,
            "absolute scale is NOT physical: wing+body CD=$0.043$ (coarse) / $0.124$ (fine)\n"
            "vs archived RCAIDE single-cruise total CD=0.01684; verdict NOT_VALIDATED",
            transform=ax.transAxes, fontsize=7.8,
            bbox=dict(boxstyle="round", fc="#fff3cd", ec="#c9a227", alpha=0.95))
    fig.suptitle("D-12D-002 WAVE_AREA_RULE: per-theta scatter is large and refinement increases drag area (numerical artefact, not converged physics)",
                 fontsize=10.5, y=1.02)
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    recompute = json.loads((WAVE / "area_rule_recompute.json").read_text(encoding="utf-8"))
    diag = json.loads((WAVE / "area_rule_diagnostics.json").read_text(encoding="utf-8"))
    reset = recompute["resolution_sensitivity"]

    # raw copies + hashes
    RAW_OUT.mkdir(parents=True, exist_ok=True)
    raw_manifest = {"created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "note": "raw OpenVSP WaveDrag outputs archived outside git (outputs/ is git-ignored); "
                            "hashed here for traceability",
                    "files": []}
    for case in ["WAVE-00", "WAVE-00R", "WAVE-01", "WAVE-02", "WAVE-03", "WAVE-04", "WAVE-05"]:
        d = WAVE / case
        if not d.is_dir():
            continue
        target = RAW_OUT / case
        target.mkdir(parents=True, exist_ok=True)
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            shutil.copy2(f, target / f.name)
            raw_manifest["files"].append({"case_id": case, "name": f.name, "bytes": f.stat().st_size,
                                          "sha256": sha256(f),
                                          "archived_path": str(target / f.name)})
    (RAW_OUT / "wave_raw_manifest.json").write_text(json.dumps(raw_manifest, indent=2), encoding="utf-8")
    raw_manifest["manifest_sha256"] = sha256(RAW_OUT / "wave_raw_manifest.json")

    # request json hashes (geometry inputs)
    req_files = []
    for name in ["baseline", "baseline_wingbody", "w03_plus1deg", "w03_plus1deg_wingbody", "WAVE-00"]:
        p = WAVE / name / "request.json"
        if p.is_file():
            req_files.append({"component": name, "bytes": p.stat().st_size, "sha256": sha256(p)})

    # per-theta CSV
    rows = ["case_id,theta_deg,donq_m2"]
    for cid in ["WAVE-01", "WAVE-02", "WAVE-03", "WAVE-04", "WAVE-05"]:
        for pt in recompute["per_theta_donq"][cid]:
            rows.append(f"{cid},{pt['theta_deg']:.4f},{pt['donq_m2']:.10g}")
    (RUN / "wave_per_theta_donq.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    # figures
    figdir = RUN / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    area02 = parse_raw(WAVE / "WAVE-02" / "Unnamed_WaveDrag_M2.020000_Shown.txt")[0]
    area05 = parse_raw(WAVE / "WAVE-05" / "Unnamed_WaveDrag_M2.020000_Shown.txt")[0]
    fig_validation(recompute, diag, area02, area05, figdir / "wave_area_rule_validation.png")
    fig_results(recompute, figdir / "wave_area_rule_results.png")

    # main JSON
    cd_coarse = recompute["WAVE-02"]["donq_avg_m2"] / SREF
    cd_fine = recompute["WAVE-05"]["donq_avg_m2"] / SREF
    cd_wing_alone = recompute["WAVE-01"]["donq_avg_m2"] / SREF
    inc = recompute["increments"]["fuselage_zero_lift_volume_wave_drag_increment"]
    w03 = recompute["increments"]["w03_plus_1deg_effect"]

    doc = {
        "schema_version": 1,
        "run_id": RUN.name,
        "component": "WAVE_AREA_RULE",
        "approval_source": "Issue #4 / D-12D-002 (comment 6538481816)",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "Supsersonic (Mach-cut) area-rule volume wave-drag estimate for the fixed fuselage, "
                 "decision B of D-12D-002; isolated main wing and wing+fixed-fuselage combinations only.",
        "frozen_conditions": {
            "mach": 2.02,
            "altitude_m": 18288.0,
            "q_inf_pa": Q_INF,
            "reference_area_m2": SREF,
            "reference_chord_m": CREF,
            "reference_span_m": BREF,
            "note": "OpenVSP WaveDrag is a pure geometry method; Mach only selects the Mach-cut angle. "
                    "No flow solver was run for this component.",
        },
        "tool": {
            "name": "OpenVSP",
            "version": "3.26.1",
            "binary": "D:/Program Files/OpenVSP/OpenVSP-3.26.1-win64-Python3.9/OpenVSP-3.26.1-win64/vsp.exe + OpenVSP Python API (external Python 3.9 worker)",
            "analysis": "WaveDrag (WaveDragMgr, Eminton-Lord); EmintonLord analysis also used for the analytic benchmark",
            "python_worker": "D:/Anaconda/envs/SUAVE/python.exe (3.9.25)",
        },
        "method": {
            "what": "Mach-plane area rule: for each azimuth theta in [0,180] deg the model is cut by planes inclined at the "
                    "Mach angle; the resulting area distribution S(x;theta) is fed to the Eminton-Lord (1956) supersonic "
                    "wave-drag integral to obtain Donq(theta)=D/q; CDWave = mean_theta(Donq)/Sref.",
            "implementation_source_evidence": {
                "file": "src/geom_core/WaveDragMgr.cpp (OpenVSP, downloaded for audit)",
                "sref_default": "WaveDragMgr.cpp:42 m_Sref.Init(\"Sref\",\"WaveDrag\",this,100,0.001,1.0e12) -- default reference area 100 m^2",
                "cd_formula": "WaveDragMgr.cpp:571 m_CDWave = D / m_Sref();",
                "averaging": "WaveDragMgr.cpp:510-575 CalcDrag(): D += WaveDrag(i)*dtheta*k with k=0.5 at theta=0 and theta=pi",
                "kernel": "src/external/wavedragEL/wavedragEL.c emlord() -- Eminton-Lord collocation solution",
                "reference_geometry_override": "WaveDragMgr.cpp:170-184 sets m_Sref to the referenced wing area only when a reference geometry is supplied; not used here",
            },
            "reference_area_convention_verified": {
                "implied_sref_from_recompute_m2": {cid: recompute[cid]["implied_sref_m2"] for cid in
                                                  ["WAVE-01", "WAVE-02", "WAVE-03", "WAVE-04", "WAVE-05"]},
                "conclusion": "CDWave output is normalised by the default 100 m^2, not by the wing Sref 358.25 m^2; "
                              "all CD values in this file are therefore expressed as CDWave*100/Sref when compared with "
                              "RCAIDE drag coefficients.",
            },
            "offline_reanalysis": "A Python port of emlord() re-computed every case from the archived slice-area text "
                                  "outputs and reproduced the OpenVSP CDWave to <= 1.8e-6 relative. This re-analysis "
                                  "started no solver process and is not counted against the 23-start budget.",
        },
        "analytic_benchmark": {
            "case_id": "WAVE-00R",
            "body": "Sears-Haack body, L=10 m, V=5 m^3, S(x)=(16V/(3*pi*L))*[4t(1-t)]^(3/2), 81 stations, EmintonLord analysis",
            "theory_donq_m2": recompute["WAVE-00R_benchmark"]["donq_theory_sears_haack_m2"],
            "python_port_donq_m2": recompute["WAVE-00R_benchmark"]["donq_python_port_m2"],
            "openvsp_donq_m2": recompute["WAVE-00R_benchmark"]["donq_openvsp_m2"],
            "rel_error_port_vs_theory": recompute["WAVE-00R_benchmark"]["rel_error_port_vs_theory"],
            "rel_error_openvsp_vs_theory": recompute["WAVE-00R_benchmark"]["rel_error_openvsp_vs_theory"],
            "verdict": "PASS -- the tool and the independent port agree with the closed-form Sears-Haack result to ~1.6e-6; "
                       "the wave-drag implementation itself is trustworthy for smooth analytic area distributions.",
        },
        "cases": {
            "WAVE-01": {"description": "12D baseline main wing alone", "discretization": "36 rot sections x 200 slices",
                        "donq_avg_m2": recompute["WAVE-01"]["donq_avg_m2"], "cdwave_output": recompute["WAVE-01"]["cdwave_csv"],
                        "cd_on_Sref_358_25": recompute["WAVE-01"]["donq_avg_m2"] / SREF,
                        "donq_min_m2": recompute["WAVE-01"]["donq_min_m2"], "donq_max_m2": recompute["WAVE-01"]["donq_max_m2"]},
            "WAVE-02": {"description": "12D baseline main wing + fixed fuselage (8-station model)", "discretization": "36 x 200",
                        "donq_avg_m2": recompute["WAVE-02"]["donq_avg_m2"], "cdwave_output": recompute["WAVE-02"]["cdwave_csv"],
                        "cd_on_Sref_358_25": cd_coarse,
                        "donq_min_m2": recompute["WAVE-02"]["donq_min_m2"], "donq_max_m2": recompute["WAVE-02"]["donq_max_m2"]},
            "WAVE-03": {"description": "W03=68.0 deg (+1 deg) main wing alone", "discretization": "36 x 200",
                        "donq_avg_m2": recompute["WAVE-03"]["donq_avg_m2"], "cdwave_output": recompute["WAVE-03"]["cdwave_csv"],
                        "cd_on_Sref_358_25": recompute["WAVE-03"]["donq_avg_m2"] / SREF,
                        "donq_min_m2": recompute["WAVE-03"]["donq_min_m2"], "donq_max_m2": recompute["WAVE-03"]["donq_max_m2"]},
            "WAVE-04": {"description": "W03=68.0 deg (+1 deg) main wing + fixed fuselage", "discretization": "36 x 200",
                        "donq_avg_m2": recompute["WAVE-04"]["donq_avg_m2"], "cdwave_output": recompute["WAVE-04"]["cdwave_csv"],
                        "cd_on_Sref_358_25": recompute["WAVE-04"]["donq_avg_m2"] / SREF,
                        "donq_min_m2": recompute["WAVE-04"]["donq_min_m2"], "donq_max_m2": recompute["WAVE-04"]["donq_max_m2"]},
            "WAVE-05": {"description": "baseline main wing + fixed fuselage, refinement (numRotSects 36->72, numSlices 200->800)",
                        "discretization": "72 x 800",
                        "donq_avg_m2": recompute["WAVE-05"]["donq_avg_m2"], "cdwave_output": recompute["WAVE-05"]["cdwave_csv"],
                        "cd_on_Sref_358_25": cd_fine,
                        "donq_min_m2": recompute["WAVE-05"]["donq_min_m2"], "donq_max_m2": recompute["WAVE-05"]["donq_max_m2"]},
        },
        "resolution_sensitivity": reset,
        "fuselage_zero_lift_volume_wave_drag_increment": {
            "definition": "Delta D/q = area-rule(wing + fixed fuselage) - area-rule(wing alone), paired per theta, coarse 36x200 only",
            "baseline_pair": inc["baseline_pair"],
            "w03_plus_1deg_pair": inc["w03_pair"],
            "candidate_for_body_correction": False,
            "why_not_usable": "Only the non-converged coarse discretization exists for a paired difference; the refined run "
                              "(WAVE-05) has no paired wing-alone counterpart, and the coarse absolute level already exceeds the "
                              "independently archived RCAIDE total drag (see absolute_magnitude_cross_check). "
                              "The increment is therefore reported as an order-of-magnitude diagnostic only.",
        },
        "w03_plus_1deg_effect": w03,
        "absolute_magnitude_cross_check": {
            "archived_rcaide_reference": {
                "source": "research/concorde_metaopt/optimization_runs/smoke-p2-20261029T1612/evaluations.jsonl (baseline d-78be330a6036)",
                "cl_end": RCAIDE_CL_END,
                "cd_end": RCAIDE_CD_END,
                "l_over_d": RCAIDE_CL_END / RCAIDE_CD_END,
                "note": "independent RCAIDE single-cruise Mission result; L/D=7.9 is physically plausible for a Concorde-class cruise",
            },
            "area_rule_wing_alone_cd": cd_wing_alone,
            "area_rule_wing_body_cd_coarse": cd_coarse,
            "area_rule_wing_body_cd_fine": cd_fine,
            "ratio_wing_body_coarse_over_rcaide_total": cd_coarse / RCAIDE_CD_END,
            "ratio_wing_body_fine_over_rcaide_total": cd_fine / RCAIDE_CD_END,
            "ratio_increment_over_rcaide_total": inc["baseline_pair"]["delta_CD_on_Sref"] / RCAIDE_CD_END,
            "conclusion": "The area-rule absolute zero-lift volume wave drag (CD 0.043 coarse, 0.124 refined) is 2.6x-7.4x the "
                          "archived RCAIDE TOTAL drag (CD 0.01684) of the whole aircraft at the same Mach and lift. A physical "
                          "volume wave drag cannot exceed the total drag of the configuration, so the mesh-sliced area-rule "
                          "absolute scale is not physical for this wing+body geometry. The paired fuselage increment "
                          "(CD +0.0082) is ~48% of the RCAIDE total drag and is likewise not usable as a calibrated correction.",
        },
        "diagnostics": {
            "condition_number_vs_n": diag["condition_number_vs_n"],
            "slice_noise": {"WAVE-02_theta56_57": diag["WAVE-02_theta56_57"], "WAVE-05_theta73_52": diag["WAVE-05_theta73_52"],
                            "WAVE-02_theta0": diag["WAVE-02_theta0"], "WAVE-05_theta0": diag["WAVE-05_theta0"]},
            "outlier_theta": diag,
            "interpretation": "The Eminton-Lord collocation matrix condition number grows ~n^3.1 (1.9e6 at n=200, 1.2e8 at n=800). "
                              "The mesh-derived Mach-cut area distributions are not smooth (rms second difference 0.006-0.20 m^2, "
                              "single-slice jumps up to 2.8 m^2), so refining the slice count injects more high-frequency "
                              "discretization noise that the ill-conditioned solve amplifies: the area-rule D/q rises from "
                              "15.50 to 44.44 m^2 (2.87x) instead of converging. The large per-theta outliers (742 m^2 at theta=73.5 deg) "
                              "are numerical artefacts of oblique cuts through a triangulated surface, not physical wave drag.",
        },
        "verdict": "NOT_VALIDATED",
        "verdict_detail": "The area-rule implementation passes the analytic Sears-Haack benchmark (PASS), but the application to the "
                          "triangulated wing+fixed-fuselage geometry does not converge under slice/rotation refinement and its "
                          "absolute level contradicts the independent RCAIDE drag level. Therefore no wave-drag increment from "
                          "this component may be added to the drag ledger or used to calibrate the fixed-fuselage body correction.",
        "body_correction_gate": {
            "gate": "BODY-CORR",
            "status": "BLOCKED / NOT_VALIDATED",
            "evidence_from_this_component": "zero-lift volume wave-drag increment of the fixed body cannot be quantified to the "
                                            "required accuracy by the available area-rule path; the body-correction gate remains "
                                            "blocked and no validated whole-aircraft fuel label may be produced.",
        },
        "budget": {
            "category": "WAVE_AREA_RULE",
            "cap": 7,
            "used": 7,
            "events": ["NA-007 WAVE-00 (EmintonLord baseline; result lost to LD-002, counted)",
                       "NA-008 WAVE-00R (benchmark rerun)", "NA-009 WAVE-01", "NA-010 WAVE-02",
                       "NA-011 WAVE-03", "NA-012 WAVE-04", "NA-013 WAVE-05"],
            "offline_reanalysis_starts": 0,
            "total_run_starts_after_this_component": 13,
        },
        "artifacts": {
            "raw_manifest": raw_manifest,
            "geometry_requests": req_files,
            "derived_csv": "wave_per_theta_donq.csv",
            "figures": ["figures/wave_area_rule_validation.png", "figures/wave_area_rule_results.png"],
        },
        "caveats": [
            "OpenVSP WaveDrag uses the OpenVSP default reference area of 100 m^2; CDWave is converted to the wing Sref 358.25 m^2 for comparison only.",
            "The fuselage is the fixed 8-station 12D model (length 61.66 m), not a CFD-quality fuselage surface; its blunt 0.001 m end caps are numerical bookkeeping.",
            "The Mach-cut area rule in this implementation does not model viscous drag, lift-dependent wave drag, or vortex drag; it is a zero-lift volume wave-drag estimate only.",
            "The W03+1 deg geometry was generated through the same 12D parametric model as the LF/OpenVSP cases; W10 twist is not part of this area-rule pair.",
            "The 7-start category is exhausted; a converged area-rule study would need additional authorised starts.",
        ],
        "raw_artifacts_location": str(RAW_OUT),
        "raw_artifacts_note": "raw slice files are large; copies live outside git under the ignored outputs/ tree and are hash-indexed above",
    }
    (RUN / "wave_drag_area_rule.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print("wrote", RUN / "wave_drag_area_rule.json", (RUN / "wave_drag_area_rule.json").stat().st_size)
    print("wrote", RUN / "wave_per_theta_donq.csv", (RUN / "wave_per_theta_donq.csv").stat().st_size)
    print("figures:")
    for f in sorted(figdir.glob("*.png")):
        print(" ", f.name, f.stat().st_size)
    print("raw manifest files:", len(raw_manifest["files"]))


if __name__ == "__main__":
    main()
