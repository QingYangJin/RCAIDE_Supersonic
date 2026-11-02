
"""Offline re-analysis of OpenVSP WaveDrag outputs (no solver starts).

Ports emlord() from OpenVSP src/external/wavedragEL/wavedragEL.c and reproduces
CDWave = mean_theta(Donq)/Sref with the WaveDrag analysis default Sref = 100 m^2
(OpenVSP src/geom_core/WaveDragMgr.cpp: m_Sref.Init(...,100,...); m_CDWave = D/m_Sref()).
This is a re-analysis of archived solver output, not a new numerical analysis start.
"""
import json, math, re, csv
from pathlib import Path

import numpy as np

WAVE = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/wave")
OUT = WAVE / "area_rule_recompute.json"


def emlord(naxs, sarea):
    prts = len(naxs)
    x = [0.0] * prts
    k = 0
    for i in range(prts):
        x[k] = naxs[i]
        if k == prts - 3:
            break
        k += 1
        if i == 0 or i == prts - 1:
            k -= 1
    c = [0.0] * prts
    qq = [0.0] * prts
    m = prts - 2
    pqq = [[0.0] * prts for _ in range(prts)]
    for i in range(m):
        nx = (x[i] - naxs[0]) / (naxs[-1] - naxs[0])
        qq[i] = (math.acos(1.0 - 2.0 * nx) - (2.0 - 4.0 * nx) * math.sqrt(nx - nx * nx)) / math.pi
        for j in range(i, prts):
            ny = (x[j] - naxs[0]) / (naxs[-1] - naxs[0])
            e = (nx - ny) ** 2
            e1 = nx + ny - 2.0 * nx * ny
            e2 = 2.0 * math.sqrt(max(nx * ny * (1.0 - nx) * (1.0 - ny), 0.0))
            if i == j:
                pqq[j][i] = e1 * e2
            elif e1 + e2 <= 0 or e1 - e2 <= 0:
                pqq[j][i] = float("nan")
            else:
                pqq[j][i] = 0.5 * e * math.log((e1 - e2) / (e1 + e2)) + e1 * e2
        if i > 0:
            for kk in range(i):
                pqq[kk][i] = pqq[i][kk]
    k = 0
    for i in range(prts):
        c[k] = sarea[i] - sarea[0] - (sarea[-1] - sarea[0]) * qq[k]
        if k == prts - 3:
            break
        k += 1
        if i == 0 or i == prts - 1:
            k -= 1
    a = np.array([row[:m] for row in pqq[:m]], dtype=float)
    rhs = np.array(c[:m], dtype=float)
    if not np.all(np.isfinite(a)):
        raise ValueError("non-finite Eminton-Lord matrix")
    sol = np.linalg.solve(a, rhs)
    totlength = naxs[-1] - naxs[0]
    drag = (4.0 * (sarea[0] - sarea[-1]) ** 2 / math.pi + math.pi * float(np.dot(sol, rhs))) / totlength ** 2
    return drag


def parse_txt(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    thetas, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("Inlet Area:", "Exit Area:", "...Wave", "CDWave:", "Mach:", "Set Name:")):
            if line.startswith(("CDWave:", "Mach:", "Set Name:")):
                cur = None
            continue
        m = re.match(r"Theta:\s*([-\d.]+),\s*Start:\s*([-\d.]+),\s*End:\s*([-\d.]+)", line)
        if m:
            cur = {"theta_deg": float(m.group(1)), "start": float(m.group(2)),
                   "end": float(m.group(3)), "x_norm": [], "area": []}
            thetas.append(cur)
            continue
        if cur is not None and "," in line:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                try:
                    cur["x_norm"].append(float(parts[0]))
                    cur["area"].append(float(parts[1]))
                except ValueError:
                    pass
    return thetas


def read_csv_results(case):
    p = next((WAVE / case).glob("results_*.csv"))
    rows = {}
    with p.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = [x.strip() for x in line.rstrip("\n").split(",")]
            if len(parts) >= 2:
                rows.setdefault(parts[0], []).extend(parts[1:])
    return rows


def cdwave_of(case):
    rows = read_csv_results(case)
    return float(rows["CDWave"][0])


def lengths_of(case):
    return [float(v) for v in read_csv_results(case).get("Length", [])]


results = {"arithmetic_note": "Offline re-analysis of archived OpenVSP WaveDrag slice-area output; 0 new solver starts, not billed against the D-12D-002 budget."}

req = json.loads((WAVE / "WAVE-00R" / "request.json").read_text())
inp = req["analysis"]["inputs"]
d0 = emlord(list(inp["X_vec"]), list(inp["Area_vec"]))
theory = 128.0 * 5.0 ** 2 / (math.pi * 10.0 ** 4)
results["WAVE-00R_benchmark"] = {
    "n_points": len(inp["X_vec"]),
    "donq_python_port_m2": d0,
    "donq_openvsp_m2": 0.101859,
    "donq_theory_sears_haack_m2": theory,
    "rel_error_port_vs_theory": (d0 - theory) / theory,
    "rel_error_openvsp_vs_theory": (0.101859 - theory) / theory,
    "meaning": "Eminton-Lord Donq has area units (D/q); CDWave = sum_theta(Donq * dtheta * k) / Sref.",
}

case_meta = {
    "WAVE-01": "baseline wing alone",
    "WAVE-02": "baseline wing + fixed fuselage",
    "WAVE-03": "W03=68.0 deg (+1 deg) wing alone",
    "WAVE-04": "W03=68.0 deg wing + fixed fuselage",
    "WAVE-05": "baseline wing + fixed fuselage, refined 72 rot / 800 slices",
}
per_theta = {}
for case, desc in case_meta.items():
    thetas = parse_txt(next((WAVE / case).glob("Unnamed_WaveDrag_M*.txt")))
    lengths = lengths_of(case)
    ntheta = len(thetas)
    if lengths:
        assert len(lengths) == ntheta, (case, len(lengths), ntheta)
    dtheta = 1.0 / (ntheta - 1)
    rows = []
    for i, t in enumerate(thetas):
        xn = t["x_norm"]
        area = t["area"]
        L = lengths[i] if lengths else (t["end"] - t["start"])
        x = [t["start"] + v * L for v in xn]
        donq = emlord(x, area)
        w = 0.5 if (i == 0 or i == ntheta - 1) else 1.0
        rows.append({"theta_deg": t["theta_deg"], "weight": w * dtheta, "donq_m2": donq,
                     "n_slices": len(area), "max_area_m2": max(area), "min_area_m2": min(area)})
    D = float(sum(r["weight"] * r["donq_m2"] for r in rows))
    cd = cdwave_of(case)
    per_theta[case] = rows
    results[case] = {
        "description": desc,
        "n_theta": ntheta,
        "n_slices": sorted({r["n_slices"] for r in rows}),
        "donq_avg_m2": D,
        "cdwave_from_donq_over_100": D / 100.0,
        "cdwave_csv": cd,
        "implied_sref_m2": D / cd,
        "rel_diff_recompute_vs_csv": (D / 100.0 - cd) / cd,
        "donq_min_m2": min(r["donq_m2"] for r in rows),
        "donq_max_m2": max(r["donq_m2"] for r in rows),
        "theta_deg_of_max": max(rows, key=lambda r: r["donq_m2"])["theta_deg"],
        "theta_deg_of_min": min(rows, key=lambda r: r["donq_m2"])["theta_deg"],
        "max_area_over_slices_m2": max(r["max_area_m2"] for r in rows),
    }

def paired(case_a, case_b):
    """weighted mean over theta of Donq_b - Donq_a, matched by common theta grid."""
    a, b = per_theta[case_a], per_theta[case_b]
    if len(a) != len(b):
        return None
    vals = [rb["donq_m2"] - ra["donq_m2"] for ra, rb in zip(a, b)]
    w = [ra["weight"] for ra in a]
    return float(sum(wi * v for wi, v in zip(w, vals))), vals

q = 0.5 * 0.1153178340089936 * 596.0373972278921 ** 2
SREF = 358.25
inc_body_base, vals_body_base = paired("WAVE-01", "WAVE-02")
inc_body_w03, vals_body_w03 = paired("WAVE-03", "WAVE-04")
inc_sweep_wing, vals_sweep_wing = paired("WAVE-01", "WAVE-03")
inc_sweep_wb, vals_sweep_wb = paired("WAVE-02", "WAVE-04")

def stat(vals):
    return {"min": min(vals), "max": max(vals), "mean": float(np.mean(vals))}

results["increments"] = {
    "q_inf_pa": q,
    "reference": {"Sref_m2": SREF, "cref_m": 18.489893, "bref_m": 25.604638},
    "fuselage_zero_lift_volume_wave_drag_increment": {
        "baseline_pair": {"wing_alone_case": "WAVE-01", "wing_body_case": "WAVE-02",
                          "delta_donq_m2": inc_body_base, "delta_D_N": inc_body_base * q,
                          "delta_CD_on_Sref": inc_body_base / SREF, "per_theta_m2": stat(vals_body_base)},
        "w03_pair": {"wing_alone_case": "WAVE-03", "wing_body_case": "WAVE-04",
                     "delta_donq_m2": inc_body_w03, "delta_D_N": inc_body_w03 * q,
                     "delta_CD_on_Sref": inc_body_w03 / SREF, "per_theta_m2": stat(vals_body_w03)},
        "interpretation": "Candidate zero-lift volume wave-drag increment of the fixed fuselage plus wing-body interference in the area-rule sense, at the coarse 36/200 discretization only. Not a calibrated interference model.",
    },
    "w03_plus_1deg_effect": {
        "wing_alone": {"delta_donq_m2": inc_sweep_wing, "delta_D_N": inc_sweep_wing * q,
                       "delta_CD_on_Sref": inc_sweep_wing / SREF, "per_theta_m2": stat(vals_sweep_wing)},
        "wing_body": {"delta_donq_m2": inc_sweep_wb, "delta_D_N": inc_sweep_wb * q,
                      "delta_CD_on_Sref": inc_sweep_wb / SREF, "per_theta_m2": stat(vals_sweep_wb)},
    },
}

coarse = results["WAVE-02"]["donq_avg_m2"]
fine = results["WAVE-05"]["donq_avg_m2"]
fine_rows = per_theta["WAVE-05"]
sub = [fine_rows[j] for j in range(0, len(fine_rows), 2)]
assert len(sub) == len(per_theta["WAVE-02"])
dth = 1.0 / (len(sub) - 1)
D_sub = float(sum((0.5 if (i == 0 or i == len(sub) - 1) else 1.0) * dth * r["donq_m2"] for i, r in enumerate(sub)))
results["resolution_sensitivity"] = {
    "coarse_36rot_200slices": {"donq_avg_m2": coarse, "cdwave_csv": results["WAVE-02"]["cdwave_csv"]},
    "fine_72rot_800slices": {"donq_avg_m2": fine, "cdwave_csv": results["WAVE-05"]["cdwave_csv"]},
    "ratio_fine_over_coarse": fine / coarse,
    "fine_slices_with_coarse_theta_subset_donq_m2": D_sub,
    "slice_effect_ratio_same_theta_grid": D_sub / coarse,
    "theta_sampling_effect_ratio": fine / D_sub,
    "coincident_theta_pairs": [
        {"theta_deg": rc["theta_deg"], "donq_coarse_m2": rc["donq_m2"], "donq_fine_m2": rf["donq_m2"],
         "ratio": rf["donq_m2"] / rc["donq_m2"]}
        for rc in per_theta["WAVE-02"] for rf in fine_rows
        if abs(rc["theta_deg"] - rf["theta_deg"]) < 1e-6
    ],
    "verdict": "NOT_CONVERGED: changing theta count 36->72 and slice count 200->800 changes the area-rule D/q by a factor %.2f." % (fine / coarse),
}
results["outlier_diagnostic"] = {
    "WAVE-05_top5_theta": [
        {"theta_deg": r["theta_deg"], "donq_m2": r["donq_m2"], "max_area_m2": r["max_area_m2"]}
        for r in sorted(fine_rows, key=lambda r: -r["donq_m2"])[:5]
    ],
    "note": "EL solution amplifies discretization spikes at oblique Mach cuts; single theta sections dominate the average.",
}
results["per_theta_donq"] = {case: rows for case, rows in per_theta.items()}
OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")

print(json.dumps({k: results[k] for k in ("WAVE-00R_benchmark", "WAVE-01", "WAVE-02", "WAVE-03", "WAVE-04", "WAVE-05")}, indent=1))
print(json.dumps({k: results[k] for k in ("increments", "resolution_sensitivity", "outlier_diagnostic")}, indent=1))
