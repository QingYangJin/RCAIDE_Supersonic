
# -*- coding: utf-8 -*-
"""P4 路线A S2 规范键图（fig1–fig9，v1.5 图合同）。

输入只来自 s2_analysis.analyze_s2_run 构建的自包含状态（state）；本模块不读取 run 原始文件、
不读 holdout、不启动任何求解器。缺数据时按 NOT_RUN / NOT_APPLICABLE 如实记录，不画伪造曲线。
每张图底部图注统一标注 evidence_scope、数据来源文件；fig9 额外说明“panel b 仅为族内 task 分布，
不声称任务族间差异”（A5-S2M0R5-01）。所有图题、坐标轴、图例、注记使用中文。
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

_CJK_FONT_CANDIDATES = ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans")
plt.rcParams["font.sans-serif"] = list(_CJK_FONT_CANDIDATES)
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 120
plt.rcParams["savefig.dpi"] = 150

_ARM_COLORS = {"FULL_MAML": "#c0392b", "FOMAML": "#2471a3"}
_ARM_LABELS = {"FULL_MAML": "FULL_MAML（全二阶近似）", "FOMAML": "FOMAML（一阶基线）"}

_NOT_APPLICABLE = "NOT_APPLICABLE"

# 每图图注的“数据来源”标注（键=图键；由 _save 统一写入 PNG 底部）。
_CAPTION_NOTES = {
    "fig1_training_loss_curves": "数据来源：run_records.jsonl（record_type=train；arm×meta_seed）",
    "fig2_post_adaptation_rmse_k5_k10": "数据来源：s2_per_task_aggregates.csv（post_adaptation_rmse_raw_k5/_k10 的 task 级值）",
    "fig3_rmse_vs_K": "数据来源：s2_per_task_aggregates.csv（task 级值；percentile bootstrap 10,000 次，seed=20261105）",
    "fig4_meta_gradient_fd": "数据来源：冻结 prereg 的 fd_gate.pilot_artifacts（原始 FD 产物）",
    "fig5_effect_size_ci": "数据来源：aggregate.json 的 inference 与 holm（task 级配对）",
    "fig6_descriptive_k0_k1_standardized": "数据来源：s2_per_task_aggregates.csv（描述性端点，不做 benefit/harm 判定）",
    "fig7_determinism_and_negative_controls": "数据来源：aggregate.json 的 negative_controls 与 coverage",
    "fig8_performance_cost": "数据来源：aggregate.json 的 resources.per_arm 与 train_wall_seconds_ratio；仅描述，不参与判定",
    "fig9_task_family_diagnostics": "数据来源：s2_per_task_aggregates.csv（K=5）+ 冻结包 tasks.json；panel b 仅为族内 task 分布，不声称任务族间差异",
}

# 当前图的证据范围注记（由 generate_s2_figures 在每图渲染前设置，_save 负责写进图注）。
_ACTIVE_SCOPE_NOTE = ""


def _evidence_scope_note(state: Mapping[str, Any]) -> str:
    """图注证据范围标注：必须显式写出 evidence_scope，缺失时写 UNKNOWN 并说明。"""
    scope = state.get("evidence_scope")
    if isinstance(scope, str) and scope.strip():
        return (
            "evidence_scope=" + scope.strip()
            + "（开发集验证结论：仅 meta_validation 20 任务；不构成确证性泛化结论）"
        )
    return "evidence_scope=UNKNOWN（图中输入缺少 evidence_scope；本图不得用于任何泛化结论）"


def _support_rows(state: Mapping[str, Any], key: str, result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """为每张图生成可机读的支撑 CSV 行（长表；数值缺失留空，绝不补 0）。"""
    rows: list[dict[str, Any]] = []

    def add(series: Any, x: Any = "", y: Any = "") -> None:
        rows.append({"series": str(series), "x": x if x is not None else "", "y": y if y is not None else ""})

    if key == "fig1_training_loss_curves":
        for row in state.get("train_series") or []:
            loss = _finite(row.get("train_loss"))
            if loss is None or row.get("status") != "OK":
                continue
            add(f"{row.get('arm')}/meta_seed={row.get('meta_seed')}", int(row.get("outer_step") or 0), loss)
    elif key == "fig2_post_adaptation_rmse_k5_k10":
        for endpoint_id, block in (state.get("endpoints") or {}).items():
            full = _endpoint_task_values(block, "FULL_MAML")
            fomaml = _endpoint_task_values(block, "FOMAML")
            for task_id in sorted(set(full) & set(fomaml)):
                add(f"{endpoint_id}/{task_id}", fomaml[task_id], full[task_id])
    elif key == "fig3_rmse_vs_K":
        block = state.get("rmse_vs_k") or {}
        k_values = [int(value) for value in block.get("K") or []]
        for arm, series in (block.get("arms") or {}).items():
            for k_value, value in zip(k_values, series):
                number = _finite(value)
                if number is not None:
                    add(arm, k_value, number)
            arm_ci = (block.get("ci") or {}).get(arm) or {}
            for k_value in k_values:
                cell = arm_ci.get(str(k_value)) or {}
                for field in ("ci_low", "ci_high", "n"):
                    value = cell.get(field)
                    if value is not None:
                        add(arm + "/" + field, k_value, value)
    elif key == "fig4_meta_gradient_fd":
        for name, item in (state.get("fd_gate_evidence") or {}).items():
            number = _finite(item.get("max_relative_error"))
            add(name, "max_relative_error", number)
            add(name, "status", item.get("status"))
        add("threshold", "max_relative_error", 1e-6)
    elif key == "fig5_effect_size_ci":
        adjusted = ((state.get("holm") or {}).get("adjusted_p") or {})
        decisions = state.get("decisions") or {}
        for item in state.get("inference") or []:
            endpoint_id = str(item.get("endpoint_id"))
            add(endpoint_id, "mean_difference", _finite(item.get("mean_difference")))
            bootstrap = item.get("bootstrap") or {}
            add(endpoint_id, "ci_low", _finite(bootstrap.get("ci_low")))
            add(endpoint_id, "ci_high", _finite(bootstrap.get("ci_high")))
            add(endpoint_id, "holm_adjusted_p", _finite(adjusted.get(endpoint_id)))
            add(endpoint_id, "decision", (decisions.get(endpoint_id) or {}).get("decision"))
    elif key == "fig6_descriptive_k0_k1_standardized":
        # v1.5 fig6 合同：仅这 4 项；std_k10 不属于本图。
        allowed = {
            "post_adaptation_rmse_raw_k0",
            "post_adaptation_rmse_raw_k1",
            "post_adaptation_rmse_std_k5",
            "post_adaptation_mae_raw_k5",
        }
        for endpoint_id, block in (state.get("descriptive_metrics") or {}).items():
            if endpoint_id not in allowed:
                continue
            for arm in ("FULL_MAML", "FOMAML"):
                values = [
                    value
                    for value in (
                        _finite(row.get(arm, {}).get("value"))
                        for row in (block.get("per_task") or {}).values()
                    )
                    if value is not None
                ]
                mean = _mean(values)
                if mean is not None:
                    add(f"{endpoint_id}/{arm}", "task_mean", mean)
    elif key == "fig7_determinism_and_negative_controls":
        for row in state.get("negative_controls") or []:
            add(str(row.get("check_id")), "negative_control_status", row.get("status"))
        coverage = state.get("coverage") or {}
        for group in coverage.get("eval_groups") or []:
            add(f"{group.get('arm')}/meta_seed={group.get('meta_seed')}", "records", group.get("records"))
            add(f"{group.get('arm')}/meta_seed={group.get('meta_seed')}", "expected_records", group.get("expected_records"))
    elif key == "fig8_performance_cost":
        resources = state.get("resources") or {}
        per_arm = resources.get("per_arm") or {}
        for arm in ("FULL_MAML", "FOMAML"):
            block = per_arm.get(arm) or {}
            for index, value in enumerate(block.get("train_wall_seconds_per_meta_seed") or []):
                add(arm + "/train_wall_per_meta_seed", index, _finite(value))
            add(arm + "/train_wall_seconds_mean", "mean", _finite(block.get("train_wall_seconds_mean")))
            add(arm + "/peak_memory_mb_max", "max", _finite(block.get("peak_memory_mb_max")))
        ratio = resources.get("train_wall_seconds_ratio") or {}
        add("train_wall_seconds_ratio", "FULL_MAML/FOMAML", _finite(ratio.get("value")))
    elif key == "fig9_task_family_diagnostics":
        block = (state.get("endpoints") or {}).get("post_adaptation_rmse_raw_k5") or {}
        values_by_arm = {arm: _endpoint_task_values(block, arm) for arm in ("FULL_MAML", "FOMAML")}
        for arm in ("FULL_MAML", "FOMAML"):
            for task_id, value in sorted(values_by_arm[arm].items()):
                add(arm, task_id, value)
        families = state.get("task_families") or {}
        for family in sorted(set(families.values())):
            members = [task_id for task_id, fam in families.items() if fam == family]
            for arm in ("FULL_MAML", "FOMAML"):
                family_values = [values_by_arm[arm][task_id] for task_id in members if task_id in values_by_arm[arm]]
                mean = _mean(family_values)
                if mean is not None:
                    add("family/" + family + "/" + arm, family, mean)
        # 图注约束直接写进支撑 CSV，便于审计（PNG 图注同时包含）。
        add(
            "caption/scope_notes",
            "图注",
            "OOD=NOT_APPLICABLE_S2_NO_OOD_SPLIT；约束=NOT_APPLICABLE_S2_SURROGATE_SCOPE；"
            "panel b 仅为族内 task 分布，不声称任务族间差异",
        )
    if not rows:
        add("NONE", "NOT_APPLICABLE", "")
    return rows


def _write_support_csv(state: Mapping[str, Any], key: str, result: Mapping[str, Any], destination: Path) -> None:
    """每图一张支撑 CSV：列含 figure_key/status/evidence_scope，便于审计图与数据的一致性。"""
    note = _evidence_scope_note(state)
    raw_scope = state.get("evidence_scope")
    scope = (
        "evidence_scope=" + str(raw_scope).strip()
        if isinstance(raw_scope, str) and raw_scope.strip()
        else "evidence_scope=UNKNOWN"
    )
    rows = _support_rows(state, key, result)
    path = destination / (key + "_support.csv")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("figure_key", "status", "evidence_scope", "series", "x", "y"),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "figure_key": key,
                    "status": result.get("status"),
                    "evidence_scope": scope,
                    "series": row["series"],
                    "x": row["x"],
                    "y": row["y"],
                }
            )


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _mean(values: Sequence[float]) -> float | None:
    items = [value for value in (_finite(value) for value in values) if value is not None]
    return math.fsum(items) / len(items) if items else None


def _endpoint_task_values(endpoint: Mapping[str, Any], arm: str) -> dict[str, float]:
    values: dict[str, float] = {}
    per_task = endpoint.get("per_task") or {} if isinstance(endpoint, Mapping) else {}
    for task_id, row in per_task.items():
        value = _finite(row[arm]["value"])
        if value is not None:
            values[task_id] = value
    return values


def _save(fig: Any, path: Path, caption_extra: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    lines: list[str] = []
    if _ACTIVE_SCOPE_NOTE:
        # 每张图的图注都必须标注 evidence_scope，防止图被误用为确证性证据。
        lines.append(_ACTIVE_SCOPE_NOTE)
    source_note = _CAPTION_NOTES.get(path.stem)
    if source_note:
        lines.append(source_note)
    if caption_extra:
        lines.append(caption_extra)
    if lines:
        fig.text(0.5, -0.02, "\n".join(lines), ha="center", va="top", fontsize=6.8, color="#555555")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _empty_figure_notice(
    path: Path,
    title: str,
    message: str,
    *,
    status: str = _NOT_APPLICABLE,
) -> dict[str, Any]:
    fig, axis = plt.subplots(figsize=(7.2, 3.6))
    axis.axis("off")
    axis.set_title(title, fontsize=13)
    axis.text(0.5, 0.5, message, ha="center", va="center", fontsize=11, wrap=True)
    _save(fig, path, caption_extra=None)
    return {"status": status, "path": None, "reason": message}


def _fig1_training_loss_curves(state: Mapping[str, Any], path: Path) -> dict[str, Any]:
    series: dict[tuple[str, int], dict[int, float]] = {}
    for row in state.get("train_series") or []:
        if row.get("status") != "OK":
            continue
        loss = _finite(row.get("train_loss"))
        if loss is None:
            continue
        key = (str(row["arm"]), int(row["meta_seed"]))
        series.setdefault(key, {})[int(row["outer_step"])] = loss
    title = "图1 训练损失曲线（按 arm × meta_seed，外循环 200 步）"
    if not series:
        return _empty_figure_notice(path, title, "无可用训练损失记录（NOT_APPLICABLE）：不伪造曲线。")
    fig, axis = plt.subplots(figsize=(8.4, 4.6))
    for (arm, meta_seed), points in sorted(series.items()):
        steps = sorted(points)
        axis.plot(
            steps,
            [points[step] for step in steps],
            color=_ARM_COLORS.get(arm, "#555555"),
            alpha=0.75 if meta_seed else 0.95,
            linewidth=1.1,
            label=f"{_ARM_LABELS.get(arm, arm)} / meta_seed={meta_seed}",
        )
    axis.set_title(title)
    axis.set_xlabel("外循环步")
    axis.set_ylabel("训练损失（train_loss）")
    axis.grid(alpha=0.3)
    axis.legend(fontsize=7.5, ncol=2, loc="upper right")
    _save(fig, path)
    return {"status": "RENDERED", "path": path.name, "reason": None}


def _fig2_post_adaptation_rmse(state: Mapping[str, Any], path: Path) -> dict[str, Any]:
    endpoints = state.get("endpoints") or {}
    target = [("post_adaptation_rmse_raw_k5", "主终点：K=5 raw RMSE"), ("post_adaptation_rmse_raw_k10", "次终点：K=10 raw RMSE")]
    panels = [(endpoint_id, label) for endpoint_id, label in target if endpoint_id in endpoints]
    title = "图2 适配后 RMSE：FULL_MAML 与 FOMAML 逐任务配对（meta_validation，20 任务）"
    if not panels:
        return _empty_figure_notice(path, title, "缺少 k5/k10 端点数据（NOT_APPLICABLE）。")
    fig, axes = plt.subplots(1, len(panels), figsize=(5.4 * len(panels), 4.8), squeeze=False)
    rendered = False
    for axis, (endpoint_id, label) in zip(axes[0], panels):
        block = endpoints[endpoint_id]
        full = _endpoint_task_values(block, "FULL_MAML")
        fomaml = _endpoint_task_values(block, "FOMAML")
        common = sorted(set(full) & set(fomaml))
        if not common:
            axis.axis("off")
            axis.set_title(label, fontsize=11)
            axis.text(0.5, 0.5, "无配对任务（NOT_APPLICABLE）", ha="center", va="center")
            continue
        rendered = True
        x_values = [fomaml[task_id] for task_id in common]
        y_values = [full[task_id] for task_id in common]
        for x_value, y_value in zip(x_values, y_values):
            axis.plot([x_value, x_value], [x_value, y_value], color="#999999", linewidth=0.8, zorder=1)
        axis.scatter(x_values, y_values, s=24, color=_ARM_COLORS["FULL_MAML"], zorder=2, label="任务（FULL vs FOMAML）")
        bound = max(max(x_values), max(y_values)) * 1.05
        axis.plot([0, bound], [0, bound], color="#333333", linestyle="--", linewidth=1.0, label="y=x（两臂相同）")
        axis.set_xlim(0, bound)
        axis.set_ylim(0, bound)
        axis.set_title(label, fontsize=11)
        axis.set_xlabel("FOMAML 的 RMSE")
        axis.set_ylabel("FULL_MAML 的 RMSE")
        axis.grid(alpha=0.3)
        axis.legend(fontsize=7.5, loc="upper left")
        null_count = int(block.get("n_tasks", 0)) - len(common)
        axis.text(
            0.02,
            0.02,
            f"配对 n={len(common)}；null 任务={null_count}；null_ratio={float(block.get('null_ratio', 0.0)):.3f}",
            transform=axis.transAxes,
            fontsize=7.5,
            va="bottom",
        )
    fig.suptitle(title, fontsize=13)
    _save(fig, path)
    if not rendered:
        return {"status": _NOT_APPLICABLE, "path": None, "reason": "k5/k10 均无配对任务" }
    return {"status": "RENDERED", "path": path.name, "reason": None}


def _fig3_rmse_vs_k(state: Mapping[str, Any], path: Path) -> dict[str, Any]:
    block = state.get("rmse_vs_k") or {}
    k_values = [int(value) for value in block.get("K") or []]
    arms = block.get("arms") or {}
    ci_block = block.get("ci") or {}
    title = "图3 适配后 raw RMSE 随支持集规模 K 变化（task 级均值 + 95% bootstrap CI，K=0/1/5/10）"
    plotted = False
    counts: list[int] = []
    fig, axis = plt.subplots(figsize=(8.0, 4.8))
    for arm, series in arms.items():
        xs: list[int] = []
        ys: list[float] = []
        lows: list[float | None] = []
        highs: list[float | None] = []
        for k_value, value in zip(k_values, series):
            number = _finite(value)
            if number is None:
                continue
            cell = (ci_block.get(arm) or {}).get(str(k_value)) or {}
            xs.append(k_value)
            ys.append(number)
            lows.append(_finite(cell.get("ci_low")))
            highs.append(_finite(cell.get("ci_high")))
            count = cell.get("n")
            if isinstance(count, int) and count > 0:
                counts.append(count)
        if not xs:
            continue
        plotted = True
        color = _ARM_COLORS.get(arm, "#555555")
        lower = [low if low is not None else y for low, y in zip(lows, ys)]
        upper = [high if high is not None else y for high, y in zip(highs, ys)]
        axis.fill_between(xs, lower, upper, color=color, alpha=0.15, linewidth=0)
        axis.plot(xs, ys, marker="o", color=color, label=_ARM_LABELS.get(arm, arm))
    if not plotted:
        plt.close(fig)
        return _empty_figure_notice(
            path, title, "所有 K 端点均为 null（NOT_RUN）：不插补、不做跨 task 平滑。", status="NOT_RUN"
        )
    axis.set_title(title)
    axis.set_xlabel("支持集规模 K（适配内循环步数）")
    axis.set_ylabel("raw RMSE（task 级均值；阴影=95% percentile bootstrap CI）")
    axis.grid(alpha=0.3)
    axis.legend(fontsize=8)
    note_parts = [
        "重采样单元=meta_validation 单个 task；先取该 task 的 meta_seed×draw 聚合值，",
        "再对 task 级值做 10,000 次 percentile bootstrap（seed=20261105）。",
    ]
    if counts:
        note_parts.append("实际参与重采样的 task 数最少 n=" + str(min(counts)) + "。")
    if counts and min(counts) < 20:
        note_parts.append("注意：n<20，CI 仅在披露的实际 n 内有效。")
    _save(fig, path, caption_extra="".join(note_parts))
    return {"status": "RENDERED", "path": path.name, "reason": None}


def _fig4_meta_gradient_fd(state: Mapping[str, Any], path: Path) -> dict[str, Any]:
    evidence = state.get("fd_gate_evidence") or {}
    title = "图4 元梯度有限差分门禁（FD pilot：max_relative_error 与 1e-6 阈值）"
    labels: list[str] = []
    values: list[float] = []
    statuses: list[str] = []
    for name, item in evidence.items():
        labels.append("micro（小规模）" if name == "micro" else "full_size（正式规模）")
        statuses.append(str(item.get("status")))
        number = _finite(item.get("max_relative_error"))
        values.append(number if number is not None else float("nan"))
    numeric = [value for value in values if math.isfinite(value)]
    if not labels or not numeric:
        return _empty_figure_notice(
            path,
            title,
            "FD 证据未提供数值 max_relative_error（状态：" + ",".join(statuses) + "）：NOT_APPLICABLE，不伪造曲线。",
        )
    fig, axis = plt.subplots(figsize=(7.2, 4.2))
    positions = list(range(len(labels)))
    colors = ["#27ae60" if status == "PASS" else "#c0392b" for status in statuses]
    axis.bar(positions, [value if math.isfinite(value) else 0.0 for value in values], color=colors, width=0.55)
    axis.set_yscale("log")
    axis.axhline(1e-6, color="#c0392b", linestyle="--", linewidth=1.2, label="预注册阈值 1e-6")
    axis.set_xticks(positions)
    axis.set_xticklabels([label + "\nstatus=" + status for label, status in zip(labels, statuses)], fontsize=8.5)
    axis.set_title(title)
    axis.set_ylabel("最大相对误差（对数轴）")
    axis.grid(alpha=0.3, axis="y")
    axis.legend(fontsize=8)
    for position, value in zip(positions, values):
        if math.isfinite(value):
            axis.text(position, value, f"{value:.2e}", ha="center", va="bottom", fontsize=8.5)
    _save(fig, path)
    return {"status": "RENDERED", "path": path.name, "reason": None}

def _fig5_effect_size_ci(state: Mapping[str, Any], path: Path) -> dict[str, Any]:
    inferences = list(state.get("inference") or [])
    title = "图5 配对效应量与 95% bootstrap 置信区间（C1 = FULL_MAML − FOMAML，逐任务 n=20）"
    rows = [item for item in inferences if int(item.get("n_pairs") or 0) > 0 and _finite(item.get("mean_difference")) is not None]
    if not rows:
        return _empty_figure_notice(path, title, "无可用配对推断结果（NOT_APPLICABLE）。")
    decisions = state.get("decisions") or {}
    holm = state.get("holm") or {}
    adjusted = holm.get("adjusted_p") or {}
    fig, axis = plt.subplots(figsize=(8.2, 4.0 + 0.35 * len(rows)))
    labels: list[str] = []
    for index, item in enumerate(rows):
        endpoint_id = str(item["endpoint_id"])
        mean_difference = float(item["mean_difference"])
        bootstrap = item.get("bootstrap") or {}
        ci_low = _finite(bootstrap.get("ci_low"))
        ci_high = _finite(bootstrap.get("ci_high"))
        label = ("主终点 K=5" if "k5" in endpoint_id else "次终点 K=10") + "\n" + endpoint_id
        labels.append(label)
        if ci_low is not None and ci_high is not None:
            axis.plot([ci_low, ci_high], [index, index], color="#2471a3", linewidth=2.0, zorder=2)
        axis.scatter([mean_difference], [index], s=46, color=_ARM_COLORS["FULL_MAML"], zorder=3)
        relative = (item.get("relative_improvement") or {}).get("value")
        parts = [f"mean={mean_difference:.4g}"]
        if relative is not None:
            parts.append(f"相对改善={float(relative) * 100:.2f}%")
        p_adjusted = adjusted.get(endpoint_id)
        if p_adjusted is not None:
            parts.append(f"Holm p={float(p_adjusted):.4g}")
        decision = (decisions.get(endpoint_id) or {}).get("decision")
        if decision:
            parts.append(str(decision))
        axis.text(max(ci_high if ci_high is not None else mean_difference, mean_difference), index + 0.16, "；".join(parts), fontsize=7.6)
    axis.axvline(0.0, color="#333333", linestyle="--", linewidth=1.0)
    axis.set_yticks(range(len(rows)))
    axis.set_yticklabels(labels, fontsize=8.5)
    axis.set_title(title, fontsize=11.5)
    axis.set_xlabel("任务级配对差值均值（负值表示 FULL_MAML 更优）")
    axis.grid(alpha=0.3, axis="x")
    _save(fig, path)
    return {"status": "RENDERED", "path": path.name, "reason": None}


def _fig6_descriptive_k0_k1_standardized(state: Mapping[str, Any], path: Path) -> dict[str, Any]:
    metrics = state.get("descriptive_metrics") or {}
    # v1.5 fig6 合同：恰为这 4 项（std_k10 不属于本图）。
    order = [
        ("post_adaptation_rmse_raw_k0", "raw RMSE K=0"),
        ("post_adaptation_rmse_raw_k1", "raw RMSE K=1"),
        ("post_adaptation_rmse_std_k5", "标准化 RMSE K=5"),
        ("post_adaptation_mae_raw_k5", "raw MAE K=5"),
    ]
    title = "图6 描述性指标（K=0/1、标准化 RMSE、MAE）：仅描述，不做 benefit/harm 判定"
    present = [(endpoint_id, label) for endpoint_id, label in order if endpoint_id in metrics]
    if not present:
        return _empty_figure_notice(path, title, "缺少描述性指标数据（NOT_APPLICABLE）。")
    fig, axis = plt.subplots(figsize=(9.2, 4.6))
    width = 0.36
    positions = list(range(len(present)))
    any_value = False
    for arm_offset, arm in ((-width / 2.0, "FULL_MAML"), (width / 2.0, "FOMAML")):
        means: list[float] = []
        for endpoint_id, _label in present:
            block = metrics[endpoint_id]
            values = [
                value
                for value in (_finite(row[arm]["value"]) for row in block["per_task"].values())
                if value is not None
            ]
            mean = _mean(values)
            if mean is not None:
                any_value = True
            means.append(mean if mean is not None else 0.0)
        axis.bar(
            [position + arm_offset for position in positions],
            means,
            width=width,
            color=_ARM_COLORS[arm],
            label=_ARM_LABELS[arm],
        )
    if not any_value:
        plt.close(fig)
        return _empty_figure_notice(path, title, "描述性指标全部为 null（NOT_APPLICABLE）：不写 0 冒充数值。")
    for position, (endpoint_id, _label) in zip(positions, present):
        block = metrics[endpoint_id]
        null_ratio = float(block.get("null_ratio") or 0.0)
        if null_ratio > 0:
            axis.text(position, 0.0, f"null率{null_ratio:.2f}", ha="center", va="bottom", fontsize=7.5, color="#7f8c8d")
    axis.set_xticks(positions)
    axis.set_xticklabels([label for _endpoint_id, label in present], fontsize=8.5)
    axis.set_title(title, fontsize=11.5)
    axis.set_ylabel("任务级均值")
    axis.grid(alpha=0.3, axis="y")
    axis.legend(fontsize=8)
    _save(fig, path)
    return {"status": "RENDERED", "path": path.name, "reason": None}


def _fig7_determinism_and_negative_controls(state: Mapping[str, Any], path: Path) -> dict[str, Any]:
    controls = list(state.get("negative_controls") or [])
    coverage = state.get("coverage") or {}
    groups = list(coverage.get("eval_groups") or [])
    title = "图7 负控/边界核对与评估网格覆盖（determinism 仅披露，不伪造 PASS）"
    if not controls and not groups:
        return _empty_figure_notice(path, title, "缺少负控与覆盖数据（NOT_APPLICABLE）。")
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.8))
    status_axis, coverage_axis = axes
    if controls:
        categories = sorted({str(row.get("category")) for row in controls})
        statuses = ["PASS", "DISCLOSED", "FAIL"]
        colors = {"PASS": "#27ae60", "DISCLOSED": "#f39c12", "FAIL": "#c0392b"}
        width = 0.26
        positions = list(range(len(categories)))
        for offset, status in enumerate(statuses):
            counts = [sum(1 for row in controls if str(row.get("category")) == category and str(row.get("status")) == status) for category in categories]
            status_axis.bar([position + (offset - 1) * width for position in positions], counts, width=width, color=colors[status], label=status)
        status_axis.set_xticks(positions)
        status_axis.set_xticklabels(categories, rotation=55, ha="right", fontsize=7.5)
        status_axis.set_ylabel("核对项数量")
        status_axis.set_title("负控/边界核对状态分布", fontsize=10.5)
        status_axis.legend(fontsize=7.5, title="状态")
        status_axis.grid(alpha=0.3, axis="y")
    else:
        status_axis.axis("off")
        status_axis.text(0.5, 0.5, "无负控数据", ha="center", va="center")
    if groups:
        labels = [f"{group['arm']}/seed{group['meta_seed']}" for group in groups]
        records = [int(group["records"]) for group in groups]
        expected = [int(group["expected_records"]) for group in groups]
        coverage_axis.bar(labels, records, color="#2471a3", label="实际记录数")
        coverage_axis.plot(labels, expected, color="#c0392b", linestyle="--", marker="x", linewidth=1.2, label="预期记录数")
        coverage_axis.set_title("eval 网格覆盖（每 arm/meta_seed）", fontsize=10.5)
        coverage_axis.set_ylabel("eval 记录数")
        coverage_axis.tick_params(axis="x", rotation=55, labelsize=7.5)
        coverage_axis.grid(alpha=0.3, axis="y")
        coverage_axis.legend(fontsize=7.5)
        if not coverage.get("complete", False):
            coverage_axis.text(0.02, 0.98, "网格不完整（已披露）", transform=coverage_axis.transAxes, va="top", fontsize=8, color="#c0392b")
    else:
        coverage_axis.axis("off")
        coverage_axis.text(0.5, 0.5, "无覆盖数据", ha="center", va="center")
    fig.suptitle(title, fontsize=12.5)
    _save(fig, path)
    return {"status": "RENDERED", "path": path.name, "reason": None}


def _fig8_performance_cost(state: Mapping[str, Any], path: Path) -> dict[str, Any]:
    """fig8 性能-成本：panel a 逐 meta_seed 训练墙钟；panel b 墙钟比与两臂峰值内存（仅描述）。"""
    resources = state.get("resources") or {}
    per_arm = resources.get("per_arm") or {}
    title = "图8 性能-成本（FULL_MAML vs FOMAML）：训练墙钟与峰值内存（仅描述，不参与判定）"
    seeds: dict[str, list[float]] = {}
    for arm in ("FULL_MAML", "FOMAML"):
        block = per_arm.get(arm) or {}
        values = [
            number
            for number in (_finite(value) for value in (block.get("train_wall_seconds_per_meta_seed") or []))
            if number is not None
        ]
        if values:
            seeds[arm] = values
    ratio = resources.get("train_wall_seconds_ratio") or {}
    ratio_value = _finite(ratio.get("value"))
    peaks = {arm: _finite((per_arm.get(arm) or {}).get("peak_memory_mb_max")) for arm in ("FULL_MAML", "FOMAML")}
    has_peaks = any(value is not None for value in peaks.values())
    if not seeds and ratio_value is None and not has_peaks:
        return _empty_figure_notice(
            path,
            title,
            "缺少训练墙钟/峰值内存记录（NOT_RUN）：不得用估计值或训练日志估算代替。",
            status="NOT_RUN",
        )
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.6))
    wall_axis, cost_axis = axes
    if seeds:
        for arm, values in seeds.items():
            wall_axis.plot(
                range(len(values)),
                values,
                marker="o",
                color=_ARM_COLORS.get(arm, "#555555"),
                label=_ARM_LABELS.get(arm, arm),
            )
        wall_axis.set_title("panel a：逐 meta_seed 训练墙钟", fontsize=10.5)
        wall_axis.set_xlabel("meta_seed 序号")
        wall_axis.set_ylabel("训练墙钟（秒/ meta_seed）")
        wall_axis.grid(alpha=0.3)
        wall_axis.legend(fontsize=7.5)
    else:
        wall_axis.axis("off")
        wall_axis.text(0.5, 0.5, "无 per_meta_seed 训练墙钟记录（NOT_RUN）", ha="center", va="center")
    xticks: list[float] = []
    xticklabels: list[str] = []
    if ratio_value is not None:
        cost_axis.bar([0.0], [ratio_value], width=0.5, color="#7f8c8d")
        cost_axis.text(0.0, ratio_value, f"{ratio_value:.3f}×", ha="center", va="bottom", fontsize=9)
        xticks.append(0.0)
        xticklabels.append("训练墙钟比\nFULL/FOMAML")
    else:
        cost_axis.text(
            0.02, 0.98, "训练墙钟比缺失（NOT_RUN）", transform=cost_axis.transAxes, va="top", fontsize=8, color="#c0392b"
        )
    peak_axis = cost_axis.twinx()
    for index, arm in enumerate(("FULL_MAML", "FOMAML")):
        value = peaks[arm]
        if value is None:
            continue
        x_position = 1.0 + index
        peak_axis.bar([x_position], [value], width=0.5, color=_ARM_COLORS[arm], alpha=0.85)
        peak_axis.text(x_position, value, f"{value:.0f}", ha="center", va="bottom", fontsize=8.5)
        xticks.append(x_position)
        xticklabels.append(arm + "\n峰值内存")
    if not has_peaks:
        cost_axis.text(
            0.02, 0.90, "峰值内存缺失（NOT_RUN）", transform=cost_axis.transAxes, va="top", fontsize=8, color="#c0392b"
        )
    cost_axis.set_xticks(xticks)
    cost_axis.set_xticklabels(xticklabels, fontsize=8.5)
    cost_axis.set_xlim(-0.6, max(2.6, (max(xticks) if xticks else 0.0) + 0.6))
    cost_axis.set_title("panel b：训练墙钟比与两臂峰值内存", fontsize=10.5)
    cost_axis.set_ylabel("训练墙钟比（FULL_MAML/FOMAML）")
    peak_axis.set_ylabel("峰值内存（MB）")
    cost_axis.grid(alpha=0.3, axis="y")
    fig.suptitle(title, fontsize=12.5)
    _save(fig, path, caption_extra="资源数值直取 aggregate.json 的 resources.per_arm；仅描述，不参与 benefit/harm 判定。")
    return {"status": "RENDERED", "path": path.name, "reason": None}


def _fig9_task_family_diagnostics(state: Mapping[str, Any], path: Path) -> dict[str, Any]:
    """fig9 任务族诊断：panel a 逐 task K=5 RMSE（两臂同序）；panel b 族内分布（不声称族间差异）。"""
    block = (state.get("endpoints") or {}).get("post_adaptation_rmse_raw_k5") or {}
    full = _endpoint_task_values(block, "FULL_MAML")
    fomaml = _endpoint_task_values(block, "FOMAML")
    families = state.get("task_families") or {}
    reason = state.get("task_families_reason")
    title = "图9 任务族诊断（K=5 task 级 RMSE；panel b 仅为族内 task 分布）"
    if not full and not fomaml:
        return _empty_figure_notice(path, title, "缺少 K=5 task 级 RMSE（NOT_RUN）：不伪造族诊断。", status="NOT_RUN")
    fig, axes = plt.subplots(1, 2, figsize=(13.6, 5.0))
    order_axis, family_axis = axes
    common = [task for task in fomaml if task in full]
    common.sort(key=lambda task: (fomaml[task], task))
    if common:
        positions = list(range(len(common)))
        order_axis.plot(
            positions,
            [fomaml[task] for task in common],
            marker="o",
            ms=3.2,
            linewidth=1.0,
            color=_ARM_COLORS["FOMAML"],
            label=_ARM_LABELS["FOMAML"],
        )
        order_axis.plot(
            positions,
            [full[task] for task in common],
            marker="o",
            ms=3.2,
            linewidth=1.0,
            color=_ARM_COLORS["FULL_MAML"],
            label=_ARM_LABELS["FULL_MAML"],
        )
        order_axis.set_xlabel("task（按 FOMAML 的 K=5 RMSE 升序；配对 n=" + str(len(common)) + "）")
        order_axis.set_ylabel("K=5 raw RMSE（task 级）")
        order_axis.legend(fontsize=7.5)
    else:
        order_axis.axis("off")
        order_axis.text(0.5, 0.5, "无配对 task（NOT_RUN）", ha="center", va="center")
    order_axis.set_title("panel a：逐 task K=5 RMSE（两臂同序）", fontsize=10.5)
    order_axis.grid(alpha=0.3, axis="y")
    family_note = ""
    if not families:
        family_axis.axis("off")
        family_axis.text(
            0.5,
            0.5,
            "task→family 映射不可用：panel b NOT_RUN\n原因：" + str(reason or "UNKNOWN"),
            ha="center",
            va="center",
            wrap=True,
        )
        family_note = "panel b NOT_RUN：task→family 映射不可用（" + str(reason or "UNKNOWN") + "）。"
    else:
        values_by_arm = {"FULL_MAML": full, "FOMAML": fomaml}
        family_names = sorted(set(families.values()))
        members = {family: [task for task, fam in families.items() if fam == family] for family in family_names}
        width = 0.36
        positions = list(range(len(family_names)))
        has_values = False
        for offset, arm in ((-width / 2.0, "FULL_MAML"), (width / 2.0, "FOMAML")):
            means: list[float] = []
            ranges: list[tuple[float, float] | None] = []
            for family in family_names:
                values = [values_by_arm[arm][task] for task in members[family] if task in values_by_arm[arm]]
                mean = _mean(values)
                means.append(mean if mean is not None else 0.0)
                ranges.append((min(values), max(values)) if values else None)
                has_values = has_values or mean is not None
            family_axis.bar(
                [position + offset for position in positions],
                means,
                width=width,
                color=_ARM_COLORS[arm],
                label=_ARM_LABELS[arm],
            )
            for position, value_range in zip(positions, ranges):
                if value_range is not None:
                    family_axis.plot(
                        [position + offset, position + offset],
                        [value_range[0], value_range[1]],
                        color="#333333",
                        linewidth=1.1,
                    )
        family_axis.set_xticks(positions)
        family_axis.set_xticklabels(
            [family + "\n(n=" + str(len(members[family])) + ")" for family in family_names], fontsize=7.5
        )
        family_axis.set_title("panel b：族内 task 分布（不声称任务族间差异）", fontsize=10.5)
        family_axis.set_ylabel("族内 K=5 raw RMSE（柱=均值，竖线=范围）")
        family_axis.grid(alpha=0.3, axis="y")
        family_axis.legend(fontsize=7.5)
        if len(family_names) == 1:
            family_note = (
                "S0-7 全部 task 同属单一 family "
                + family_names[0]
                + "：panel b 仅为族内 task 分布，不声称任务族间差异。"
            )
        else:
            family_note = "多 family 仅逐族展示族内分布，不声称任务族间显著性差异。"
        if not has_values:
            family_axis.text(
                0.02, 0.98, "族内数值缺失（NOT_RUN）", transform=family_axis.transAxes, va="top", fontsize=8, color="#c0392b"
            )
    fig.suptitle(title, fontsize=12.5)
    extra = (
        "OOD：NOT_APPLICABLE_S2_NO_OOD_SPLIT；约束：NOT_APPLICABLE_S2_SURROGATE_SCOPE。" + family_note
    )
    _save(fig, path, caption_extra=extra)
    return {"status": "RENDERED", "path": path.name, "reason": None}


_FIGURE_FUNCTIONS = {
    "fig1_training_loss_curves": _fig1_training_loss_curves,
    "fig2_post_adaptation_rmse_k5_k10": _fig2_post_adaptation_rmse,
    "fig3_rmse_vs_K": _fig3_rmse_vs_k,
    "fig4_meta_gradient_fd": _fig4_meta_gradient_fd,
    "fig5_effect_size_ci": _fig5_effect_size_ci,
    "fig6_descriptive_k0_k1_standardized": _fig6_descriptive_k0_k1_standardized,
    "fig7_determinism_and_negative_controls": _fig7_determinism_and_negative_controls,
    "fig8_performance_cost": _fig8_performance_cost,
    "fig9_task_family_diagnostics": _fig9_task_family_diagnostics,
}


def generate_s2_figures(
    *,
    state: Mapping[str, Any],
    output_dir: str | Path,
    figure_filenames: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """生成 9 张规范键图（fig1–fig9）并返回 figure_status 结构（由 s2_analysis 校验后落盘）。"""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    filenames = dict(figure_filenames or {key: key + ".png" for key in _FIGURE_FUNCTIONS})
    figures: dict[str, Any] = {}
    global _ACTIVE_SCOPE_NOTE
    _ACTIVE_SCOPE_NOTE = _evidence_scope_note(state)
    for key, function in _FIGURE_FUNCTIONS.items():
        filename = str(filenames.get(key) or (key + ".png"))
        path = destination / filename
        try:
            result = function(state, path)
        except Exception as exc:  # noqa: BLE001 - 单图失败不得中断其余图，且必须写入原因
            result = {
                "status": "NOT_RUN",
                "path": None,
                "reason": ("RENDER_ERROR: " + str(exc).replace("\n", " "))[:300],
            }
        _write_support_csv(state, key, result, destination)
        status_text = str(result.get("status"))
        if status_text == "RENDERED":
            figures[key] = {"status": "RENDERED", "path": filename, "reason": None}
        else:
            figures[key] = {
                "status": "NOT_RUN" if status_text == "NOT_RUN" else "NOT_APPLICABLE",
                "path": None,
                "reason": result.get("reason"),
            }
    summary = {
        "n_figures": len(figures),
        "n_rendered": sum(1 for item in figures.values() if item["status"] == "RENDERED"),
        "n_not_run": sum(1 for item in figures.values() if item["status"] == "NOT_RUN"),
        "n_not_applicable": sum(1 for item in figures.values() if item["status"] == "NOT_APPLICABLE"),
    }
    return {"figures": figures, "summary": summary}
