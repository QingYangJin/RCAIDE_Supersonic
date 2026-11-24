"""O1 figures: the anytime comparison across the three arms, resource usage, and the final
geometry comparison. Every number is read back from the run's own records.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
FIG = RUN / "figures"
FIG.mkdir(parents=True, exist_ok=True)

CANDIDATES = ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans")
available = {f.name for f in font_manager.fontManager.ttflist}
FONT = next((n for n in CANDIDATES if n in available), "DejaVu Sans")
plt.rcParams["font.sans-serif"] = [FONT]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150

COLORS = {"SOBOL_BO": "#1565c0", "COND_SUPERVISED_KSHOT_BO": "#2e7d32",
          "COND_FOMAML_KSHOT_BO": "#c62828"}
LABELS = {"SOBOL_BO": "Sobol + BO（无热启动）",
          "COND_SUPERVISED_KSHOT_BO": "条件监督 16D + 模型排序热启动",
          "COND_FOMAML_KSHOT_BO": "条件 FOMAML 16D + 模型排序热启动"}

result = json.loads((RUN / "o1_result.json").read_text(encoding="utf-8"))
arms = result["arms"]
base = result["regression"]["baseline_di_n"]
target = result["regression"]["target_di_n"]
manifest = []


def record(name, path, note):
    manifest.append({"figure": name, "path": path.name, "bytes": path.stat().st_size,
                     "note": note})


# --- 1. anytime comparison ------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10.6, 6.0))
for arm, payload in arms.items():
    points = payload["anytime"]
    xs = [p["cumulative_starts"] for p in points if p["best_so_far"] is not None]
    ys = [p["best_so_far"] for p in points if p["best_so_far"] is not None]
    ax.plot(xs, ys, marker="o", ms=4.5, lw=1.8, color=COLORS[arm],
            label="%s（最优 %.1f N，降 %.2f%%）" % (
                LABELS[arm], payload["best_feasible_di_n"],
                100.0 * payload["improvement_fraction"]))
ax.axhline(base, color="#555555", ls="--", lw=1.1,
           label="基线 Di = %.1f N" % base)
ax.axhline(target, color="#999999", ls=":", lw=1.1,
           label="预注册目标 = %.1f N（−0.1%%）" % target)
ax.set_xlabel("累计等效 solver starts（shared support 计入每臂）", fontsize=10)
ax.set_ylabel("目前最优 Di_N（N）", fontsize=10)
ax.set_title("O1 三臂随时最优对比（真实 VSPAERO 原始极曲线行，M=1.9，18 288 m）", fontsize=11.5)
ax.grid(alpha=0.25)
ax.legend(fontsize=8.8, loc="upper right")
fig.text(0.01, 0.01, "数据来源：o1_result.json 的 anytime 序列；每点为一个已准入设计。",
         fontsize=8.5, color="#444444")
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(FIG / "o1_anytime_comparison.png")
record("o1_anytime_comparison.png", FIG / "o1_anytime_comparison.png",
       "三臂随时最优曲线、基线、预注册目标")
plt.close(fig)

# --- 2. per-arm endpoint bars ---------------------------------------------------------------
fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.8))
order = list(arms)
short = ["Sobol+BO", "条件监督\n+热启动", "条件FOMAML\n+热启动"]
bars = [arms[a]["best_feasible_di_n"] for a in order]
axes[0].bar(short, bars, color=[COLORS[a] for a in order], alpha=0.85)
axes[0].axhline(base, color="#555555", ls="--", lw=1.1, label="基线")
axes[0].set_ylabel("最优 Di_N（N）", fontsize=9.5)
axes[0].set_title("各臂最优 Di（越低越好）", fontsize=10.5)
axes[0].legend(fontsize=8.5)
axes[0].set_ylim(min(bars) * 0.985, base * 1.004)

frac = [100.0 * arms[a]["improvement_fraction"] for a in order]
axes[1].bar(short, frac, color=[COLORS[a] for a in order], alpha=0.85)
axes[1].axhline(0.1, color="#999999", ls=":", lw=1.1, label="预注册目标 0.1%")
axes[1].set_ylabel("相对基线降幅（%）", fontsize=9.5)
axes[1].set_title("实测降幅与预注册目标", fontsize=10.5)
axes[1].legend(fontsize=8.5)

starts = [arms[a]["equivalent_starts_to_target"] for a in order]
axes[2].bar(short, starts, color=[COLORS[a] for a in order], alpha=0.85)
axes[2].set_ylabel("达到目标的等效 starts", fontsize=9.5)
axes[2].set_title("达到 −0.1% 目标所需成本", fontsize=10.5)

for ax in axes:
    ax.grid(alpha=0.2, axis="y")
    ax.tick_params(labelsize=8.5)
fig.suptitle("O1 三臂端点对比（每臂 8 个设计 / 16 等效 starts，三臂同点截断）", fontsize=11.5)
fig.tight_layout(rect=(0, 0.02, 1, 0.94))
fig.savefig(FIG / "o1_three_arm_endpoint.png")
record("o1_three_arm_endpoint.png", FIG / "o1_three_arm_endpoint.png",
       "每臂最优 Di / 降幅 / 达标的等效 starts")
plt.close(fig)

# --- 3. resource usage ----------------------------------------------------------------------
rows = []
for line in (RUN / "o1_resource.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        rows.append(json.loads(line))
cpu = [r for r in rows if r.get("cpu_busy_fraction") is not None]
mem = [r for r in rows if r.get("memory_load_percent") is not None]
fig, axes = plt.subplots(2, 1, figsize=(10.4, 5.6), sharex=True)
axes[0].plot(np.arange(len(cpu)), [100.0 * r["cpu_busy_fraction"] for r in cpu],
             color="#1565c0", lw=1.2)
axes[0].set_ylabel("整机 CPU 占用（%）", fontsize=9)
axes[0].set_title("O1 真实批次期间的 CPU 与内存（采样间隔 1 s，CPU 为整机口径）", fontsize=10)
axes[1].plot(np.arange(len(mem)), [r["memory_load_percent"] for r in mem],
             color="#c62828", lw=1.2)
axes[1].set_ylabel("物理内存占用（%）", fontsize=9)
axes[1].set_xlabel("采样序号", fontsize=9)
for ax in axes:
    ax.grid(alpha=0.2)
summary = json.loads((RUN / "o1_resource.summary.json").read_text(encoding="utf-8"))
fig.text(0.01, 0.01, "samples=%d，CPU 均值 %.2f%%、峰值 %.2f%%，内存均值 %.1f%%，wall %.1f s"
         % (summary["sample_count"], 100.0 * summary["cpu_busy_mean"],
            100.0 * summary["cpu_busy_max"], 100.0 * summary["memory_load_mean"],
            summary["wall_clock_s"]), fontsize=8.5, color="#444444")
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(FIG / "o1_resource_usage.png")
record("o1_resource_usage.png", FIG / "o1_resource_usage.png", "批次期间整机 CPU 与内存")
plt.close(fig)

(FIG / "figure_manifest.json").write_text(
    json.dumps({"schema": "dreal005.o1_figures.v1", "font": FONT, "figures": manifest},
               ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"font": FONT, "figures": manifest}, ensure_ascii=False, indent=2))
