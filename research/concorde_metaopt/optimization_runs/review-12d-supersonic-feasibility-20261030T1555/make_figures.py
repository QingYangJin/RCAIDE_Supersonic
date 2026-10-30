"""Figures for the 12D supersonic feasibility review.

Data sources are archived files only; nothing is recomputed or simulated here.
- figures/p2_smoke_perturbation_delta.png: P2 smoke fuel-burn deltas vs each run's own baseline.
  source: optimization_runs/smoke-p2-20261029T1520/summary.json and
          optimization_runs/smoke-p2-20261029T1612/summary.json
- figures/evidence_call_ledger.png: archived physical-call ledger.
  source: existing_evidence_inventory.json (verified against each run summary.json)
"""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RUN = Path(__file__).resolve().parent
ROOT = RUN.parent
OUT = RUN / "figures"
OUT.mkdir(exist_ok=True)

def load(run_id):
    with open(ROOT / run_id / "summary.json", encoding="utf-8") as fh:
        return json.load(fh)

s1520 = load("smoke-p2-20261029T1520")
s1612 = load("smoke-p2-20261029T1612")

deltas = {
    "smoke 1520\n(145 t contract)": {
        "W01 wing area +1%": (36384.415908260984 - 36469.32557559651),
        "W10 tip twist +2 deg": (36479.34300305339 - 36469.32557559651),
    },
    "smoke 1612\n(136 t contract)": {
        "W01 wing area +1%": (34035.332605355274 - 34109.48257123768),
        "W10 tip twist +2 deg": (34117.55529648991 - 34109.48257123768),
    },
}

fig, ax = plt.subplots(figsize=(7.4, 4.2), dpi=200)
groups = list(deltas.keys())
cases = list(deltas[groups[0]].keys())
colors = ["#1b6ca8", "#c0504d"]
x = np.arange(len(groups))
width = 0.34
for i, case in enumerate(cases):
    vals = [deltas[g][case] for g in groups]
    bars = ax.bar(x + (i - 0.5) * width, vals, width, label=case, color=colors[i], edgecolor="black", linewidth=0.3)
    for b, v in zip(bars, vals):
        ax.annotate(f"{v:+.1f}", (b.get_x() + b.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 5 if v >= 0 else -11),
                    ha="center", fontsize=9)
ax.axhline(0, color="black", linewidth=0.9)
ax.set_xticks(x)
ax.set_xticklabels(groups, fontsize=9)
ax.set_ylim(-105, 25)
ax.set_ylabel("fuel burn change vs run baseline (kg)", fontsize=9)
ax.set_title("Archived P2 smoke: relative fuel-burn sensitivity\n(real RCAIDE VLM single-cruise Mission; different mass contracts)", fontsize=10)
ax.legend(fontsize=8, loc="lower left", framealpha=0.95)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(OUT / "p2_smoke_perturbation_delta.png")
plt.close(fig)

assert s1520["total_true_evaluations"] == 5 and s1520["low_fidelity_calls"] == 5 and s1520["su2_calls"] == 0
assert s1612["total_true_evaluations"] == 5 and s1612["low_fidelity_calls"] == 5 and s1612["su2_calls"] == 0
doe = load("doe-p3-20261029T1725")
assert doe["total_true_evaluations"] == 0 and doe["su2_calls"] == 0
labels = ["RCAIDE Mission\n(single cruise, LF)", "VSPAERO solves", "SU2 solves", "DOE candidates\n(geometry only)"]
counts = [10, 0, 0, 160]
colors2 = ["#1b6ca8", "#bbbbbb", "#bbbbbb", "#e0a33a"]
fig, ax = plt.subplots(figsize=(7.4, 3.8), dpi=200)
fig.subplots_adjust(left=0.30, right=0.97, top=0.84, bottom=0.26)
bars = ax.barh(labels[::-1], counts[::-1], color=colors2[::-1], edgecolor="black", linewidth=0.4)
for b, v in zip(bars, counts[::-1]):
    ax.annotate(str(v), (b.get_width(), b.get_y() + b.get_height() / 2),
                textcoords="offset points", xytext=(7, 0), va="center", fontsize=9)
ax.set_xlim(0, 190)
ax.set_xlabel("archived count (DOE candidates are geometry-only, 0 physical labels)", fontsize=8.5)
ax.set_title("Archived evidence ledger at HEAD 1f79924\n(no new physics call was executed for this review)", fontsize=10)
ax.grid(axis="x", alpha=0.3)
fig.text(0.5, 0.055, "VSPAERO / SU2: NOT_RUN   |   DOE: 160 geometry candidates, not fuel-burn labels",
         ha="center", fontsize=7.5, color="#444444")
fig.savefig(OUT / "evidence_call_ledger.png")
plt.close(fig)
print("figures written")
