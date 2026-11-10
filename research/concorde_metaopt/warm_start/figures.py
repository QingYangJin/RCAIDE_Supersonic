"""路线A 合成实验的中文图（matplotlib，physical_call_count=0）。

读取 optimization_runs/dnext001-a-warmstart-* 下的 metrics.csv 与 cell_summary.csv，
生成 figures/*.png。无数据的 cell 不画假点，直接留空并在图注写 NOT_RUN。
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

SOURCE_LABELS = {
    "random": "随机（对照）",
    "zero_shot_surrogate": "零样本代理",
    "pretrain_supervised": "监督预训练",
    "fomaml_kshot": "FOMAML K-shot",
}
BACKEND_LABELS = {"bo": "约束BO", "de": "差分进化DE", "pso": "粒子群PSO"}
BACKEND_STYLES = {
    "bo": {"marker": "o", "linestyle": "-"},
    "de": {"marker": "s", "linestyle": "--"},
    "pso": {"marker": "^", "linestyle": "-."},
}
COLORS = {"random": "#7f7f7f", "zero_shot_surrogate": "#1f77b4", "pretrain_supervised": "#2ca02c", "fomaml_kshot": "#d62728"}
FOOTNOTE = "数据来源：合成解析真值（SYNTHETIC_ANALOGUE），physical_call_count=0；单 seed，仅供方向性参考。"


def _read_csv(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(value: Any) -> Optional[float]:
    if value is None or value == "" or value == "None":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: Sequence[Optional[float]]) -> Optional[float]:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return float(np.mean(clean))


def _latest_run_dir(base: str) -> str:
    pattern = os.path.join(base, "dnext001-a-warmstart-*")
    candidates = [path for path in glob.glob(pattern) if os.path.isdir(path)]
    if not candidates:
        raise FileNotFoundError("未找到 run 目录：%s" % pattern)
    return sorted(candidates)[-1]


def _filter(rows: Sequence[Dict[str, str]], **conditions: Any) -> List[Dict[str, str]]:
    result = []
    for row in rows:
        matched = True
        for key, expected in conditions.items():
            actual = row.get(key)
            if isinstance(expected, (int, float)) and not isinstance(expected, bool):
                value = _float(actual)
                if value is None or abs(value - float(expected)) > 1e-9:
                    matched = False
                    break
            elif str(actual) != str(expected):
                matched = False
                break
        if matched:
            result.append(row)
    return result


def figure_matrix_overview(rows: Sequence[Dict[str, str]], output: str) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(12.5, 9.0))
    ax1, ax2, ax3, ax4 = axes.ravel()

    budgets = [16, 32, 64, 128]
    for backend in ("bo", "de", "pso"):
        for source, alpha, label_suffix in (("random", 0.45, "对照"), ("fomaml_kshot", 1.0, "FOMAML")):
            values = []
            for budget in budgets:
                subset = [
                    _float(row["first_feasible_eval"])
                    for row in rows
                    if row["backend"] == backend
                    and row["source"] == source
                    and int(float(row["budget_B"])) == budget
                    and float(row["K"]) in (0.0, 5.0)
                    and abs(float(row["diversity_weight_rho"])) < 1e-9
                ]
                values.append(_mean(subset))
            xs = [budget for budget, value in zip(budgets, values) if value is not None]
            ys = [value for value in values if value is not None]
            if xs:
                ax1.plot(
                    xs,
                    ys,
                    color=COLORS[source],
                    alpha=alpha,
                    linewidth=1.8 if source == "fomaml_kshot" else 1.2,
                    label="%s-%s" % (BACKEND_LABELS[backend], label_suffix),
                    **BACKEND_STYLES[backend],
                )
    ax1.set_xlabel("真实评价预算 B")
    ax1.set_ylabel("首次可行评价序号（均值，含支撑观测）")
    ax1.set_title("首次可行评价 vs 预算（K∈{0,5}，ρ=0）")
    ax1.set_xticks(budgets)
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=7, ncol=2)

    ks = [0, 1, 3, 5]
    for backend in ("bo", "de", "pso"):
        values = []
        for k in ks:
            subset = [
                _float(row["gap_to_reference"])
                for row in rows
                if row["backend"] == backend
                and row["source"] == "fomaml_kshot"
                and int(float(row["budget_B"])) == 64
                and int(float(row["K"])) == k
                and abs(float(row["diversity_weight_rho"])) < 1e-9
            ]
            values.append(_mean(subset))
        xs = [k for k, value in zip(ks, values) if value is not None]
        ys = [value for value in values if value is not None]
        if xs:
            ax2.plot(xs, ys, color="#333333", label=BACKEND_LABELS[backend], **BACKEND_STYLES[backend])
    ax2.set_xlabel("K-shot 支撑观测数 K")
    ax2.set_ylabel("相对参考解 gap（均值，越小越好）")
    ax2.set_title("FOMAML 热启动质量 vs K（B=64，ρ=0）")
    ax2.set_xticks(ks)
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8)

    sources = ["random", "zero_shot_surrogate", "pretrain_supervised", "fomaml_kshot"]
    positions = np.arange(len(sources))
    width = 0.26
    for offset, backend in enumerate(("bo", "de", "pso")):
        values = []
        for source in sources:
            subset = [
                _float(row["gap_to_reference"])
                for row in rows
                if row["backend"] == backend
                and row["source"] == source
                and int(float(row["budget_B"])) == 64
                and int(float(row["K"])) == 3
                and abs(float(row["diversity_weight_rho"])) < 1e-9
            ]
            values.append(_mean(subset))
        heights = [value if value is not None else 0.0 for value in values]
        ax3.bar(positions + (offset - 1) * width, heights, width, label=BACKEND_LABELS[backend])
        for position, value in zip(positions + (offset - 1) * width, values):
            if value is None:
                ax3.text(position, 0.01, "NOT_RUN", rotation=90, fontsize=6, ha="center")
    ax3.set_xticks(positions)
    ax3.set_xticklabels([SOURCE_LABELS[item] for item in sources], fontsize=8)
    ax3.set_ylabel("相对参考解 gap（均值，越小越好）")
    ax3.set_title("四种采样来源对比（B=64，K=3，ρ=0）")
    ax3.grid(alpha=0.3, axis="y")
    ax3.legend(fontsize=8)

    rhos = [0.0, 0.25, 0.5, 0.75]
    for backend in ("de", "pso"):
        values = []
        for rho in rhos:
            subset = [
                _float(row["diversity"])
                for row in rows
                if row["backend"] == backend
                and row["source"] == "fomaml_kshot"
                and int(float(row["budget_B"])) == 64
                and int(float(row["K"])) == 3
                and abs(float(row["diversity_weight_rho"]) - rho) < 1e-9
            ]
            values.append(_mean(subset))
        xs = [rho for rho, value in zip(rhos, values) if value is not None]
        ys = [value for value in values if value is not None]
        if xs:
            ax4.plot(xs, ys, color="#333333", label=BACKEND_LABELS[backend], **BACKEND_STYLES[backend])
    ax4.set_xlabel("多样性权重 ρ")
    ax4.set_ylabel("最终种群多样性（0-1 归一化成对距离）")
    ax4.set_title("最终种群多样性 vs ρ（FOMAML，B=64，K=3）")
    ax4.set_xticks(rhos)
    ax4.grid(alpha=0.3)
    ax4.legend(fontsize=8)

    figure.suptitle("路线A：优化器无关热启动合成矩阵总览", fontsize=13)
    figure.text(0.01, 0.005, FOOTNOTE, fontsize=7.5, color="#555555")
    figure.tight_layout(rect=(0, 0.02, 1, 0.97))
    figure.savefig(output, dpi=160)
    plt.close(figure)


def figure_anytime(rows: Sequence[Dict[str, str]], output: str) -> None:
    figure, axes = plt.subplots(1, 3, figsize=(14.0, 4.4), sharey=False)
    for axis, backend in zip(axes, ("bo", "de", "pso")):
        for source, alpha in (("random", 0.45), ("fomaml_kshot", 1.0)):
            xs: List[int] = []
            ys: List[float] = []
            for budget in (16, 32, 64, 128):
                key = "anytime_best_feasible_%d" % budget
                subset = [
                    _float(row.get(key))
                    for row in rows
                    if row["backend"] == backend
                    and row["source"] == source
                    and int(float(row["budget_B"])) == budget
                    and float(row["K"]) in (0.0, 5.0)
                    and abs(float(row["diversity_weight_rho"])) < 1e-9
                ]
                value = _mean(subset)
                if value is not None:
                    xs.append(budget)
                    ys.append(value)
            if xs:
                axis.plot(xs, ys, color=COLORS[source], alpha=alpha, marker="o", markersize=4, label=SOURCE_LABELS[source])
        axis.set_title(BACKEND_LABELS[backend])
        axis.set_xlabel("预算截断点")
        axis.set_ylabel("截至该预算的最优可行目标值（均值）")
        axis.set_xticks([16, 32, 64, 128])
        axis.grid(alpha=0.3)
        axis.legend(fontsize=8)
    figure.suptitle("早期 anytime 性能：随机对照 vs FOMAML 热启动", fontsize=13)
    figure.text(0.01, 0.005, FOOTNOTE, fontsize=7.5, color="#555555")
    figure.tight_layout(rect=(0, 0.03, 1, 0.95))
    figure.savefig(output, dpi=160)
    plt.close(figure)


def figure_feasibility_calibration(rows: Sequence[Dict[str, str]], output: str) -> None:
    """预测可行概率 vs 真实可行率（负结果可视化）。"""
    figure, axis = plt.subplots(figsize=(6.4, 4.6))
    sources = ["zero_shot_surrogate", "pretrain_supervised", "fomaml_kshot"]
    positions = np.arange(len(sources))
    predicted: List[float] = []
    actual: List[float] = []
    for source in sources:
        subset = [
            row
            for row in rows
            if row["source"] == source
            and int(float(row["budget_B"])) == 64
            and int(float(row["K"])) == 3
            and abs(float(row["diversity_weight_rho"])) < 1e-9
        ]
        predicted.append(
            _mean([_float(row.get("proposal_predicted_feasibility_mean")) for row in subset]) or 0.0
        )
        actual_rates = []
        for row in subset:
            count = _float(row.get("proposal_true_feasible_count"))
            total = _float(row.get("proposal_n_new"))
            if count is not None and total:
                actual_rates.append(count / total)
        actual.append(_mean(actual_rates) or 0.0)
    width = 0.36
    axis.bar(positions - width / 2, predicted, width, label="代理预测可行概率（均值）", color="#1f77b4")
    axis.bar(positions + width / 2, actual, width, label="真实可行率（提议点，均值）", color="#d62728")
    axis.set_xticks(positions)
    axis.set_xticklabels([SOURCE_LABELS[item] for item in sources], fontsize=8)
    axis.set_ylabel("可行性比例")
    axis.set_title("代理可行性校准：预测高估（负结果）", fontsize=12)
    axis.set_ylim(0.0, 1.0)
    axis.grid(alpha=0.3, axis="y")
    axis.legend(fontsize=8)
    figure.text(0.01, 0.005, FOOTNOTE + " 提案点仅 4-8 个/run，真实可行率分辨率有限。", fontsize=7.5, color="#555555")
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    figure.savefig(output, dpi=160)
    plt.close(figure)


def generate(output_root: str) -> List[str]:
    metrics_path = os.path.join(output_root, "metrics.csv")
    rows = _read_csv(metrics_path)
    figures_dir = os.path.join(output_root, "figures")
    os.makedirs(figures_dir, exist_ok=True)
    outputs = [
        os.path.join(figures_dir, "fig1_matrix_overview.png"),
        os.path.join(figures_dir, "fig2_anytime.png"),
        os.path.join(figures_dir, "fig3_feasibility_calibration.png"),
    ]
    figure_matrix_overview(rows, outputs[0])
    figure_anytime(rows, outputs[1])
    figure_feasibility_calibration(rows, outputs[2])
    return outputs


def main(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="生成路线A合成实验中文图")
    parser.add_argument("--output-root", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)
    base = os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
        "research",
        "concorde_metaopt",
        "optimization_runs",
    )
    output_root = args.output_root or _latest_run_dir(base)
    outputs = generate(output_root)
    print("图已生成：")
    for path in outputs:
        print(" -", path)
    return {"output_root": output_root, "figures": outputs}


if __name__ == "__main__":
    main()
