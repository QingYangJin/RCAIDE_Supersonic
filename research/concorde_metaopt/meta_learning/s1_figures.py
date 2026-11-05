"""P4 路线A S1 规范图生成（A6 实现）。

合同依据：
- docs/planning/p4_route_a_s1_execution_plan_20261105.md（v1.0，§8 图清单：固定 7 个键名）
- docs/planning/p4_route_a_s1_statistical_plan_20261105.md（v1.1）

边界（硬性）：
- 只读取 s1_analysis 产出的 aggregate 与可选日志，不执行 runner / BO / 真实求解器；
- 无网络、无物理调用；固定绘图参数，同一输入产出确定性的 PNG；
- 缺失输入不得伪造曲线：对应图键写 NOT_RUN / NOT_APPLICABLE 并给出原因；
- 图面文字使用英文，避免中文字体缺失导致的乱码/警告。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from .s1_analysis import (
    ARM_IDS,
    COMPARISONS,
    FIGURE_KEYS,
    INFERENCE_KS,
    MAIN_SPLIT,
    PRIMARY_ENDPOINTS,
    S1_FIGURE_STATUS_SCHEMA_VERSION,
)

STATUS_NOT_RUN = "NOT_RUN"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
FIGURE_FILENAMES = {key: key + ".png" for key in FIGURE_KEYS}

FIGURE_TITLES = {
    "fig1_meta_training_loss": "fig1: meta-training loss",
    "fig2_k_shot_adaptation": "fig2: K-shot adaptation (C1 treatment vs reference)",
    "fig3_feasible_rate": "fig3: feasible hit rate vs K (B=64)",
    "fig4_equal_budget_gap": "fig4: equal-budget gap to reference (B=64, meta_test)",
    "fig5_fairness_audit": "fig5: fairness audit (equal billable budget)",
    "fig6_k_sweep_delta": "fig6: K sweep of paired mean differences (C1, meta_test)",
    "fig7_negative_control_and_determinism": "fig7: negative control and determinism",
}

# 固定绘图风格（确定性；不依赖用户 matplotlibrc）。
PLOT_STYLE = {
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "legend.fontsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "figure.dpi": 120,
    "savefig.dpi": 150,
    "axes.grid": True,
    "grid.alpha": 0.30,
    "axes.spines.top": False,
    "axes.spines.right": False,
}

ARM_COLORS = {
    "RAND-BO": "#4C78A8",
    "PRETRAIN-KSHOT-BO": "#F58518",
    "FOMAML-ZERO-BO": "#54A24B",
    "FOMAML-KSHOT-BO": "#E45756",
    "DE": "#72B7B2",
}
BUDGET_STYLES = {64: "-", 128: "--"}
C1 = next((item for item in COMPARISONS if item["id"] == "C1"), None)


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def _finite_number(value: Any) -> float | None:
    """把 JSON 数值转成有限 float；布尔、字符串、NaN/Inf 一律视为缺失。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _arm_summary_rows(aggregate: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = aggregate.get("endpoint_rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, Mapping) and row.get("row_type") == "arm_summary"]


def _comparison_rows(aggregate: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = aggregate.get("endpoint_rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, Mapping) and row.get("row_type") == "comparison"]


def _index_arm_rows(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, int, int, str, str], Mapping[str, Any]]:
    index: dict[tuple[str, int, int, str, str], Mapping[str, Any]] = {}
    for row in rows:
        try:
            key = (
                str(row["split"]),
                int(row["budget_B"]),
                int(row["K"]),
                str(row["arm"]),
                str(row["endpoint"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        index[key] = row
    return index


def _arm_mean(
    index: Mapping[tuple[str, int, int, str, str], Mapping[str, Any]],
    *,
    split: str,
    budget_B: int,
    K: int,
    arm: str,
    endpoint: str,
) -> float | None:
    row = index.get((split, int(budget_B), int(K), arm, endpoint))
    return None if row is None else _finite_number(row.get("mean"))


def _save(fig: Any, path: Path) -> bool:
    """保存图片并校验非空；失败返回 False（由调用方写 NOT_RUN）。"""
    fig.savefig(path, dpi=150, bbox_inches="tight", metadata={"Software": None})
    return path.exists() and path.stat().st_size > 0


# ---------------------------------------------------------------------------
# fig1：meta 训练损失（可选输入）
# ---------------------------------------------------------------------------
_LOSS_KEYS = ("loss", "train_loss", "meta_train_loss", "mean_loss", "training_loss", "value")
_STEP_KEYS = ("step", "epoch", "iteration", "index", "iter")


def _series_from_items(items: Any) -> tuple[list[float], list[float]] | None:
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)) or not items:
        return None
    if all(_finite_number(item) is not None for item in items):
        values = [float(item) for item in items]
        return [float(index) for index in range(1, len(values) + 1)], values
    if all(isinstance(item, Mapping) for item in items):
        loss_key = None
        for candidate in _LOSS_KEYS:
            if all(_finite_number(item.get(candidate)) is not None for item in items):
                loss_key = candidate
                break
        if loss_key is None:
            return None
        step_key = None
        for candidate in _STEP_KEYS:
            if all(_finite_number(item.get(candidate)) is not None for item in items):
                step_key = candidate
                break
        values = [float(item[loss_key]) for item in items]
        if step_key is None:
            steps = [float(index) for index in range(1, len(values) + 1)]
        else:
            steps = [float(item[step_key]) for item in items]
        return steps, values
    return None


def _series_from_mapping(payload: Mapping[str, Any]) -> tuple[list[float], list[float]] | None:
    for key in ("history", "records", "log", "series", "losses", "loss", "meta_train_loss", "train_loss"):
        if key in payload:
            parsed = _series_from_items(payload[key])
            if parsed is not None:
                return parsed
    losses: list[float] | None = None
    for key in _LOSS_KEYS:
        candidate = payload.get(key)
        if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)) and candidate:
            converted = [_finite_number(value) for value in candidate]
            if all(value is not None for value in converted):
                losses = [float(value) for value in converted]  # type: ignore[arg-type]
                break
    if losses is None:
        return None
    steps: list[float] | None = None
    for key in _STEP_KEYS:
        candidate = payload.get(key)
        if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)) and len(candidate) == len(losses):
            converted = [_finite_number(value) for value in candidate]
            if all(value is not None for value in converted):
                steps = [float(value) for value in converted]  # type: ignore[arg-type]
                break
    if steps is None:
        steps = [float(index) for index in range(1, len(losses) + 1)]
    return steps, losses


def _extract_meta_loss_series(payload: Any) -> dict[str, tuple[list[float], list[float]]] | None:
    """从多种合理日志结构提取损失曲线；无法解析返回 None（不得伪造数据）。"""
    if payload is None:
        return None
    if isinstance(payload, Mapping) and "train" in payload:
        series: dict[str, tuple[list[float], list[float]]] = {}
        for key in ("train", "validation", "val"):
            if key in payload:
                parsed = _series_from_items(payload[key])
                if parsed is not None:
                    series[key] = parsed
        if series:
            return series
    if isinstance(payload, Mapping):
        parsed = _series_from_mapping(payload)
    else:
        parsed = _series_from_items(payload)
    if parsed is None:
        return None
    return {"loss": parsed}


def _render_meta_training_loss(aggregate: Mapping[str, Any], path: Path, meta_training_log: Any) -> tuple[str, str]:
    series = _extract_meta_loss_series(meta_training_log)
    if not series:
        return STATUS_NOT_RUN, "未提供可解析的 meta_training_log（fig1 为可选图）"
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    try:
        for label, (steps, losses) in series.items():
            minimum = min(len(steps), len(losses))
            if minimum < 2:
                continue
            ax.plot(steps[:minimum], losses[:minimum], marker="o", markersize=2.5, linewidth=1.4, label=label)
        if not ax.lines:
            return STATUS_NOT_RUN, "meta_training_log 中损失点少于 2 个"
        ax.set_title(FIGURE_TITLES["fig1_meta_training_loss"])
        ax.set_xlabel("step / epoch")
        ax.set_ylabel("loss")
        ax.legend(loc="best", frameon=False)
        if not _save(fig, path):
            return STATUS_NOT_RUN, "图片写入失败"
        return "OK", "由可选 meta_training_log 渲染"
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# fig2：K-shot 适配（C1 处理臂 vs 参考臂）
# ---------------------------------------------------------------------------
def _render_k_shot_adaptation(aggregate: Mapping[str, Any], path: Path) -> tuple[str, str]:
    if C1 is None:
        return STATUS_NOT_APPLICABLE, "缺少 C1 比较定义"
    index = _index_arm_rows(_arm_summary_rows(aggregate))
    treatments = [index[("meta_test", budget, K, C1["arm"], endpoint)] for budget in (64, 128) for K in INFERENCE_KS for endpoint in ("best_feasible_value",) if ("meta_test", budget, K, C1["arm"], endpoint) in index]
    if not treatments:
        return STATUS_NOT_APPLICABLE, "meta_test 无 K>0 的 C1 层"
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    try:
        plotted = False
        for budget in (64, 128):
            for arm, style, prefix in (
                (C1["arm"], "-", "treatment"),
                (C1["reference"], "--", "reference"),
            ):
                xs: list[float] = []
                ys: list[float] = []
                for K in INFERENCE_KS:
                    value = _arm_mean(
                        index,
                        split=MAIN_SPLIT,
                        budget_B=budget,
                        K=K,
                        arm=arm,
                        endpoint="best_feasible_value",
                    )
                    if value is not None:
                        xs.append(float(K))
                        ys.append(value)
                if not xs:
                    continue
                ax.plot(
                    xs,
                    ys,
                    marker="o",
                    linestyle=BUDGET_STYLES[budget],
                    color=ARM_COLORS.get(arm, "#333333"),
                    label=prefix + " " + arm + " (B=" + str(budget) + ")",
                )
                plotted = True
        if not plotted:
            return STATUS_NOT_RUN, "全部主层取值为 null，无法绘制 fig2"
        ax.set_title(FIGURE_TITLES["fig2_k_shot_adaptation"])
        ax.set_xlabel("K (support examples)")
        ax.set_ylabel("mean best_feasible_value (lower is better)")
        ax.set_xticks([float(K) for K in INFERENCE_KS])
        ax.legend(loc="best", frameon=False)
        if not _save(fig, path):
            return STATUS_NOT_RUN, "图片写入失败"
        return "OK", "使用 meta_test 任务级均值"
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# fig3：可行命中率 vs K（5 臂，B=64）
# ---------------------------------------------------------------------------
def _render_feasible_rate(aggregate: Mapping[str, Any], path: Path) -> tuple[str, str]:
    index = _index_arm_rows(_arm_summary_rows(aggregate))
    budget = 64
    ks = [K for K in (0, 1, 3, 5) if any(_arm_mean(index, split=MAIN_SPLIT, budget_B=budget, K=K, arm=arm, endpoint="feasible_hit_rate") is not None for arm in ARM_IDS)]
    if not ks:
        return STATUS_NOT_RUN, "B=64 无任何非 null 的 feasible_hit_rate"
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    try:
        for arm in ARM_IDS:
            xs: list[float] = []
            ys: list[float] = []
            for K in ks:
                value = _arm_mean(index, split=MAIN_SPLIT, budget_B=budget, K=K, arm=arm, endpoint="feasible_hit_rate")
                if value is not None:
                    xs.append(float(K))
                    ys.append(value)
            if xs:
                label = arm + (" (K=0 CLONE, descriptive)" if arm == "FOMAML-KSHOT-BO" else "")
                ax.plot(xs, ys, marker="o", color=ARM_COLORS.get(arm, "#333333"), label=label)
        ax.set_title(FIGURE_TITLES["fig3_feasible_rate"])
        ax.set_xlabel("K (support examples)")
        ax.set_ylabel("mean feasible hit rate (higher is better)")
        ax.set_xticks([float(K) for K in ks])
        ax.legend(loc="best", frameon=False)
        if not _save(fig, path):
            return STATUS_NOT_RUN, "图片写入失败"
        return "OK", "5 臂 x B=64 的任务级均值"
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# fig4：等预算 gap（B=64，meta_test）
# ---------------------------------------------------------------------------
def _render_equal_budget_gap(aggregate: Mapping[str, Any], path: Path) -> tuple[str, str]:
    if C1 is None:
        return STATUS_NOT_APPLICABLE, "缺少 C1 比较定义"
    index = _index_arm_rows(_arm_summary_rows(aggregate))
    budget = 64
    ks = [K for K in (3, 5) if (
        _arm_mean(index, split=MAIN_SPLIT, budget_B=budget, K=K, arm=C1["arm"], endpoint="gap_to_reference") is not None
        or _arm_mean(index, split=MAIN_SPLIT, budget_B=budget, K=K, arm=C1["reference"], endpoint="gap_to_reference") is not None
    )]
    if not ks:
        return STATUS_NOT_RUN, "B=64 无任何非 null 的 gap_to_reference"
    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    try:
        width = 0.36
        for offset, arm, color in ((-0.18, C1["arm"], ARM_COLORS.get(C1["arm"], "#333333")), (0.18, C1["reference"], "#9E9E9E")):
            xs: list[float] = []
            ys: list[float] = []
            for position, K in enumerate(ks):
                value = _arm_mean(index, split=MAIN_SPLIT, budget_B=budget, K=K, arm=arm, endpoint="gap_to_reference")
                if value is None:
                    continue
                xs.append(float(position) + offset)
                ys.append(value)
                ax.annotate(("%.4g" % value), (float(position) + offset, value), textcoords="offset points", xytext=(0, 3), ha="center", fontsize=7)
            if xs:
                ax.bar(xs, ys, width=width, color=color, label=arm)
        ax.set_xticks([float(position) for position in range(len(ks))])
        ax.set_xticklabels(["K=" + str(K) for K in ks])
        ax.set_title(FIGURE_TITLES["fig4_equal_budget_gap"])
        ax.set_ylabel("mean gap_to_reference (lower is better)")
        ax.legend(loc="best", frameon=False)
        if not _save(fig, path):
            return STATUS_NOT_RUN, "图片写入失败"
        return "OK", "B=64 主确认层，任务级均值"
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# fig5：公平性审计（等 billable 预算）
# ---------------------------------------------------------------------------
def _render_fairness_audit(aggregate: Mapping[str, Any], path: Path) -> tuple[str, str]:
    rows = aggregate.get("budget_audit")
    if not isinstance(rows, list):
        return STATUS_NOT_RUN, "aggregate 缺少 budget_audit"
    main_rows = [row for row in rows if isinstance(row, Mapping) and row.get("split") == MAIN_SPLIT and int(row.get("budget_B", -1)) == 64]
    if not main_rows:
        return STATUS_NOT_RUN, "budget_audit 无 meta_test/B=64 行"
    ks = sorted({int(row.get("K", 0)) for row in main_rows})
    arms = [arm for arm in ARM_IDS if any(str(row.get("arm")) == arm for row in main_rows)]
    if not arms:
        return STATUS_NOT_RUN, "budget_audit 无已知臂"
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    try:
        width = 0.8 / max(len(ks), 1)
        for index, K in enumerate(ks):
            xs: list[float] = []
            ys: list[float] = []
            for position, arm in enumerate(arms):
                match = [row for row in main_rows if str(row.get("arm")) == arm and int(row.get("K", 0)) == K]
                if not match:
                    continue
                xs.append(float(position) - 0.4 + width / 2.0 + index * width)
                ys.append(sum(int(row.get("n_ok", 0)) for row in match))
            if xs:
                ax.bar(xs, ys, width=width, label="K=" + str(K), color=plt.cm.viridis((index + 1) / (len(ks) + 1.0)))
        failures = sum(int(row.get("n_failed", 0)) for row in main_rows)
        clones = sum(int(row.get("n_clone", 0)) for row in main_rows)
        ax.set_xticks([float(position) for position in range(len(arms))])
        ax.set_xticklabels(arms, rotation=15, ha="right")
        ax.set_ylabel("OK runs (billable budget B=64)")
        ax.set_title(FIGURE_TITLES["fig5_fairness_audit"])
        ax.legend(loc="best", frameon=False)
        ax.text(
            0.01,
            0.99,
            "failed=" + str(failures) + ", K=0 clones=" + str(clones) + "\neach OK run billable_evals == B = 64",
            transform=ax.transAxes,
            va="top",
            fontsize=7,
        )
        if not _save(fig, path):
            return STATUS_NOT_RUN, "图片写入失败"
        return "OK", "budget_audit 的 OK 运行计数；预算偏移已在记录校验阶段拒绝"
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# fig6：K 扫描的配对均值差（C1，4 主端点）
# ---------------------------------------------------------------------------
def _render_k_sweep_delta(aggregate: Mapping[str, Any], path: Path) -> tuple[str, str]:
    rows = [
        row
        for row in _comparison_rows(aggregate)
        if str(row.get("comparison_id")) == "C1" and row.get("split") == MAIN_SPLIT
    ]
    if not rows:
        return STATUS_NOT_APPLICABLE, "meta_test 无 C1 比较行"
    index: dict[tuple[int, int, str], Mapping[str, Any]] = {}
    for row in rows:
        try:
            index[(int(row["budget_B"]), int(row["K"]), str(row["endpoint"]))] = row
        except (KeyError, TypeError, ValueError):
            continue
    endpoints = [endpoint for endpoint in PRIMARY_ENDPOINTS]
    fig, axes = plt.subplots(2, 2, figsize=(10.0, 6.4), squeeze=False)
    plotted = 0
    try:
        for position, endpoint in enumerate(endpoints):
            ax = axes[position // 2][position % 2]
            for budget in (64, 128):
                xs: list[float] = []
                ys: list[float] = []
                lows: list[float] = []
                highs: list[float] = []
                for K in INFERENCE_KS:
                    row = index.get((budget, K, endpoint))
                    if row is None:
                        continue
                    mean_difference = _finite_number(row.get("mean_difference"))
                    if mean_difference is None:
                        continue
                    xs.append(float(K))
                    ys.append(mean_difference)
                    low = _finite_number(row.get("ci_low"))
                    high = _finite_number(row.get("ci_high"))
                    lows.append(mean_difference if low is None else low)
                    highs.append(mean_difference if high is None else high)
                if not xs:
                    continue
                lower = [max(0.0, value - base) for value, base in zip(ys, lows)]
                upper = [max(0.0, base - value) for value, base in zip(ys, highs)]
                ax.errorbar(
                    xs,
                    ys,
                    yerr=[lower, upper],
                    marker="o",
                    linestyle=BUDGET_STYLES[budget],
                    color="#4C78A8" if budget == 64 else "#F58518",
                    capsize=3,
                    linewidth=1.3,
                    label="B=" + str(budget),
                )
                plotted += 1
            ax.axhline(0.0, color="#666666", linewidth=0.9)
            ax.set_title(endpoint)
            ax.set_xlabel("K")
            ax.set_ylabel("mean paired difference")
            ax.set_xticks([float(K) for K in INFERENCE_KS])
            ax.legend(loc="best", frameon=False)
        if plotted == 0:
            return STATUS_NOT_RUN, "4 个主端点均无可用配对均值差"
        fig.suptitle(FIGURE_TITLES["fig6_k_sweep_delta"])
        fig.tight_layout()
        if not _save(fig, path):
            return STATUS_NOT_RUN, "图片写入失败"
        return "OK", "C1 配对均值差 + 百分位 bootstrap 95% CI"
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# fig7：负控与确定性
# ---------------------------------------------------------------------------
def _render_negative_control(aggregate: Mapping[str, Any], path: Path) -> tuple[str, str]:
    payload = aggregate.get("negative_controls")
    if not isinstance(payload, Mapping):
        return STATUS_NOT_RUN, "aggregate 缺少 negative_controls"
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        return STATUS_NOT_RUN, "negative_controls 无检查行"
    split_rows = [row for row in rows if isinstance(row, Mapping) and row.get("check") == "negative_control_split"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.2, 4.4), gridspec_kw={"width_ratios": [1.65, 1.0]})
    try:
        if split_rows:
            budget = 64
            K = 3
            endpoint = "best_feasible_value"
            selected = [
                row
                for row in split_rows
                if int(row.get("budget_B", -1)) == budget and int(row.get("K", -1)) == K and str(row.get("endpoint")) == endpoint
            ]
            if selected:
                labels: list[str] = []
                values: list[float] = []
                for row in sorted(selected, key=lambda item: str(item.get("comparison_id"))):
                    improvement = _finite_number(row.get("improvement"))
                    labels.append(str(row.get("comparison_id")))
                    values.append(0.0 if improvement is None else improvement)
                ax1.bar([float(position) for position in range(len(labels))], values, color="#4C78A8")
                ax1.axhline(0.0, color="#666666", linewidth=0.9)
                ax1.set_xticks([float(position) for position in range(len(labels))])
                ax1.set_xticklabels(labels)
                ax1.set_title("negative control: " + endpoint + " (B=64, K=3)")
                ax1.set_ylabel("mean improvement (positive = treatment better)")
            else:
                ax1.text(0.5, 0.5, "negative_control split: no selected rows", ha="center", va="center", transform=ax1.transAxes)
        else:
            ax1.text(0.5, 0.5, "negative_control split: NOT_AVAILABLE", ha="center", va="center", transform=ax1.transAxes)
        determinism = payload.get("determinism")
        clone = payload.get("clone_k0")
        lines = [
            "overall: " + str(payload.get("status")),
            "n_checks: " + str(payload.get("n_checks")),
            "n_fail: " + str(payload.get("n_fail")),
            "",
            "determinism: " + str(determinism.get("status") if isinstance(determinism, Mapping) else "NOT_AVAILABLE"),
        ]
        # 图内文本只用 ASCII 状态码；中文 note 仅保留在 figure_status.json，避免字体缺字。
        lines.append("")
        lines.append("clone K=0: " + str(clone.get("status") if isinstance(clone, Mapping) else "NOT_AVAILABLE"))
        if isinstance(clone, Mapping):
            lines.append("  checked pairs: " + str(clone.get("checked")))
        ax2.axis("off")
        ax2.text(0.0, 1.0, "\n".join(lines), va="top", ha="left", fontsize=8, transform=ax2.transAxes)
        ax2.set_title("negative controls & determinism status")
        fig.suptitle(FIGURE_TITLES["fig7_negative_control_and_determinism"])
        fig.tight_layout()
        if not _save(fig, path):
            return STATUS_NOT_RUN, "图片写入失败"
        return "OK", "负控 split/CLONE/确定性状态"
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def render_figures(
    aggregate: Mapping[str, Any],
    output_dir: str | Path,
    *,
    meta_training_log: Any = None,
) -> dict[str, Any]:
    """渲染 7 张规范图，返回 figure_status payload（可直接写 figure_status.json）。

    - aggregate：s1_analysis.run_s1_analysis 返回的聚合 dict（只读）；
    - meta_training_log：可选 meta 训练日志（fig1）；缺失时 fig1 = NOT_RUN；
    - 任一图缺失输入 -> 对应键写 NOT_RUN/NOT_APPLICABLE，其余图照常生成；
    - 不写任何绝对路径：仅记录文件名与原因。
    """
    if not isinstance(aggregate, Mapping):
        raise TypeError("aggregate 必须是 Mapping")
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    figures: dict[str, str] = {key: STATUS_NOT_RUN for key in FIGURE_KEYS}
    notes: dict[str, str] = {}
    renderers = {
        "fig2_k_shot_adaptation": _render_k_shot_adaptation,
        "fig3_feasible_rate": _render_feasible_rate,
        "fig4_equal_budget_gap": _render_equal_budget_gap,
        "fig5_fairness_audit": _render_fairness_audit,
        "fig6_k_sweep_delta": _render_k_sweep_delta,
        "fig7_negative_control_and_determinism": _render_negative_control,
    }
    with matplotlib.rc_context(PLOT_STYLE):
        status, note = _render_meta_training_loss(aggregate, target / FIGURE_FILENAMES["fig1_meta_training_loss"], meta_training_log)
        figures["fig1_meta_training_loss"] = FIGURE_FILENAMES["fig1_meta_training_loss"] if status == "OK" else status
        notes["fig1_meta_training_loss"] = note
        for key, renderer in renderers.items():
            filename = FIGURE_FILENAMES[key]
            path = target / filename
            try:
                status, note = renderer(aggregate, path)
            except Exception as exc:  # 图不应阻断分析结论：记录原因并继续
                status = STATUS_NOT_RUN
                note = "渲染异常：" + type(exc).__name__ + ": " + str(exc)[:180]
                if path.exists():
                    path.unlink()
            figures[key] = filename if status == "OK" else status
            notes[key] = note
    generated = sorted(filename for key, filename in FIGURE_FILENAMES.items() if figures[key] == filename)
    status_payload: dict[str, Any] = {
        "schema_version": S1_FIGURE_STATUS_SCHEMA_VERSION,
        "figures": figures,
        "notes": notes,
        "generated": generated,
        "output_dir_name": target.name,
    }
    return status_payload


__all__ = [
    "FIGURE_FILENAMES",
    "FIGURE_TITLES",
    "STATUS_NOT_APPLICABLE",
    "STATUS_NOT_RUN",
    "render_figures",
]
