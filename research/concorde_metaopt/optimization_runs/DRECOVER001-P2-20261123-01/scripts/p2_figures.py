
"""P2 figures: four-arm K-shot MAE, per-task errors, training curves, parity, offline selection."""
from __future__ import annotations
import csv, json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
TAB = RUN / "tables"
FIG = RUN / "figures"
FIG.mkdir(parents=True, exist_ok=True)
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

ARMS = ["RANDOM_INIT", "POOLED_PRETRAIN", "TASK_COND_PRETRAIN", "FOMAML"]
CN = {"RANDOM_INIT": "随机初始化", "POOLED_PRETRAIN": "普通联合预训练",
      "TASK_COND_PRETRAIN": "任务条件预训练", "FOMAML": "FOMAML"}
COLORS = {"RANDOM_INIT": "#9e9e9e", "POOLED_PRETRAIN": "#1f77b4",
          "TASK_COND_PRETRAIN": "#2ca02c", "FOMAML": "#d62728"}

def rows(path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))

metrics = rows(TAB / "p2_arm_metrics.csv")
preds = rows(TAB / "p2_predictions.csv")
curves = rows(TAB / "p2_training_curves.csv")
sel = json.loads((RUN / "training" / "p2_offline_selection.json").read_text(encoding="utf-8"))["rows"]
ds = json.loads((RUN / "p2_dataset" / "p2_dataset.json").read_text(encoding="utf-8"))
split = {t["task_id"]: t["split"] for t in ds["tasks"]}
label = {t["task_id"]: t["task_id"].replace("P2-CANON-", "") + ("（" + t["split"] + "）") for t in ds["tasks"]}
fig_rows = []

# fig1: mean MAE by arm x K x split
ks = sorted({int(r["k"]) for r in metrics})
fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.3), sharey=True)
for ax, sp in zip(axes, ("val", "test")):
    width = 0.2
    for i, arm in enumerate(ARMS):
        vals, errs = [], []
        for k in ks:
            v = [float(r["mae_n"]) for r in metrics if r["arm"] == arm and int(r["k"]) == k
                 and split.get(r["task_id"]) == sp]
            vals.append(float(np.mean(v)) if v else 0.0)
            errs.append(float(np.std(v)) if v else 0.0)
            for k, m in zip(ks, vals):
                pass
        xs = np.arange(len(ks)) + i * width - 1.5 * width
        ax.bar(xs, vals, width, color=COLORS[arm], label=CN[arm], yerr=errs, capsize=2)
        for x, v in zip(xs, vals):
            ax.text(x, v, "%.0f" % v, ha="center", va="bottom", fontsize=6.5, rotation=90)
            fig_rows.append({"figure": "fig1_arm_mae_by_k", "split": sp, "arm": arm,
                             "k": None, "value": v})
    ax.set_xticks(np.arange(len(ks)))
    ax.set_xticklabels(["K=%d" % k for k in ks])
    ax.set_title("验证集（M180/M220）" if sp == "val" else "留出测试集（M240/M260）", fontsize=10)
    ax.grid(True, axis="y", alpha=0.3)
    ax.tick_params(labelsize=8)
axes[0].set_ylabel("逐任务 MAE（N，独立 query 行）", fontsize=9)
axes[0].legend(fontsize=7.5)
fig.suptitle("P2 四臂对照：真实准入标签上的 K-shot 逐任务平均 MAE（误差棒=跨任务/种子标准差）", fontsize=10)
fig.tight_layout()
fig.savefig(FIG / "p2_arm_mae_by_k.png", dpi=170)
plt.close(fig)

# fix fig1 rows: record per k
fig_rows = [r for r in fig_rows if False]
for sp in ("val", "test"):
    for arm in ARMS:
        for k in ks:
            v = [float(r["mae_n"]) for r in metrics if r["arm"] == arm and int(r["k"]) == k
                 and split.get(r["task_id"]) == sp]
            fig_rows.append({"figure": "fig1_arm_mae_by_k", "split": sp, "arm": arm,
                             "k": k, "value": float(np.mean(v)) if v else ""})

# fig2: per-task MAE, panels by K
eval_tasks = [t["task_id"] for t in ds["tasks"] if t["split"] in ("val", "test")]
fig, axes = plt.subplots(1, len(ks), figsize=(12.2, 4.2), sharey=True)
for ax, k in zip(np.atleast_1d(axes), ks):
    width = 0.2
    for i, arm in enumerate(ARMS):
        vals = []
        for t in eval_tasks:
            v = [float(r["mae_n"]) for r in metrics
                 if r["arm"] == arm and int(r["k"]) == k and r["task_id"] == t]
            vals.append(float(np.mean(v)) if v else 0.0)
        xs = np.arange(len(eval_tasks)) + i * width - 1.5 * width
        ax.bar(xs, vals, width, color=COLORS[arm], label=CN[arm])
        for x, v in zip(xs, vals):
            fig_rows.append({"figure": "fig2_per_task_mae", "split": split[eval_tasks[int(x // 1)] if False else eval_tasks[0]],
                             "arm": arm, "k": k, "value": v})
    ax.set_xticks(np.arange(len(eval_tasks)))
    ax.set_xticklabels([label[t] for t in eval_tasks], fontsize=7.5)
    ax.set_title("K=%d" % k, fontsize=10)
    ax.grid(True, axis="y", alpha=0.3)
    ax.tick_params(labelsize=8)
axes[0].set_ylabel("MAE（N）", fontsize=9)
axes[0].legend(fontsize=7.5)
fig.suptitle("P2 逐任务 K-shot MAE（每任务 1–3 个独立 query 行；种子 7/19/43 平均）", fontsize=10)
fig.tight_layout()
fig.savefig(FIG / "p2_per_task_mae.png", dpi=170)
plt.close(fig)

# rebuild fig2 rows properly
fig_rows = [r for r in fig_rows if r["figure"] != "fig2_per_task_mae"]
for arm in ARMS:
    for k in ks:
        for t in eval_tasks:
            v = [float(r["mae_n"]) for r in metrics
                 if r["arm"] == arm and int(r["k"]) == k and r["task_id"] == t]
            fig_rows.append({"figure": "fig2_per_task_mae", "split": split[t], "arm": arm,
                             "k": k, "value": float(np.mean(v)) if v else ""})

# fig3: training curves (outer loss) by arm
fig, ax = plt.subplots(figsize=(8.6, 4.4))
for arm in ARMS:
    sub = [r for r in curves if r["arm"] == arm and r["outer_loss"] not in ("", None)]
    if not sub:
        continue
    steps = sorted({int(r["step"]) for r in sub})
    mean = [np.mean([float(r["outer_loss"]) for r in sub if int(r["step"]) == s]) for s in steps]
    lo = [np.min([float(r["outer_loss"]) for r in sub if int(r["step"]) == s]) for s in steps]
    hi = [np.max([float(r["outer_loss"]) for r in sub if int(r["step"]) == s]) for s in steps]
    ax.plot(steps, mean, color=COLORS[arm], label=CN[arm])
    ax.fill_between(steps, lo, hi, color=COLORS[arm], alpha=0.13)
    for s, m in zip(steps, mean):
        fig_rows.append({"figure": "fig3_training_curves", "split": "train", "arm": arm,
                         "k": None, "value": m, "step": s})
ax.set_xlabel("外循环步数", fontsize=9)
ax.set_ylabel("训练/外循环损失（归一化目标）", fontsize=9)
ax.set_title("P2 训练曲线：K=1 与 K=3 共 6 条曲线按步平均（阴影为最小–最大）；随机初始化无训练", fontsize=9)
ax.grid(True, alpha=0.3)
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(FIG / "p2_training_curves.png", dpi=170)
plt.close(fig)

# fig4: parity plot per arm (val+test query rows)
fig, axes = plt.subplots(2, 2, figsize=(10.4, 9.0), sharex=True, sharey=True)
for ax, arm in zip(axes.ravel(), ARMS):
    sub = [r for r in preds if r["arm"] == arm]
    for k in ks:
        pts = [r for r in sub if int(r["k"]) == k]
        ax.scatter([float(r["target_n"]) / 1000 for r in pts], [float(r["prediction_n"]) / 1000 for r in pts],
                   s=22, alpha=0.75, label="K=%d" % k, color=COLORS[arm],
                   marker="o" if k == 1 else "s")
    lims = [95, 155]
    ax.plot(lims, lims, "k--", linewidth=0.8)
    ax.set_title(CN[arm], fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7.5)
    ax.tick_params(labelsize=8)
    for r in sub:
        fig_rows.append({"figure": "fig4_parity", "split": split[r["task_id"]], "arm": arm,
                         "k": int(r["k"]), "value": float(r["prediction_n"]),
                         "target": float(r["target_n"]), "task_id": r["task_id"]})
for ax in axes[:, 0]:
    ax.set_ylabel("模型预测 Di_N（kN）", fontsize=9)
for ax in axes[1, :]:
    ax.set_xlabel("真实准入 Di_N（kN）", fontsize=9)
fig.suptitle("P2 预测–真值对照（验证+测试任务独立 query 行；虚线为 y=x）", fontsize=10)
fig.tight_layout()
fig.savefig(FIG / "p2_prediction_parity.png", dpi=170)
plt.close(fig)

# fig5: offline selection regret
fig, ax = plt.subplots(figsize=(9.2, 4.3))
sel_tasks = sorted({r["task_id"] for r in sel})
width = 0.2
for i, arm in enumerate(ARMS):
    vals = []
    for t in sel_tasks:
        v = [float(r["selection_regret_n"]) for r in sel if r["arm"] == arm and r["task_id"] == t]
        vals.append(float(np.mean(v)) if v else 0.0)
    xs = np.arange(len(sel_tasks)) + i * width - 1.5 * width
    ax.bar(xs, vals, width, color=COLORS[arm], label=CN[arm])
    for x, v in zip(xs, vals):
        fig_rows.append({"figure": "fig5_offline_selection_regret", "split": split.get(sel_tasks[int(round(x - i * width + 1.5 * width))], ""),
                         "arm": arm, "k": None, "value": v})
ax.set_xticks(np.arange(len(sel_tasks)))
ax.set_xticklabels([label[t] for t in sel_tasks], fontsize=7.5)
ax.set_ylabel("离线挑选遗憾（N）", fontsize=9)
ax.set_title("P2 离线候选排序诊断：按预测最小 Di_N 选设计，与真实最优的差异（非在线优化、非 P3）", fontsize=9)
ax.grid(True, axis="y", alpha=0.3)
ax.legend(fontsize=7.5)
fig.tight_layout()
fig.savefig(FIG / "p2_offline_selection_regret.png", dpi=170)
plt.close(fig)

with (FIG / "figure_data.csv").open("w", encoding="utf-8", newline="") as fh:
    fields = ["figure", "split", "arm", "k", "value", "target", "task_id", "step"]
    w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in fig_rows:
        w.writerow(r)
print("figures", sorted(p.name for p in FIG.glob("*.png")))
print("figure_data rows", len(fig_rows))
