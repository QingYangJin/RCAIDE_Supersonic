"""Build the full-chain figures for the D-12D-002 run (no solver starts)."""
import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
REPO = Path("D:/RCAIDE")
RUN = REPO / "research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z"
FIG = RUN / "figures"
FIG.mkdir(parents=True, exist_ok=True)
Q_FROZEN = 20483.94023343017
SREF = 358.25

plt.rcParams.update({"font.size": 9, "axes.titlesize": 10, "figure.dpi": 150,
                     "savefig.dpi": 150, "axes.grid": True, "grid.alpha": 0.3})


def load(p):
    return json.loads(Path(p).read_text())


def fig_lf_density():
    res = load(RUN / "lf_vspaero_results.json")
    order = ["SENS-A", "LFV-00", "SENS-B"]
    labels = {"SENS-A": "coarse 8x17", "LFV-00": "medium 16x33", "SENS-B": "fine 32x65"}
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4))
    for case in order:
        rows = res["cases"][case]["rows"]
        rows = sorted(rows, key=lambda r: r["AoA"])
        a = [r["AoA"] for r in rows]
        axes[0].plot(a, [r["CL"] for r in rows], "o-", label=labels[case], ms=3)
        axes[1].plot(a, [r["CDi"] for r in rows], "o-", label=labels[case], ms=3)
        axes[2].plot(a, [r["CDtot"] for r in rows], "o-", label=labels[case], ms=3)
    axes[0].set_title("isolated wing CL vs alpha")
    axes[1].set_title("VSPAERO CDi vs alpha (sign flips / blow-up)")
    axes[2].set_title("VSPAERO CDtot vs alpha (negative at fine)")
    for ax, xl in zip(axes, ["alpha [deg]", "alpha [deg]", "alpha [deg]"]):
        ax.set_xlabel(xl)
        ax.axhline(0, color="k", lw=0.6)
    axes[1].set_yscale("symlog", linthresh=1e-3)
    axes[0].legend()
    fig.suptitle("VSPAERO 6.2.0 thin-surface Mach 2.02: no density convergence - drag result NOT VALIDATED",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / "lf_vspaero_density_sensitivity.png")
    plt.close(fig)


def read_history(path):
    rows = list(csv.reader(open(path)))
    hdr = [h.strip().strip('"') for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        d = {}
        for i, h in enumerate(hdr):
            try:
                d[h] = float(r[i])
            except (ValueError, IndexError):
                d[h] = None
        out.append(d)
    return out


def fig_su2():
    cases = [("HFS-02", "medium (125,876 tets)", "tab:blue"),
             ("HFS-03", "fine (256,455 tets)", "tab:red")]
    hist = {}
    for cid, lab, col in cases:
        p = EXT / "hf" / "wing" / ("history_" + cid + ".csv")
        hist[cid] = read_history(p)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4))
    for cid, lab, col in cases:
        h = hist[cid]
        it = [r["Inner_Iter"] for r in h]
        step = max(1, len(it) // 400)
        axes[0].plot(it[::step], [r["CD"] for r in h][::step], col, lw=1, label=lab)
        axes[1].plot(it[::step], [r["CL"] for r in h][::step], col, lw=1, label=lab)
        axes[2].plot(it[::step], [r["rms[Rho]"] for r in h][::step], col, lw=1, label=lab)
    axes[0].set_title("SU2 Euler isolated wing CD")
    axes[1].set_title("SU2 Euler isolated wing CL")
    axes[2].set_title("rms[Rho] plateau (sharp-LE singularity)")
    axes[2].axhline(-8, color="k", ls="--", lw=0.7)
    axes[2].text(500, -7.6, "requested -8 converged line", fontsize=7)
    for ax in axes:
        ax.set_xlabel("iteration")
        ax.legend()
    fig.suptitle("SU2 8.5.0 Euler, 12D main wing, Mach 2.02, AoA 2.84 deg: forces stable, residual plateau",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / "su2_wing_force_convergence.png")
    plt.close(fig)

    vals = {}
    for cid, _, _ in cases:
        p = EXT / "hf" / "wing" / (cid.lower().replace("-", "") + "_analysis.json")
        if p.exists():
            vals[cid] = load(p)["final"]
    if len(vals) == 2:
        fig, axes = plt.subplots(1, 2, figsize=(8, 3.2))
        names = ["CD", "CL", "CMy"]
        x = np.arange(len(names))
        for i, (cid, lab, col) in enumerate(cases):
            axes[0].bar(x + (i - 0.5) * 0.35, [vals[cid][n] for n in names], width=0.35,
                        label=lab, color=col)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_title("medium vs fine")
        axes[0].legend()
        for i, (cid, lab, col) in enumerate(cases):
            for j, n in enumerate(names):
                axes[0].text(j + (i - 0.5) * 0.35, vals[cid][n], "%.5f" % vals[cid][n],
                             ha="center", va="bottom", fontsize=6)
        rel = [(vals["HFS-03"][n] - vals["HFS-02"][n]) / abs(vals["HFS-02"][n]) * 100 for n in names]
        axes[1].bar(names, rel, color="tab:purple")
        axes[1].axhline(0, color="k", lw=0.6)
        axes[1].set_ylabel("fine vs medium [%]")
        axes[1].set_title("relative change (fine - medium)")
        for i, v in enumerate(rel):
            axes[1].text(i, v, "%+.2f%%" % v, ha="center", va="bottom" if v >= 0 else "top", fontsize=8)
        fig.suptitle("SU2 grid sensitivity: only two levels available (coarse level failed and consumed its budget slot)",
                     fontsize=9)
        fig.tight_layout()
        fig.savefig(FIG / "su2_wing_mesh_sensitivity.png")
        plt.close(fig)


def fig_drag():
    e2e = load(RUN / "mission_e2e.json")
    rc = e2e["cases"]["E2E-00"]["drag_ledger"]
    comp = rc["component_drag_magnitude_n"]
    wave = load(RUN / "wave_drag_area_rule.json")
    inc = wave["fuselage_zero_lift_volume_wave_drag_increment"]["baseline_pair"]
    su2 = {}
    for cid in ("HFS-02", "HFS-03"):
        p = EXT / "hf" / "wing" / (cid.lower().replace("-", "") + "_analysis.json")
        if p.exists():
            su2[cid] = load(p)["final"]["CD"] * Q_FROZEN * SREF
    entries = [
        ("RCAIDE parasite (viscous+form)", comp["parasite"]),
        ("RCAIDE induced (VLM Trefftz)", comp["induced"]),
        ("RCAIDE compressible (empirical)", comp["compressible"]),
        ("RCAIDE total", rc["total_drag_magnitude_n"]),
    ]
    if "HFS-02" in su2:
        entries.append(("SU2 Euler wing (medium)", su2["HFS-02"]))
    if "HFS-03" in su2:
        entries.append(("SU2 Euler wing (fine)", su2["HFS-03"]))
    entries += [
        ("area rule wing alone", wave["cases"]["WAVE-01"]["donq_avg_m2"] * Q_FROZEN),
        ("area rule wing+body", wave["cases"]["WAVE-02"]["donq_avg_m2"] * Q_FROZEN),
        ("area-rule paired increment", inc["delta_D_N"]),
    ]
    entries = [e for e in entries if e[1]]
    labels = [e[0] for e in entries]
    vals = [e[1] for e in entries]
    colors = []
    for l in labels:
        colors.append("tab:red" if l.startswith("area") else ("tab:green" if l.startswith("SU2") else "tab:blue"))
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    y = np.arange(len(labels))
    ax.barh(y, vals, color=colors, alpha=0.85)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xscale("log")
    ax.set_xlabel("drag magnitude on Sref = 358.25 m2 [N] (log scale)")
    for i, v in enumerate(vals):
        ax.text(v * 1.08, i, "%.0f N" % v, va="center", fontsize=7)
    ax.invert_yaxis()
    ax.set_title("Drag bookkeeping at Mach 2.02: components are NOT additive across tools\n"
                 "(different physics, different CL, LF VSPAERO drag unusable, area-rule level not converged)",
                 fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "drag_component_bookkeeping.png")
    plt.close(fig)


def fig_e2e():
    e2e = load(RUN / "mission_e2e.json")
    cases = e2e["cases"]
    order = ["E2E-00", "E2E-01", "LFV-04", "LFV-05"]
    names = {"E2E-00": "12D baseline", "E2E-01": "W10 tip twist +2 deg",
             "LFV-04": "V01 tail area +1%", "LFV-05": "V02 tail sweep +2 deg"}
    vals = [cases[c]["objective_fuel_burn_kg"] for c in order]
    deltas = [cases[c]["delta_vs_E2E_00_kg"] for c in order]
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    x = np.arange(len(order))
    ax.bar(x, vals, color=["tab:gray", "tab:orange", "tab:cyan", "tab:purple"])
    ax.set_xticks(x)
    ax.set_xticklabels([names[c] for c in order], fontsize=8)
    ax.set_ylabel("single-cruise fuel burn [kg]")
    ax.set_ylim(min(vals) - 60, max(vals) + 30)
    for i, (v, d) in enumerate(zip(vals, deltas)):
        ax.text(i, v + 3, "%.2f kg\n(%+.3f kg)" % (v, d), ha="center", fontsize=7)
    ax.set_title("RCAIDE LF single-cruise chain (Mach 2.02, 6.5-hour-class cruise, 3028020 m)\n"
                 "E2E-00 reproduces the archived baseline exactly: 34109.48257123768 kg", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "mission_e2e_fuel_deltas.png")
    plt.close(fig)


def main():
    fig_lf_density()
    fig_su2()
    fig_drag()
    fig_e2e()
    print("figures written:")
    for p in sorted(FIG.glob("*.png")):
        print(" ", p.name, p.stat().st_size)


if __name__ == "__main__":
    main()
