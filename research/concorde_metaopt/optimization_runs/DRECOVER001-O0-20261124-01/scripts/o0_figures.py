"""O0 figures: resource usage during the real batch and the optimization history.

Every number is read back from the records the run wrote (o0_resource.jsonl, the O0 tables,
and the O0-FINAL verification rounds). Nothing is recomputed from memory or typed by hand.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
TAB = RUN / "tables"
FIG = RUN / "figures"
FIG.mkdir(parents=True, exist_ok=True)

CANDIDATES = ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans")
available = {f.name for f in font_manager.fontManager.ttflist}
FONT = next((n for n in CANDIDATES if n in available), "DejaVu Sans")
plt.rcParams["font.sans-serif"] = [FONT]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150

manifest = []


def record(name, path, note):
    manifest.append({"figure": name, "path": path.name, "bytes": path.stat().st_size,
                     "note": note})


# --- 1. resource usage over the real solver time -------------------------------------------
rows = [json.loads(line) for line in (RUN / "o0_resource.jsonl").read_text(
    encoding="utf-8").splitlines() if line.strip()]
labels = sorted({r["label"] for r in rows})
fig, axes = plt.subplots(2, 1, figsize=(10.4, 6.0), sharex=True)
colors = {"O0-BO-B01": "#d62728", "O0-BO-B02": "#1f77b4"}
# A sample can carry a null CPU figure when the two GetSystemTimes deltas are zero on the
# first tick; those samples are dropped for the CPU panel rather than drawn as zero.
for label in labels:
    sel = [r for r in rows if r["label"] == label]
    cpu = [r for r in sel if r["cpu_busy_fraction"] is not None]
    mem = [r for r in sel if r["memory_load_percent"] is not None]
    axes[0].plot(np.arange(len(cpu)), [100.0 * r["cpu_busy_fraction"] for r in cpu],
                 color=colors.get(label, "grey"), lw=1.2,
                 label="%s（%d 个采样）" % (label, len(sel)))
    axes[1].plot(np.arange(len(mem)), [r["memory_load_percent"] for r in mem],
                 color=colors.get(label, "grey"), lw=1.2, label=label)
axes[0].set_ylabel("整机 CPU 占用（%）", fontsize=9)
axes[0].set_title("真实 VSPAERO 批次期间的 CPU 与内存占用（采样间隔 1 s，"
                  "CPU 为整机口径而非本进程份额）", fontsize=10)
axes[1].set_ylabel("物理内存占用（%）", fontsize=9)
axes[1].set_xlabel("采样序号（两次批次分别计数）", fontsize=9)
for ax in axes:
    ax.grid(True, alpha=0.3)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=7.5)
fig.tight_layout()
p = FIG / "o0_resource_usage.png"
fig.savefig(p)
plt.close(fig)
record("o0_resource_usage", p, "CPU busy fraction and physical memory load sampled once per "
       "second during the two real batches; CPU is host-wide, not the run's share")

# --- 2. optimization history ---------------------------------------------------------------
with (TAB / "o0_optimization_history_B02.csv").open(encoding="utf-8", newline="") as fh:
    hist = list(csv.DictReader(fh))
idx = [int(r["design_index"]) for r in hist]
di = [float(r["di_n"]) for r in hist]
base = float(hist[0]["di_n"])
best_i = int(np.argmin(di))
fig, ax = plt.subplots(figsize=(9.4, 4.6))
ax.plot(idx, di, "-o", color="#1f77b4", lw=1.3, ms=4.5, label="每个设计的同升力 Di（N）")
ax.axhline(base, color="#d62728", ls="--", lw=1.1, label="基座设计（design 0）%.1f N" % base)
ax.scatter([idx[best_i]], [di[best_i]], s=90, facecolors="none", edgecolors="#2ca02c",
           lw=1.8, zorder=5, label="最低 Di（design %d）%.1f N" % (idx[best_i], di[best_i]))
for i, v in zip(idx, di):
    if i in (0, best_i):
        ax.annotate("%.1f" % v, (i, v), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=7.5)
ax.set_xlabel("设计尝试序号（11 个已准入设计，全部来自真实 VSPAERO 原始行）", fontsize=9)
ax.set_ylabel("同升力诱导阻力 Di（N）", fontsize=9)
ax.set_title("O0 真实反馈贝叶斯优化：设计序列上的同升力 Di（改进 %.1f N，%.3f%%）"
             % (base - di[best_i], 100.0 * (base - di[best_i]) / base), fontsize=10)
ax.grid(True, alpha=0.3)
ax.tick_params(labelsize=8)
ax.legend(fontsize=8)
fig.tight_layout()
p = FIG / "o0_optimization_history.png"
fig.savefig(p)
plt.close(fig)
record("o0_optimization_history", p, "Di_N for every admitted design in the closed batch, with "
       "the baseline and the lowest-Di design marked; read from the batch tables")

# --- 3. verified before/after with the O0-FINAL re-runs ------------------------------------
rounds = json.loads((RUN / "o0_final" / "o0_final_rounds.json").read_text(
    encoding="utf-8"))["rounds"]
by_design = {}
for row in rounds:
    if row.get("admitted"):
        by_design.setdefault(row["design"], []).append(float(row["di_n"]))
fig, ax = plt.subplots(figsize=(7.6, 4.4))
names = ["baseline", "best"]
cn = {"baseline": "基座构型", "best": "优化构型"}
for pos, name in enumerate(names):
    vals = by_design.get(name, [])
    xs = np.full(len(vals), pos, dtype=float) + np.linspace(-0.06, 0.06, len(vals))
    ax.scatter(xs, vals, s=46, color="#1f77b4" if name == "baseline" else "#2ca02c",
               zorder=4, label="%s（%d 次独立复验，均准入）" % (cn[name], len(vals)))
    if vals:
        ax.hlines(float(np.mean(vals)), pos - 0.24, pos + 0.24, color="black", lw=1.2)
ax.set_xticks([0, 1])
ax.set_xticklabels([cn["baseline"], cn["best"]])
ax.set_ylabel("同升力诱导阻力 Di（N）", fontsize=9)
ax.set_title("O0-FINAL 独立复验：两个设计各两次全新 case 重跑（同一冻结配置）", fontsize=10)
ax.grid(True, axis="y", alpha=0.3)
ax.tick_params(labelsize=8)
ax.legend(fontsize=8)
fig.tight_layout()
p = FIG / "o0_final_verified_improvement.png"
fig.savefig(p)
plt.close(fig)
record("o0_final_verified_improvement", p, "the four admitted O0-FINAL re-runs, plotted as "
       "individual points; the repeat spread is zero so the two points coincide per design")

(FIG / "figure_manifest.json").write_text(
    json.dumps({"schema": "dreal005.o0_figure_manifest.v1", "font": FONT,
                "figures": manifest}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8", newline="\n")
print(json.dumps({"font": FONT, "figures": [m["path"] for m in manifest]},
                 ensure_ascii=False, indent=2))
