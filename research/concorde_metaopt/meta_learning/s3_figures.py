"""S3 十图渲染（计划 §5.3；只读 figure_state，不触碰 run 目录）。

约定：
- 每图输出 PNG + 同名 _data.csv（figN_..._data.csv），图注含 evidence_scope 与数据源 sha；
- 数据缺失时返回 NOT_RUN（不渲染伪造数据），由 analysis 写入 figure_status.json；
- 仅使用 matplotlib Agg 后端；中文标签优先使用系统 CJK 字体，找不到时回退并披露。
"""

from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from . import s3_prereg as sp

FIGURE_KEYS = (
    "fig1_training_loss_and_full_meta_grad",
    "fig2_kshot_rmse_k0_k1_k3_k5",
    "fig3_feasible_hit_rate_by_arm",
    "fig4_best_feasible_and_first_feasible",
    "fig5_fomaml_vs_full_vs_anil_cost",
    "fig6_task_family_diagnostics",
    "fig7_ood_diagnostics",
    "fig8_negative_controls",
    "fig9_determinism_and_budget",
    "fig10_vspaero_gate_status",
)

EVIDENCE_SCOPE_NOTE = "DEVELOPMENT_VALIDATION_ONLY：本图仅用于开发验证，不作确证性结论"
CJK_FONT_CANDIDATES = (
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
)


def _windows_font_files() -> tuple[str, ...]:
    """由 Windows 目录环境变量派生候选字体文件路径（不硬编码本机绝对路径）。"""
    winroot = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or ""
    if not winroot:
        return ()
    font_dir = Path(winroot) / "Fonts"
    return tuple(str(font_dir / name) for name in ("msyh.ttc", "simhei.ttf", "msyhbd.ttc"))


CJK_FONT_FILES = _windows_font_files()


class FigureError(RuntimeError):
    """图渲染错误（analysis 层会转为 NOT_RUN 并披露）。"""

    def __init__(self, message: str, *, code: str = "S3_FIGURE_ERROR") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _configure_chinese_font() -> str:
    """配置中文字体；返回实际生效的字体族名（找不到时返回空串）。"""
    available = {font.name for font in font_manager.fontManager.ttflist}
    chosen = ""
    for candidate in CJK_FONT_CANDIDATES:
        if candidate in available:
            chosen = candidate
            break
    if not chosen:
        for path in CJK_FONT_FILES:
            if not path:  # 无 Windows 字体目录时跳过（非 Windows 环境）
                continue
            if Path(path).is_file():
                try:
                    font_manager.fontManager.addfont(path)
                    chosen = font_manager.FontProperties(fname=path).get_name()
                    break
                except Exception:  # noqa: BLE001 - 字体加载失败不影响其它图
                    continue
    family = [chosen] if chosen else ["DejaVu Sans"]
    plt.rcParams["font.sans-serif"] = family + ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 110
    return chosen


def _figure_footer(figure: Any, *, note: str, sources: Sequence[Mapping[str, Any]]) -> None:
    parts = [EVIDENCE_SCOPE_NOTE, note]
    for source in sources:
        name = str(source.get("name") or source.get("path") or "source")
        sha = str(source.get("sha256") or "")
        if sha:
            parts.append(name + " sha256=" + sha[:16] + "…")
    figure.text(0.5, 0.01, " | ".join(parts), ha="center", va="bottom", fontsize=6.5, color="#444444", wrap=True)


def _write_data_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in columns:
                columns.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns or ["status"])
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _csv_cell(row.get(column)) for column in (columns or ["status"])})
    return sp.sha256_file(path)


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False, sort_keys=True)
    if isinstance(value, Mapping):
        return json.dumps(dict(value), ensure_ascii=False, sort_keys=True)
    return value


def _save_figure(figure: Any, *, key: str, output_dir: Path, rows: Sequence[Mapping[str, Any]], note: str, sources: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    csv_path = output_dir / (key + "_data.csv")
    data_sha = _write_data_csv(csv_path, rows)
    _figure_footer(figure, note=note, sources=sources)
    figure.tight_layout(rect=(0.0, 0.05, 1.0, 1.0))
    png_path = output_dir / (key + ".png")
    figure.savefig(png_path, bbox_inches="tight")
    plt.close(figure)
    return {"status": "RENDERED", "path": str(png_path), "csv_path": str(csv_path), "reason": "", "data_sha256": data_sha}


def _not_run(key: str, reason: str) -> dict[str, Any]:
    return {"status": "NOT_RUN", "path": None, "csv_path": None, "reason": str(reason)}


def _rows(state: Mapping[str, Any], name: str) -> list[dict[str, Any]]:
    value = state.get(name)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _endpoint_rows(state: Mapping[str, Any], endpoint: str) -> list[dict[str, Any]]:
    return [row for row in _rows(state, "endpoint_rows") if str(row.get("endpoint")) == endpoint]


def _sources(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _rows(state, "source_files")


def _arm_style(arm: str) -> dict[str, Any]:
    if arm == "S3-BO-FOMAML-CON":
        return {"color": "#1f77b4", "marker": "o", "label": "FOMAML-CON（主对比）"}
    if arm == "S3-BO-FOMAML-OBJ":
        return {"color": "#d62728", "marker": "s", "label": "FOMAML-OBJ（主对比）"}
    if arm == "S3-BO-RANDOM":
        return {"color": "#7f7f7f", "marker": "^", "label": "RANDOM（描述性）"}
    if arm == "S3-BO-ANIL-CON":
        return {"color": "#2ca02c", "marker": "D", "label": "ANIL-CON（成本审计）"}
    return {"color": "#9467bd", "marker": "v", "label": "DE（描述性）"}


def _fig1(state: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    training = state.get("training") or {}
    losses = training.get("loss_by_meta_seed") if isinstance(training, Mapping) else None
    if not isinstance(losses, Mapping) or not losses:
        return _not_run("fig1_training_loss_and_full_meta_grad", "train record 缺失，无法绘制训练损失")
    figure, axes = plt.subplots(1, 2, figsize=(11.0, 4.2))
    rows: list[dict[str, Any]] = []
    for seed, series in sorted(losses.items()):
        steps = [int(item[0]) for item in series]
        values = [float(item[1]) for item in series]
        axes[0].plot(steps, values, marker=".", linewidth=1.2, label="meta_seed=" + str(seed))
        for step, value in zip(steps, values):
            rows.append({"panel": "training_loss", "meta_seed": int(seed), "outer_step": step, "loss": value})
    axes[0].set_title("图1a 训练损失随 outer step 变化")
    axes[0].set_xlabel("outer step")
    axes[0].set_ylabel("训练损失")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)
    axes[1].text(0.5, 0.55, "全量元梯度范数: NOT_AVAILABLE_IN_RECORDS", ha="center", va="center", transform=axes[1].transAxes, fontsize=10, color="#b22222")
    axes[1].set_title("图1b 全量元梯度（记录不含该字段）")
    axes[1].axis("off")
    rows.append({"panel": "full_meta_grad", "status": "NOT_AVAILABLE_IN_RECORDS"})
    return _save_figure(figure, key="fig1_training_loss_and_full_meta_grad", output_dir=output_dir, rows=rows, note="训练损失来自 run_records train 行；全量元梯度未在 8 字段 train record 中记录", sources=_sources(state))


def _fig2(state: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    kshot = state.get("kshot") or {}
    if isinstance(kshot, Mapping) and str(kshot.get("status")) == "NOT_RUN":
        return _not_run("fig2_kshot_rmse_k0_k1_k3_k5", str(kshot.get("reason")))
    return _not_run("fig2_kshot_rmse_k0_k1_k3_k5", "无 K-shot 曲线数据")


def _fig3(state: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    rows_all = _endpoint_rows(state, "feasible_hit_rate")
    if not rows_all:
        return _not_run("fig3_feasible_hit_rate_by_arm", "端点表缺 feasible_hit_rate")
    budgets = sorted({int(row["budget"]) for row in rows_all})
    arms = [str(arm) for arm in (state.get("arms") or [])]
    figure, axes = plt.subplots(figsize=(9.0, 4.6))
    width = 0.8 / max(len(arms), 1)
    rows: list[dict[str, Any]] = []
    for arm_index, arm in enumerate(arms):
        values = []
        positions = []
        for budget_index, budget in enumerate(budgets):
            match = [row for row in rows_all if str(row.get("arm_id")) == arm and int(row["budget"]) == budget]
            if not match:
                continue
            entry = match[0]
            values.append(float(entry["mean"]) if entry.get("mean") is not None else float("nan"))
            positions.append(budget_index + arm_index * width + width / 2.0)
            rows.append({"arm_id": arm, "budget": budget, "mean": entry.get("mean"), "ci_low": entry.get("ci_low"), "ci_high": entry.get("ci_high"), "n_null": entry.get("n_null")})
        style = _arm_style(arm)
        axes.bar(positions, values, width=width, color=style["color"], label=style["label"], alpha=0.85)
    axes.set_xticks([index + 0.4 for index in range(len(budgets))])
    axes.set_xticklabels(["预算 B=" + str(budget) for budget in budgets])
    axes.set_ylabel("可行命中率（均值，task 级 bootstrap 95% CI）")
    axes.set_title("图3 各臂可行命中率（主对比 CON−OBJ；RANDOM/DE 仅描述）")
    axes.legend(fontsize=8)
    axes.grid(axis="y", alpha=0.3)
    axes.set_ylim(0.0, 1.0)
    return _save_figure(figure, key="fig3_feasible_hit_rate_by_arm", output_dir=output_dir, rows=rows, note="主对比为 CON−OBJ；RANDOM/DE 仅供描述，不参与推断", sources=_sources(state))


def _fig4(state: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    best = _endpoint_rows(state, "best_feasible_value")
    first = _endpoint_rows(state, "first_feasible_eval_index")
    if not best and not first:
        return _not_run("fig4_best_feasible_and_first_feasible", "端点表缺 best/first 数据")
    figure, axes = plt.subplots(1, 2, figsize=(11.0, 4.2))
    rows: list[dict[str, Any]] = []
    for panel_index, (name, rows_all, title, ylabel) in enumerate((
        ("best_feasible_value", best, "图4a 最优可行目标值（越低越好）", "best_feasible_value"),
        ("first_feasible_eval_index", first, "图4b 首个可行评估序号（越小越快）", "first_feasible_eval_index"),
    )):
        arms = [str(arm) for arm in (state.get("arms") or [])]
        for arm_index, arm in enumerate(arms):
            points = [row for row in rows_all if str(row.get("arm_id")) == arm]
            xs = [arm_index + (index - (len(points) - 1) / 2.0) * 0.08 for index in range(len(points))]
            ys = [float(row["mean"]) if row.get("mean") is not None else float("nan") for row in points]
            style = _arm_style(arm)
            axes[panel_index].scatter(xs, ys, color=style["color"], marker=style["marker"], label=style["label"])
            for row, x, y in zip(points, xs, ys):
                rows.append({"panel": name, "arm_id": arm, "budget": row.get("budget"), "mean": y})
        axes[panel_index].set_xticks(range(len(arms)))
        axes[panel_index].set_xticklabels(arms, rotation=20, ha="right", fontsize=8)
        axes[panel_index].set_title(title)
        axes[panel_index].set_ylabel(ylabel)
        axes[panel_index].grid(alpha=0.3)
        axes[panel_index].legend(fontsize=7)
    return _save_figure(figure, key="fig4_best_feasible_and_first_feasible", output_dir=output_dir, rows=rows, note="best/first 为描述性端点，不做推断", sources=_sources(state))


def _fig5(state: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    cost = _rows(state, "cost_rows")
    if not cost:
        return _not_run("fig5_fomaml_vs_full_vs_anil_cost", "成本表缺失")
    figure, axes = plt.subplots(figsize=(9.0, 4.4))
    rows: list[dict[str, Any]] = []
    arms = [str(arm) for arm in (state.get("arms") or [])]
    budgets = sorted({int(row["budget"]) for row in cost})
    width = 0.8 / max(len(arms), 1)
    for arm_index, arm in enumerate(arms):
        values = []
        positions = []
        for budget_index, budget in enumerate(budgets):
            match = [row for row in cost if str(row.get("arm_id")) == arm and int(row["budget"]) == budget]
            if not match:
                continue
            entry = match[0]
            values.append(float(entry["total_cost_mean_s"]) if entry.get("total_cost_mean_s") is not None else 0.0)
            positions.append(budget_index + arm_index * width + width / 2.0)
            rows.append({"arm_id": arm, "budget": budget, "total_cost_mean_s": entry.get("total_cost_mean_s"), "adaptation_cost_mean": entry.get("adaptation_cost_mean")})
        style = _arm_style(arm)
        axes.bar(positions, values, width=width, color=style["color"], label=style["label"], alpha=0.85)
    axes.set_xticks([index + 0.4 for index in range(len(budgets))])
    axes.set_xticklabels(["预算 B=" + str(budget) for budget in budgets])
    axes.set_ylabel("run wall time（秒，均值）")
    axes.set_title("图5 各臂成本对比（FOMAML vs ANIL；S2 归档只读对比不可用）")
    axes.legend(fontsize=8)
    axes.grid(axis="y", alpha=0.3)
    s2 = state.get("s2_archive") or {}
    note = "S2 归档状态: " + str(s2.get("status")) + "；" + str(s2.get("reason", ""))
    return _save_figure(figure, key="fig5_fomaml_vs_full_vs_anil_cost", output_dir=output_dir, rows=rows, note=note, sources=_sources(state))


def _fig6(state: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    families = state.get("task_families") or {}
    rows_all = families.get("rows") if isinstance(families, Mapping) else None
    if not isinstance(rows_all, Sequence) or not rows_all:
        return _not_run("fig6_task_family_diagnostics", "封存参考解缺失，无法做族内 task 诊断")
    figure, axes = plt.subplots(1, 2, figsize=(11.0, 4.2))
    rows: list[dict[str, Any]] = []
    values = [float(row["f_ref"]) for row in rows_all if row.get("f_ref") is not None]
    task_ids = [str(row.get("task_id")) for row in rows_all]
    axes[0].hist(values, bins=min(10, max(3, len(values))), color="#4c72b0", alpha=0.85)
    axes[0].set_title("图6a 族内 task 参考目标值 f_ref 分布")
    axes[0].set_xlabel("f_ref（KKT 参考解目标值）")
    axes[0].set_ylabel("task 数")
    axes[0].grid(axis="y", alpha=0.3)
    kinds: dict[str, int] = {}
    for row in rows_all:
        keys = str(row.get("reference_kind") or "UNKNOWN")
        kinds[keys] = kinds.get(keys, 0) + 1
    axes[1].bar(list(kinds.keys()), list(kinds.values()), color="#55a868")
    axes[1].set_title("图6b 参考解类型计数")
    axes[1].set_ylabel("task 数")
    axes[1].tick_params(axis="x", rotation=15)
    for index, row in enumerate(rows_all):
        rows.append({"task_id": task_ids[index], "f_ref": row.get("f_ref"), "reference_kind": row.get("reference_kind")})
    return _save_figure(figure, key="fig6_task_family_diagnostics", output_dir=output_dir, rows=rows, note="仅描述族内 task 分布，不声称任务族间差异", sources=_sources(state))


def _fig7(state: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    ood = _rows(state, "ood_rows")
    if not ood or all(str(row.get("status")) == "NOT_RUN" for row in ood):
        return _not_run("fig7_ood_diagnostics", "run 产物不含 OOD 段（OOD 分析 NOT_RUN）")
    figure, axes = plt.subplots(figsize=(8.0, 4.2))
    arms = sorted({str(row.get("arm_id")) for row in ood})
    values = []
    for arm in arms:
        entries = [float(row["feasible_hit_rate_mean"]) for row in ood if str(row.get("arm_id")) == arm and row.get("feasible_hit_rate_mean") is not None]
        values.append(sum(entries) / len(entries) if entries else float("nan"))
    axes.bar(arms, values, color="#c44e52", alpha=0.85)
    axes.set_title("图7 OOD 描述性可行命中率（不参与主推断）")
    axes.set_ylabel("OOD 可行命中率均值")
    axes.tick_params(axis="x", rotation=20)
    axes.grid(axis="y", alpha=0.3)
    return _save_figure(figure, key="fig7_ood_diagnostics", output_dir=output_dir, rows=ood, note="OOD 仅描述性，不参与 C1/C2 主推断", sources=_sources(state))


def _fig8(state: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    negative = _rows(state, "negative_control_rows")
    if not negative:
        return _not_run("fig8_negative_controls", "负控行缺失")
    figure, axes = plt.subplots(figsize=(10.0, 4.4))
    ids = [str(row.get("control_id")) for row in negative]
    codes = []
    for row in negative:
        status = str(row.get("status"))
        codes.append({"PASS": 1.0, "FAIL": -1.0, "DISCLOSED": 0.0}.get(status, 0.0))
    colors = ["#2ca02c" if code > 0 else ("#d62728" if code < 0 else "#7f7f7f") for code in codes]
    axes.bar(ids, codes, color=colors)
    axes.set_yticks([-1.0, 0.0, 1.0])
    axes.set_yticklabels(["FAIL", "DISCLOSED", "PASS"])
    axes.set_title("图8 负控制与 fail-closed 证据状态")
    axes.tick_params(axis="x", rotation=45)
    axes.grid(axis="y", alpha=0.3)
    return _save_figure(figure, key="fig8_negative_controls", output_dir=output_dir, rows=negative, note="负控状态由分析层证据派生，禁止硬编码 PASS", sources=_sources(state))


def _fig9(state: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    determinism = _rows(state, "determinism_rows")
    cost = _rows(state, "cost_rows")
    if not determinism and not cost:
        return _not_run("fig9_determinism_and_budget", "确定性/预算数据缺失")
    figure, axes = plt.subplots(1, 2, figsize=(11.0, 4.2))
    rows: list[dict[str, Any]] = []
    if determinism:
        names = [str(row.get("pass")) for row in determinism]
        records = [float(row.get("n_records") or 0.0) for row in determinism]
        axes[0].bar(names, records, color="#8172b2")
        axes[0].set_title("图9a 确定性重跑记录数")
        axes[0].set_ylabel("记录数")
        rows.extend(dict(row) for row in determinism)
    else:
        axes[0].text(0.5, 0.5, "确定性产物缺失（NOT_RUN）", ha="center", transform=axes[0].transAxes)
        axes[0].axis("off")
    if cost:
        budgets = sorted({int(row["budget"]) for row in cost})
        for arm in sorted({str(row.get("arm_id")) for row in cost}):
            entries = [row for row in cost if str(row.get("arm_id")) == arm]
            xs = [budgets.index(int(row["budget"])) for row in entries if int(row["budget"]) in budgets]
            ys = [float(row["total_cost_mean_s"]) if row.get("total_cost_mean_s") is not None else float("nan") for row in entries if int(row["budget"]) in budgets]
            style = _arm_style(arm)
            axes[1].plot(xs, ys, marker=style["marker"], color=style["color"], label=style["label"])
        axes[1].set_xticks(range(len(budgets)))
        axes[1].set_xticklabels(["B=" + str(budget) for budget in budgets])
        axes[1].set_title("图9b 预算-成本（wall time）")
        axes[1].set_ylabel("run wall time（秒）")
        axes[1].legend(fontsize=7)
        axes[1].grid(alpha=0.3)
        rows.extend(dict(row) for row in cost)
    return _save_figure(figure, key="fig9_determinism_and_budget", output_dir=output_dir, rows=rows, note="确定性重跑与预算成本均为描述性", sources=_sources(state))


def _fig10(state: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    gate = state.get("vspaero_gate") or {}
    if not isinstance(gate, Mapping) or str(gate.get("status")) != "OK":
        return _not_run("fig10_vspaero_gate_status", "未找到只读 VSPAERO 门禁归档: " + str(gate.get("reason", "")))
    gates = gate.get("gates") or {}
    if not gates:
        return _not_run("fig10_vspaero_gate_status", "VSPAERO 门禁归档缺 gates 字段")
    figure, axes = plt.subplots(figsize=(10.0, 4.6))
    names = list(gates.keys())
    codes = []
    for name in names:
        text = str(gates[name])
        if text.startswith("PASS"):
            codes.append(1.0)
        elif text.startswith("PARTIAL") or "PROVISIONAL" in text:
            codes.append(0.5)
        elif text.startswith("BLOCKED") or text.startswith("NOT"):
            codes.append(-1.0)
        else:
            codes.append(0.0)
    colors = ["#2ca02c" if code >= 1.0 else ("#ff7f0e" if code > 0.0 else ("#d62728" if code < 0.0 else "#7f7f7f")) for code in codes]
    axes.barh(names, codes, color=colors)
    axes.set_xlim(-1.2, 1.2)
    axes.set_xticks([-1.0, 0.0, 0.5, 1.0])
    axes.set_xticklabels(["BLOCKED/NOT", "UNKNOWN", "PARTIAL", "PASS"])
    axes.set_title("图10 VSPAERO 相关门禁状态（只读归档，未启动求解器）")
    for index, name in enumerate(names):
        axes.text(1.05, index, str(gates[name]), va="center", fontsize=7)
    rows = [{"gate": name, "status": gates[name], "source": gate.get("path"), "source_sha256": gate.get("sha256")} for name in names]
    return _save_figure(figure, key="fig10_vspaero_gate_status", output_dir=output_dir, rows=rows, note="只读 archived gates；physical_call_count=0，未启动 VSPAERO/求解器", sources=_sources(state))


_FIGURE_BUILDERS = {
    "fig1_training_loss_and_full_meta_grad": _fig1,
    "fig2_kshot_rmse_k0_k1_k3_k5": _fig2,
    "fig3_feasible_hit_rate_by_arm": _fig3,
    "fig4_best_feasible_and_first_feasible": _fig4,
    "fig5_fomaml_vs_full_vs_anil_cost": _fig5,
    "fig6_task_family_diagnostics": _fig6,
    "fig7_ood_diagnostics": _fig7,
    "fig8_negative_controls": _fig8,
    "fig9_determinism_and_budget": _fig9,
    "fig10_vspaero_gate_status": _fig10,
}


def generate_figures(figure_state: Mapping[str, Any], *, output_dir: str | Path, repo_root: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """渲染全部 10 图；逐图捕获异常并返回 NOT_RUN 状态。"""
    _ = repo_root
    if not isinstance(figure_state, Mapping):
        raise FigureError("figure_state 必须是 JSON 对象")
    target = Path(output_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    chosen_font = _configure_chinese_font()
    results: dict[str, dict[str, Any]] = {}
    for key in FIGURE_KEYS:
        builder = _FIGURE_BUILDERS[key]
        try:
            result = builder(figure_state, target)
            if isinstance(result, Mapping):
                result = dict(result)
                result["font_family"] = chosen_font
                results[key] = result
            else:
                results[key] = _not_run(key, "图构建器返回非法状态")
        except Exception as error:  # noqa: BLE001 - 单图失败不影响其它图
            plt.close("all")
            results[key] = _not_run(key, "图渲染失败: " + str(error)[:300])
    _write_figure_summary(target / "figure_generation_summary.json", results, chosen_font)
    return results


def _write_figure_summary(path: Path, results: Mapping[str, Any], font: str) -> None:
    summary = {
        "schema_version": "p4ra-s3-figure-generation-1",
        "cjk_font": font,
        "cjk_font_available": bool(font),
        "figures": {key: {"status": item.get("status"), "path": item.get("path"), "csv_path": item.get("csv_path"), "reason": item.get("reason")} for key, item in results.items()},
        "evidence_scope": "DEVELOPMENT_VALIDATION_ONLY",
        "physical_call_count": 0,
    }
    path.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


__all__ = ["FIGURE_KEYS", "FigError" if False else "FigureError", "generate_figures"]
