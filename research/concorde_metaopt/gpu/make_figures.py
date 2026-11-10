"""D-NEXT-001 A4｜G1 基准中文图（读取 run 目录的 summary.json / metrics.csv）。

图 1：三路配置在 FOMAML 预训练 / K-shot 适应 / 代理批量打分上的墙钟（对数坐标）。
图 2：相对 CPU-FP64 的墙钟加速比（<1 表示更慢，如实呈现）。
图 3：数值精度：元梯度相对误差与元验证 QueryRMSE。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

CONFIG_LABELS = {
    "cpu-fp64": "CPU-FP64",
    "cuda-fp64": "GPU-FP64",
    "cuda-fp32": "GPU-FP32",
}
WORKLOAD_LABELS = {
    "fomaml_pretrain": "FOMAML 元预训练",
    "kshot_adapt": "K-shot 适应",
    "surrogate_batch_score": "代理批量打分",
    "gemm_probe": "GEMM 吞吐探针",
}
COLORS = {"cpu-fp64": "#4C78A8", "cuda-fp64": "#F58518", "cuda-fp32": "#54A24B"}


def make_figures(run_dir: Path | str) -> list[str]:
    run_dir = Path(run_dir)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    results: dict[str, Any] = summary.get("results", {})
    configs = [name for name in results if name in CONFIG_LABELS]
    if not configs:
        raise RuntimeError("summary.json 中没有可绘制的配置")

    figures = run_dir / "figures"
    figures.mkdir(exist_ok=True)
    produced: list[str] = []

    # 图 1：墙钟
    workloads = ["fomaml_pretrain", "kshot_adapt", "surrogate_batch_score", "gemm_probe"]
    figure, axis = plt.subplots(figsize=(10.5, 5.6))
    width = 0.8 / max(len(configs), 1)
    for index, config in enumerate(configs):
        walls = []
        for workload in workloads:
            block = results[config]["workloads"].get(workload)
            walls.append(block["wall_s_median"] if block else float("nan"))
        positions = [position + index * width for position in range(len(workloads))]
        axis.bar(positions, walls, width=width, label=CONFIG_LABELS[config], color=COLORS.get(config, "#999999"))
        for position, wall in zip(positions, walls):
            if wall == wall and wall > 0:
                axis.text(position, wall, f"{wall:.3g}s", ha="center", va="bottom", fontsize=7, rotation=90)
    axis.set_yscale("log")
    axis.set_xticks([position + width * (len(configs) - 1) / 2 for position in range(len(workloads))])
    axis.set_xticklabels([WORKLOAD_LABELS[name] for name in workloads])
    axis.set_ylabel("墙钟中位数（秒，对数坐标）")
    axis.set_title("图1  12 维合成 FOMAML 任务的墙钟对比（同步计时，重复≥3 次）")
    axis.legend()
    axis.grid(True, axis="y", which="both", alpha=0.3)
    figure.tight_layout()
    path = figures / "fig1_walltime.png"
    figure.savefig(path, dpi=160)
    plt.close(figure)
    produced.append(str(path))

    # 图 2：相对 CPU-FP64 加速比
    if "cpu-fp64" in results:
        reference = results["cpu-fp64"]["workloads"]
        figure, axis = plt.subplots(figsize=(9.6, 5.0))
        labels: list[str] = []
        values: list[float] = []
        colors: list[str] = []
        for config in configs:
            if config == "cpu-fp64":
                continue
            for workload in workloads:
                block = results[config]["workloads"].get(workload)
                ref_block = reference.get(workload)
                if not block or not ref_block or ref_block["wall_s_median"] <= 0:
                    continue
                labels.append(f"{CONFIG_LABELS[config]}\n{WORKLOAD_LABELS[workload]}")
                values.append(ref_block["wall_s_median"] / block["wall_s_median"])
                colors.append(COLORS.get(config, "#999999"))
        if values:
            positions = range(len(values))
            axis.barh(list(positions), values, color=colors)
            axis.axvline(1.0, color="#333333", linestyle="--", linewidth=1)
            axis.set_yticks(list(positions))
            axis.set_yticklabels(labels, fontsize=8)
            axis.set_xlabel("相对 CPU-FP64 的加速比（>1 更快，<1 更慢）")
            axis.set_title("图2  计算设备加速比（合成任务；GPU 更快不等于算法更好）")
            for position, value in zip(positions, values):
                axis.text(value, position, f"{value:.2f}x", va="center", ha="left", fontsize=8)
            axis.grid(True, axis="x", alpha=0.3)
            figure.tight_layout()
            path = figures / "fig2_speedup.png"
            figure.savefig(path, dpi=160)
            plt.close(figure)
            produced.append(str(path))

    # 图 3：精度
    figure, axis = plt.subplots(figsize=(9.6, 4.8))
    names = []
    gradient_errors = []
    query_rmse = []
    for config in configs:
        names.append(CONFIG_LABELS[config])
        grad = summary.get("gradient_errors", {}).get(config)
        gradient_errors.append(grad["rel_l2"] if grad else 0.0)
        pretrain = results[config]["workloads"].get("fomaml_pretrain")
        query_rmse.append(pretrain["query_rmse_median"] if pretrain else float("nan"))
    positions = range(len(names))
    axis.bar([position - 0.2 for position in positions], gradient_errors, width=0.4, label="元梯度相对 CPU-FP64 的 L2 误差", color="#E45756")
    axis.bar([position + 0.2 for position in positions], query_rmse, width=0.4, label="元验证 QueryRMSE", color="#72B7B2")
    axis.set_xticks(list(positions))
    axis.set_xticklabels(names)
    axis.set_yscale("log")
    axis.set_title("图3  数值精度：元梯度误差（参考=CPU-FP64）与元验证 QueryRMSE")
    axis.legend()
    axis.grid(True, axis="y", which="both", alpha=0.3)
    figure.tight_layout()
    path = figures / "fig3_precision.png"
    figure.savefig(path, dpi=160)
    plt.close(figure)
    produced.append(str(path))

    (figures / "figure_index.json").write_text(
        json.dumps({"figures": [Path(item).name for item in produced]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return produced


if __name__ == "__main__":
    import sys

    print(make_figures(sys.argv[1] if len(sys.argv) > 1 else "."))
