"""A0 ablation figures from the actual training result (Chinese labels, real numbers).

Every figure is paired with the CSV it was drawn from so a reader can recompute it. No
figure is drawn from a number that is not in tables/a0_arm_metrics.csv or a0_result.json.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

A0 = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01")
FIG = A0 / "figures"
TAB = A0 / "tables"

CANDIDATES = ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC",
              "DejaVu Sans")


def pick_font() -> str:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in CANDIDATES:
        if name in available:
            return name
    return "DejaVu Sans"


FONT = pick_font()
plt.rcParams["font.sans-serif"] = [FONT]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150

ARM_LABEL = {
    "RANDOM_INIT": "随机初始化",
    "POOLED_PRETRAIN_12D": "池化预训练 12维",
    "COND_SUPERVISED_16D": "条件监督 16维",
    "FOMAML_12D": "FOMAML 12维",
    "COND_FOMAML_16D": "条件FOMAML 16维",
}
COLOR = {
    "RANDOM_INIT": "#9e9e9e",
    "POOLED_PRETRAIN_12D": "#42a5f5",
    "COND_SUPERVISED_16D": "#2e7d32",
    "FOMAML_12D": "#ef6c00",
    "COND_FOMAML_16D": "#6a1b9a",
}


def load_metrics():
    with open(TAB / "a0_arm_metrics.csv", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_result():
    return json.loads((A0 / "training/a0_result.json").read_text(encoding="utf-8"))


def mean(rows, split):
    by = {}
    for row in rows:
        if row["split"] != split:
            continue
        by.setdefault((row["arm"], int(row["k"])), []).append(float(row["mae_n"]))
    out = {}
    for key, values in by.items():
        out[key] = (sum(values) / len(values), len(values))
    return out


def fig_main(metrics) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), sharey=True)
    ks = [0, 1, 3]
    for ax, split, title in ((axes[0], "val", "验证集（2 任务）"),
                             (axes[1], "test", "测试集（2 任务）")):
        data = mean(metrics, split)
        for arm in ARM_LABEL:
            ys = [data.get((arm, k), (float("nan"), 0))[0] for k in ks]
            ax.plot(ks, ys, marker="o", linewidth=2.2, label=ARM_LABEL[arm],
                    color=COLOR[arm])
        ax.set_title(title, fontsize=13)
        ax.set_xlabel("K（真实 support 数量）")
        ax.set_xticks(ks)
        ax.grid(alpha=0.3)
        ax.set_yscale("log")
    axes[0].set_ylabel("平均 MAE（N，对数刻度）")
    axes[0].legend(fontsize=9, framealpha=0.9)
    fig.suptitle("A0 五臂消融：44 条真实准入标签上的实际梯度训练（每点为 2 任务×3 seed 均值）",
                 fontsize=13)
    fig.text(0.01, 0.01,
             "数据来源：tables/a0_arm_metrics.csv；物理求解器启动 0 次；标签来源为已准入的真实 VSPAERO 极曲线行。",
             fontsize=8.5, color="#444444")
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    fig.savefig(FIG / "a0_five_arm_mae_vs_k.png")
    plt.close(fig)


def fig_condition_effect(metrics) -> None:
    """Isolate the condition vector: 12D vs 16D for the two matched pairs."""
    data = mean(metrics, "test")
    ks = [0, 1, 3]
    pairs = (("POOLED_PRETRAIN_12D", "COND_SUPERVISED_16D",
              "监督：12维 → 16维（加入4维任务条件）"),
             ("FOMAML_12D", "COND_FOMAML_16D",
              "元学习：12维 → 16维（加入4维任务条件）"))
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.8), sharey=True)
    for ax, (base_arm, cond_arm, title) in zip(axes, pairs):
        base = [data.get((base_arm, k), (float("nan"), 0))[0] for k in ks]
        cond = [data.get((cond_arm, k), (float("nan"), 0))[0] for k in ks]
        x = range(len(ks))
        ax.bar([i - 0.19 for i in x], base, width=0.36,
               label=ARM_LABEL[base_arm], color=COLOR[base_arm])
        ax.bar([i + 0.19 for i in x], cond, width=0.36,
               label=ARM_LABEL[cond_arm], color=COLOR[cond_arm])
        for i, (b, c) in enumerate(zip(base, cond)):
            if b and c:
                ax.text(i, max(b, c) * 1.05, "%.0f%%" % (100.0 * (c - b) / b),
                        ha="center", fontsize=9, color="#b71c1c")
        ax.set_xticks(list(x))
        ax.set_xticklabels(["K=%d" % k for k in ks])
        ax.set_title(title, fontsize=12)
        ax.set_ylabel("测试集平均 MAE（N）")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3, axis="y")
    fig.suptitle("A0 机制归因：主要收益来自 4 维任务条件特征，而不是元学习目标本身", fontsize=13)
    fig.text(0.01, 0.01,
             "红色百分比为条件臂相对同族 12 维臂的 MAE 变化；数据来源 tables/a0_arm_metrics.csv。",
             fontsize=8.5, color="#444444")
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))
    fig.savefig(FIG / "a0_condition_vector_effect.png")
    plt.close(fig)


def fig_meta_effect(metrics) -> None:
    """The primary mechanism contrast: COND_FOMAML_16D minus COND_SUPERVISED_16D."""
    data = mean(metrics, "test")
    ks = [0, 1, 3]
    deltas = [data.get(("COND_FOMAML_16D", k), (0, 0))[0]
              - data.get(("COND_SUPERVISED_16D", k), (0, 0))[0] for k in ks]
    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    colors = ["#c62828" if d > 0 else "#2e7d32" for d in deltas]
    bars = ax.bar(["K=%d" % k for k in ks], deltas, color=colors, width=0.55)
    for bar, delta in zip(bars, deltas):
        ax.text(bar.get_x() + bar.get_width() / 2,
                delta + (400 if delta > 0 else -1200), "%.0f N" % delta,
                ha="center", fontsize=10)
    ax.axhline(0, color="#333333", linewidth=1)
    ax.set_ylabel("测试集 MAE 差（条件FOMAML16维 − 条件监督16维，N）")
    ax.set_title("A0 核心配对：同为 16 维条件输入，元学习目标在 K=1/3 有小幅收益、K=0 更差",
                 fontsize=12)
    ax.grid(alpha=0.3, axis="y")
    fig.text(0.01, 0.01,
             "负值表示条件FOMAML更好；数据来源 a0_result.json 的 core_pair 与 tables/a0_arm_metrics.csv。",
             fontsize=8.5, color="#444444")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIG / "a0_meta_objective_delta.png")
    plt.close(fig)


def fig_cost(metrics, result) -> None:
    cost = result["cost"]
    with open(TAB / "a0_cost.csv", encoding="utf-8") as handle:
        cost_rows = list(csv.DictReader(handle))
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.4))
    arms = list(ARM_LABEL)
    walls = []
    updates = []
    for arm in arms:
        rows = [r for r in cost_rows if r["arm"] == arm]
        walls.append(sum(float(r["wall_s"] or 0) for r in rows))
        updates.append(sum(int(float(r["outer_gradient_updates"] or 0)
                              + float(r["inner_gradient_updates"] or 0)) for r in rows))
    axes[0].barh([ARM_LABEL[a] for a in arms], walls, color=[COLOR[a] for a in arms])
    for i, value in enumerate(walls):
        axes[0].text(value, i, " %.2f s / %d 次更新" % (value, updates[i]),
                     va="center", fontsize=9)
    axes[0].set_xlim(0, max(walls) * 1.9 if max(walls) > 0 else 1)
    axes[0].set_xlabel("该臂在 3 seed × 3 K 上的累计训练墙钟（s）")
    axes[0].set_title("训练成本（离线，无物理启动）", fontsize=12)
    axes[0].grid(alpha=0.3, axis="x")
    labels = ["CPU 平均占用", "内存平均占用"]
    values = [100.0 * cost["cpu_busy_fraction_mean"], cost["memory_load_percent_mean"]]
    bars = axes[1].bar(labels, values, color=["#1565c0", "#6a1b9a"], width=0.5)
    for bar, value in zip(bars, values):
        axes[1].text(bar.get_x() + bar.get_width() / 2, value + 1.5, "%.1f%%" % value,
                     ha="center", fontsize=10)
    axes[1].set_ylim(0, 100)
    axes[1].set_ylabel("百分比（%）")
    axes[1].set_title("A0 训练期间主机资源占用（采样 %d 次）" % cost["resource_samples"],
                      fontsize=12)
    axes[1].grid(alpha=0.3, axis="y")
    fig.suptitle("A0 实际消耗：训练总墙钟 %.1f s，CPU 均值 %.1f%%，内存均值 %.1f%%"
                 % (cost["training_wall_s"], 100 * cost["cpu_busy_fraction_mean"],
                    cost["memory_load_percent_mean"]), fontsize=12)
    fig.text(0.01, 0.01,
             "资源数据来源 training/a0_resource.jsonl（host-wide CPU 与物理内存占用），"
             "不是单进程占用。", fontsize=8.5, color="#444444")
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))
    fig.savefig(FIG / "a0_cost_and_resources.png")
    plt.close(fig)


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    metrics = load_metrics()
    result = load_result()
    fig_main(metrics)
    fig_condition_effect(metrics)
    fig_meta_effect(metrics)
    fig_cost(metrics, result)
    rows = []
    data_test = mean(metrics, "test")
    data_val = mean(metrics, "val")
    for arm in ARM_LABEL:
        for k in (0, 1, 3):
            rows.append({"arm": arm, "k": k,
                         "val_mean_mae_n": round(data_test and data_val.get((arm, k), (0, 0))[0], 3),
                         "test_mean_mae_n": round(data_test.get((arm, k), (0, 0))[0], 3),
                         "n": data_test.get((arm, k), (0, 0))[1]})
    with open(FIG / "figure_data.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["arm", "k", "val_mean_mae_n",
                                                    "test_mean_mae_n", "n"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(json.dumps({"font": FONT, "figures": sorted(p.name for p in FIG.glob("*.png"))},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
