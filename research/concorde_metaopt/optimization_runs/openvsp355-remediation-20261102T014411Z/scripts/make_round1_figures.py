# Make the Round-1 (D-12D-003) figures from data already present in this package.
# Data sources: evidence/geometry_parity_355_vs_326.json (this run), role_reviews/a1/geometry_diff.json.
# No solver is started; this script only reads package JSON and writes PNGs.
import json
import os
from pathlib import Path

RUN = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", "D:/RCAIDE/outputs/matplotlib-cache")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

par = json.loads((RUN / "evidence" / "geometry_parity_355_vs_326.json").read_text(encoding="utf-8"))
wing = par["wing_only"]["baseline"]
wb = par["wing_body"]["components"]
fus = wb["fuselage"]

fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"width_ratios": [1.0, 1.25]})

# Panel A: unique vertex counts per component, old 3.26.1 vs new 3.55.0
labels = ["main wing\n(baseline)", "fuselage\n(wing+body model)"]
old = [wing["old"]["unique_old"], fus["old_unique"]]
new = [wing["old"]["unique_new"], fus["new_unique"]]
x = range(len(labels))
axes[0].bar([i - 0.19 for i in x], old, width=0.36, label="OpenVSP 3.26.1 (Python 3.9)", color="#9aa7b4", edgecolor="black", linewidth=0.6)
axes[0].bar([i + 0.19 for i in x], new, width=0.36, label="OpenVSP 3.55.0 (Python 3.11)", color="#2f6db0", edgecolor="black", linewidth=0.6)
axes[0].set_xticks(list(x))
axes[0].set_xticklabels(labels, fontsize=9)
axes[0].set_ylabel("unique STL vertices")
axes[0].set_title("Cross-version geometry parity (unique vertex sets)", fontsize=10.5)
axes[0].legend(fontsize=8, loc="upper right")
axes[0].set_ylim(0, 1350)
axes[0].annotate("identical set\nonly_old=0, only_new=0", xy=(0.0, 1120), ha="center", fontsize=8, color="#1c6b1c")
axes[0].annotate(f"only_new={fus['only_new']}\nmax NN 30.07 mm", xy=(1.0, 600), ha="center", fontsize=8, color="#a33")
axes[0].grid(axis="y", alpha=0.3)

# Panel B: fuselage nearest-neighbour distance brackets (derived from cumulative counts in the JSON)
s = fus["only_new_nn_stats"]
bins = [
    ("<= 1e-6 m", s["le_1e-6"]),
    ("1e-6 - 1e-3 m", s["le_1mm"] - s["le_1e-6"]),
    ("1e-3 - 1e-2 m", s["le_10mm"] - s["le_1mm"]),
    ("1e-2 - 30.07 mm", s["le_30_1mm"] - s["le_10mm"]),
]
axes[1].bar([b[0] for b in bins], [b[1] for b in bins], color="#c46a2f", edgecolor="black", linewidth=0.6)
axes[1].set_ylabel("new fuselage vertices (122 unmatched)")
axes[1].set_title("Fuselage subdivision changed slightly between versions", fontsize=10.5)
axes[1].tick_params(axis="x", labelsize=8)
for i, (lab, val) in enumerate(bins):
    axes[1].annotate(str(val), xy=(i, val + 1.5), ha="center", fontsize=8)
axes[1].annotate(
    f"median {s['median']*1000:.2f} mm, max {s['max']*1000:.2f} mm\n"
    f"= {s['max']/61.66*100:.3f}% of the 61.66 m fuselage length\n"
    "wing vertex set unchanged; paired area-rule runs must be single-version",
    xy=(0.02, 0.66), xycoords="axes fraction", va="top", fontsize=8,
    bbox=dict(boxstyle="round", fc="#f5f5f5", ec="#999"),
)
axes[1].grid(axis="y", alpha=0.3)

fig.suptitle("D-12D-003 Round-1: OpenVSP 3.55.0 vs 3.26.1 geometry parity (zero solver cases, offline STL only)", fontsize=11)
fig.text(0.5, 0.005, "Source: evidence/geometry_parity_355_vs_326.json. STL file hashes differ across versions even where geometry matches; identity is tested on unique vertex sets, not hashes.",
         ha="center", fontsize=7.2, color="#444")
fig.tight_layout(rect=(0, 0.03, 1, 0.95))
out = RUN / "figures" / "geometry_parity_355_vs_326.png"
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out, dpi=130)
print("wrote", out, out.stat().st_size, "bytes")
