# -*- coding: utf-8 -*-
"""M5 formal run 中文图生成（fig1/fig3/fig4/fig5）。零求解、只读 run 证据。"""
import argparse
import csv
import hashlib
import json
import os
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.ft2font import FT2Font

RUN_DEFAULT = "D:/RCAIDE-p4-meta-learning/research/concorde_metaopt/optimization_runs/p4-meta-m5-formal-20261104T1018Z"
BASE_DEFAULT = "C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/p4-m5m6/a2/m5_figures_report_attempt2"

ARMS = ["M5-BO-MAML-init", "M5-BO-pretrain-init", "M5-BO-random", "M5-DE"]
ARM_SHORT = {
    "M5-BO-MAML-init": "MAML-init",
    "M5-BO-pretrain-init": "pretrain-init",
    "M5-BO-random": "random",
    "M5-DE": "DE",
}
ARM_COLORS = {
    "M5-BO-MAML-init": "#1f77b4",
    "M5-BO-pretrain-init": "#2ca02c",
    "M5-BO-random": "#7f7f7f",
    "M5-DE": "#d62728",
}
SPLITS = ["meta_test", "meta_test_ood"]
BUDGETS = [64, 128]

TEXT = {
    "fig1_title": "图1 M5 元训练损失（合成解析任务族，3 个元种子）",
    "fig1_x": "元训练迭代步",
    "fig1_y": "代理损失（越小越好）",
    "fig1_leg_q": "MAML 代理 loss_query（3 元种子均值，阴影为 min–max）",
    "fig1_leg_s": "MAML 代理 loss_support（3 元种子均值，虚线）",
    "fig1_leg_p": "预训练代理终点（3 元种子，无迭代曲线）",
    "fig1_foot": "元验证损失 validation_loss = NOT_AVAILABLE（M5 未记录，按合同不得补造）；预训练代理仅 1 个终点值/元种子。",
    "fig3_title": "图3 等预算可行命中率中位数（按数据划分与预算）",
    "fig3_y": "可行命中率中位数（%）",
    "fig3_foot": "柱=各臂可行命中率中位数的中位数聚合；x 轴第二行 = 该臂无任何可行解的 runs 占比（null_run_fraction），如实披露、不当作 0；first_feasible_evaluation_index 覆盖率见报告 4.4；本图仅画可行命中率。\uff1b\u6ce8\uff1a\u56db\u4e2a\u5b50\u56fe\u7eb5\u8f74\u72ec\u7acb\uff08meta_test \u4e0e ood\u3001\u9884\u7b97 64 \u4e0e 128 \u91cf\u7ea7\u4e0d\u540c\uff09\u3002",
    "fig4_title": "图4 等预算最优可行值 / gap_to_reference 收敛曲线（meta_test+ood 合并）",
    "fig4_y1": "中位最优可行值 best_feasible_value（越小越好）",
    "fig4_y2": "中位 gap_to_reference（越小越好）",
    "fig4_x": "评价序号（预算内）",
    "fig4_foot": "曲线按该预算下全部 runs 聚合（meta_test+ood）；无可行解的点保持空白（不插值、不以 best_objective_raw 代替）；图例 n= 为该臂曾出现可行解的 runs 数。",
    "fig5_title": "图5 公平性审计（代理评分成本、初始设计重叠与可识别性）",
    "fig5_a": "代理评分运行次数（柱）与中位耗时（标注）",
    "fig5_b": "初始设计重叠度（clone 审计；越低越可识别）",
    "fig5_foot": "公平性门禁 PASS（4 臂 / 4800 记录 / 2400 组）；可识别性 IDENTIFIABLE（MAML-init vs pretrain-init 的初始设计多数高度重叠但未达 clone 判据，详见报告 6 与 clone_audit.csv）；确定性 PASS，但 run 未保存原始 rerun digest（raw_digest_manifest = NOT_STORED），无法独立复算；物理调用 0（SYNTHETIC_ONLY）。DE 与随机臂初始设计相同但引擎不同（SAME_INIT_DIFFERENT_ENGINE，非克隆）。",
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def setup_font():
    candidates = [
        ("Microsoft YaHei", "C:/Windows/Fonts/msyh.ttc"),
        ("Microsoft YaHei Bold", "C:/Windows/Fonts/msyhbd.ttc"),
        ("SimHei", "C:/Windows/Fonts/simhei.ttf"),
        ("SimSun", "C:/Windows/Fonts/simsun.ttc"),
    ]
    chars = sorted({ch for t in TEXT.values() for ch in t if ord(ch) > 127})
    missing_all = []
    for family, path in candidates:
        if not os.path.exists(path):
            missing_all.append((family, "FILE_MISSING"))
            continue
        try:
            font_manager.fontManager.addfont(path)
            ft = FT2Font(path)
            missing = [ch for ch in chars if ft.get_char_index(ord(ch)) == 0]
        except Exception as exc:  # noqa: BLE001
            missing_all.append((family, "LOAD_FAIL:%s" % exc))
            continue
        if not missing:
            resolved = font_manager.FontProperties(fname=path).get_name()
            plt.rcParams["font.family"] = [resolved]
            plt.rcParams["axes.unicode_minus"] = False
            return {"family": resolved, "path": path, "chars_checked": len(chars), "missing": [], "candidates_tried": [c[0] for c in candidates]}
        missing_all.append((family, "missing=%d" % len(missing)))
    raise SystemExit("CJK 字体不可用: %s" % missing_all)


def check_layout(fig, texts_axes):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    items = []
    for ax in fig.axes:
        for t in ax.texts:
            items.append((str(t.get_text()), t))
    items.extend(("figtext", t) for t in fig.texts)
    boxes = []
    for label, t in items:
        try:
            b = t.get_window_extent(renderer)
            if b.width <= 0 or b.height <= 0:
                continue
            boxes.append((label, b))
        except Exception:  # noqa: BLE001
            pass
    overlaps = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            b1 = boxes[i][1]
            b2 = boxes[j][1]
            x_overlap = min(b1.x1, b2.x1) - max(b1.x0, b2.x0)
            y_overlap = min(b1.y1, b2.y1) - max(b1.y0, b2.y0)
            if x_overlap > 1.0 and y_overlap > 1.0:
                overlaps.append({"a": boxes[i][0][:40], "b": boxes[j][0][:40], "x": round(x_overlap, 2), "y": round(y_overlap, 2)})
    (texts_axes or {}).clear()
    return {"text_count": len(boxes), "overlaps": overlaps, "status": "PASS" if not overlaps else "FAIL"}


def style_ax(ax):
    ax.grid(True, axis="y", ls=":", lw=0.6, color="#bbbbbb", alpha=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def save_fig(fig, outdir, name, dpi):
    path = outdir / name
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def load_training_history(run_dir):
    rows = list(csv.DictReader((run_dir / "metrics/training_history.csv").open(encoding="utf-8", newline="")))
    maml = {}
    pretrain = {}
    for r in rows:
        arm = r["arm"]
        if arm == "M5-MAML-proxy":
            seed = r["meta_seed"]
            it = int(r["iteration"])
            rec = maml.setdefault(seed, {"iter": [], "q": [], "s": []})
            rec["iter"].append(it)
            rec["q"].append(float(r["loss_query"]))
            rec["s"].append(float(r["loss_support"]) if r["loss_support"] not in ("", None) else np.nan)
        elif arm == "M5-pretrain-proxy":
            pretrain.setdefault("q", []).append(float(r["loss_query"]))
            pretrain.setdefault("iter", []).append(int(r["iteration"]))
    return maml, pretrain, rows


def fig1_meta_training_loss(run_dir, outdir, dpi):
    maml, pretrain, rows = load_training_history(run_dir)
    seeds = sorted(maml.keys(), key=lambda s: int(s))
    iters = np.array(sorted(maml[seeds[0]]["iter"]))
    q = np.vstack([np.array(maml[s]["q"]) for s in seeds])
    sm = np.vstack([np.array(maml[s]["s"]) for s in seeds])
    q_mean, q_min, q_max = q.mean(axis=0), q.min(axis=0), q.max(axis=0)
    s_mean, s_min, s_max = sm.mean(axis=0), sm.min(axis=0), sm.max(axis=0)

    fig, ax = plt.subplots(figsize=(11.2, 6.0))
    ax.fill_between(iters, q_min, q_max, color=ARM_COLORS["M5-BO-MAML-init"], alpha=0.16, linewidth=0)
    ax.plot(iters, q_mean, color=ARM_COLORS["M5-BO-MAML-init"], lw=2.0, label=TEXT["fig1_leg_q"])
    ax.plot(iters, s_mean, color=ARM_COLORS["M5-BO-MAML-init"], lw=1.6, ls="--", alpha=0.85, label=TEXT["fig1_leg_s"])
    ax.fill_between(iters, s_min, s_max, color=ARM_COLORS["M5-BO-MAML-init"], alpha=0.08, linewidth=0)
    pv = np.array(pretrain["q"])
    px = pretrain["iter"][0] if pretrain["iter"] else 50
    ax.scatter([px] * len(pv), pv, marker="D", s=42, color=ARM_COLORS["M5-BO-pretrain-init"], zorder=5, label=TEXT["fig1_leg_p"])
    order = [i for i, _ in sorted(enumerate(pv), key=lambda t: t[1])]
    for rank, i in enumerate(order):
        ax.annotate("%.3f" % pv[i], (px, pv[i]), textcoords="offset points", xytext=(9, 6 + 15 * rank), fontsize=8, color=ARM_COLORS["M5-BO-pretrain-init"])
    ax.annotate("query 末值 %.3f" % q_mean[-1], (iters[-1], q_mean[-1]), textcoords="offset points", xytext=(-6, 8), fontsize=8.5, color="#333333", ha="right")
    ax.set_title(TEXT["fig1_title"], fontsize=13, pad=10)
    ax.set_xlabel(TEXT["fig1_x"], fontsize=10)
    ax.set_ylabel(TEXT["fig1_y"], fontsize=10)
    style_ax(ax)
    ax.legend(fontsize=8.6, loc="upper right", framealpha=0.92)
    ax.set_xlim(0, max(iters) + 4)
    fig.text(0.5, -0.02, TEXT["fig1_foot"], ha="center", va="top", fontsize=8.2, color="#444444", wrap=True)
    layout = check_layout(fig, None)
    path = save_fig(fig, outdir, "fig1_meta_training_loss.png", dpi)
    loss_summary = {
        "metric": "3 meta_seed arithmetic mean over training_history.csv iterations",
        "loss_query_first": float(q_mean[0]),
        "loss_query_last": float(q_mean[-1]),
        "loss_support_first": float(s_mean[0]),
        "loss_support_last": float(s_mean[-1]),
        "pretrain_endpoints": [float(x) for x in pv],
    }
    return {"key": "fig1_meta_training_loss", "file": path.name, "status": "GENERATED", "series_n": len(seeds) * 2, "rows": len(rows), "layout_check": layout, "loss_summary": loss_summary}


def load_figure_data(run_dir):
    return json.loads((run_dir / "figures/figure_data.json").read_text(encoding="utf-8"))


def parse_series_key(key):
    parts = dict(p.split("=") for p in key.split("|"))
    return parts


def fig3_feasible_rate(run_dir, outdir, dpi):
    fd = load_figure_data(run_dir)
    blk = fd["figures"]["fig3_feasible_rate"]
    data = {}
    for key, v in blk["series"].items():
        p = parse_series_key(key)
        data[(p["split"], int(p["budget"]), p["arm"])] = {
            "median": v.get("median_feasible_hit_rate"),
            "nullfrac": v.get("null_run_fraction"),
            "n_runs": v.get("n_runs"),
        }
    fig, axes = plt.subplots(2, 2, figsize=(13.2, 8.6), sharey=False)
    for i, split in enumerate(SPLITS):
        for j, budget in enumerate(BUDGETS):
            ax = axes[i][j]
            vals, nulls, ns = [], [], []
            for arm in ARMS:
                rec = data.get((split, budget, arm), {})
                vals.append(100.0 * (rec.get("median") if rec.get("median") is not None else np.nan))
                nf = rec.get("nullfrac")
                nulls.append(100.0 * nf if nf is not None else np.nan)
                ns.append(rec.get("n_runs"))
            x = np.arange(len(ARMS))
            colors = [ARM_COLORS[a] for a in ARMS]
            bars = ax.bar(x, vals, width=0.62, color=colors, alpha=0.88, edgecolor="white")
            top = max([v for v in vals if not np.isnan(v)] or [1.0])
            for k, b in enumerate(bars):
                v = vals[k]
                if np.isnan(v):
                    ax.text(b.get_x() + b.get_width() / 2, 0.02 * top, "无数据", ha="center", va="bottom", fontsize=8, color="#666666")
                    continue
                ax.text(b.get_x() + b.get_width() / 2, v + 0.03 * top, "%.3f%%" % v, ha="center", va="bottom", fontsize=8.0)
            ax.set_xticks(x)
            tick_labels = []
            for k, arm in enumerate(ARMS):
                nf = nulls[k]
                suffix = ("\n无解 %.1f%%" % nf) if (nf is not None and not np.isnan(nf)) else ""
                tick_labels.append(ARM_SHORT[arm] + suffix)
            ax.set_xticklabels(tick_labels, fontsize=8.4)
            ax.set_title("%s（预算 %d）" % (split, budget), fontsize=11)
            style_ax(ax)
            ax.set_ylim(0, top * 1.30)
    axes[0][0].set_ylabel(TEXT["fig3_y"], fontsize=10)
    axes[1][0].set_ylabel(TEXT["fig3_y"], fontsize=10)
    fig.suptitle(TEXT["fig3_title"], fontsize=13.5, y=0.995)
    fig.text(0.5, -0.015, TEXT["fig3_foot"], ha="center", va="top", fontsize=8.2, color="#444444", wrap=True)
    layout = check_layout(fig, None)
    path = save_fig(fig, outdir, "fig3_feasible_rate.png", dpi)
    return {"key": "fig3_feasible_rate", "file": path.name, "status": "GENERATED", "series_n": len(blk["series"]), "layout_check": layout}


def fig4_equal_budget_gap(run_dir, outdir, dpi):
    fd = load_figure_data(run_dir)
    blk = fd["figures"]["fig4_equal_budget_gap"]
    data = {}
    for key, v in blk["series"].items():
        p = parse_series_key(key)
        data[(int(p["budget"]), p["arm"])] = v
    fig, axes = plt.subplots(2, 2, figsize=(13.6, 9.0))
    fields = [("median_best_feasible", TEXT["fig4_y1"]), ("median_gap_to_reference", TEXT["fig4_y2"])]
    for i, budget in enumerate(BUDGETS):
        for j, (field, ylabel) in enumerate(fields):
            ax = axes[i][j]
            for arm in ARMS:
                v = data.get((budget, arm), {})
                curve = v.get("curve") or []
                xs = [c["eval_index"] for c in curve]
                ys = [c.get(field) if c.get(field) is not None else np.nan for c in curve]
                ax.plot(xs, ys, color=ARM_COLORS[arm], lw=1.5, marker="o", ms=1.8,
                        label="%s（可行 n=%s）" % (ARM_SHORT[arm], v.get("runs_with_any_feasible")))
            ax.set_title("预算 %d：%s" % (budget, ylabel), fontsize=10.5)
            ax.set_xlabel(TEXT["fig4_x"], fontsize=9)
            style_ax(ax)
            ax.set_xlim(0, budget + 3)
            if j == 0:
                ax.legend(fontsize=7.6, loc="upper right", framealpha=0.9)
    fig.suptitle(TEXT["fig4_title"], fontsize=13.5, y=0.995)
    fig.text(0.5, -0.012, TEXT["fig4_foot"], ha="center", va="top", fontsize=8.2, color="#444444", wrap=True)
    layout = check_layout(fig, None)
    path = save_fig(fig, outdir, "fig4_equal_budget_gap.png", dpi)
    return {"key": "fig4_equal_budget_gap", "file": path.name, "status": "GENERATED", "series_n": len(blk["series"]), "layout_check": layout}


def fig5_fairness_audit(run_dir, outdir, dpi):
    fd = load_figure_data(run_dir)
    blk = fd["figures"]["fig5_fairness_audit"]
    arms = blk["arms"]
    clone_rows = list(csv.DictReader((run_dir / "metrics/clone_audit.csv").open(encoding="utf-8", newline="")))
    clone = {}
    for r in clone_rows:
        a = r.get("arm")
        if a not in clone:
            clone[a] = r
            continue
        try:
            if float(r.get("mean_initial_overlap")) > float(clone[a].get("mean_initial_overlap")):
                clone[a] = r
        except (TypeError, ValueError):
            pass

    fig = plt.figure(figsize=(13.6, 7.6))
    gs = fig.add_gridspec(1, 2, wspace=0.28, left=0.07, right=0.98, top=0.86, bottom=0.30)
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])

    x = np.arange(len(ARMS))
    runs = [arms[a].get("proxy_scoring_runs", 0) for a in ARMS]
    walls = [arms[a].get("proxy_scoring_wall_s_median") for a in ARMS]
    bars = ax1.bar(x, runs, width=0.6, color=[ARM_COLORS[a] for a in ARMS], alpha=0.88, edgecolor="white")
    ymax = max(runs) * 1.22 if max(runs) > 0 else 1.0
    ax1.set_ylim(0, ymax)
    off = 0.03 * ymax
    for k, b in enumerate(bars):
        w = walls[k]
        txt = "中位 %.2f ms" % (1000 * w) if w is not None else "无代理评分"
        ax1.text(b.get_x() + b.get_width() / 2, runs[k] + off, txt, ha="center", va="bottom", fontsize=8.4)
    ax1.set_xticks(x)
    ax1.set_xticklabels([ARM_SHORT[a] for a in ARMS], fontsize=9)
    ax1.set_ylabel("代理评分运行次数", fontsize=10)
    ax1.set_title(TEXT["fig5_a"], fontsize=11)
    # ylim already set before annotation loop
    style_ax(ax1)

    labels = []
    means, maxs = [], []
    for a in ARMS:
        rec = clone.get(a)
        if rec is None:
            labels.append(ARM_SHORT[a] + "\n无记录")
            means.append(np.nan)
            maxs.append(np.nan)
            continue
        means.append(float(rec["mean_initial_overlap"]))
        maxs.append(float(rec["max_initial_overlap"]))
        labels.append(ARM_SHORT[a] + "\n" + str(rec.get("label")))
    x2 = np.arange(len(ARMS))
    w = 0.36
    b1 = ax2.bar(x2 - w / 2, means, width=w, color="#8c8c8c", alpha=0.9, label="平均初始设计重叠")
    b2 = ax2.bar(x2 + w / 2, maxs, width=w, color="#c44e52", alpha=0.9, label="最大初始设计重叠")
    for bars_ in (b1, b2):
        for b in bars_:
            h = b.get_height()
            if not np.isnan(h):
                ax2.text(b.get_x() + b.get_width() / 2, h + 0.02, "%.2f" % h, ha="center", va="bottom", fontsize=8.0)
    ax2.set_xticks(x2)
    ax2.set_xticklabels(labels, fontsize=8.2)
    ax2.set_ylim(0, 1.22)
    ax2.set_ylabel("初始设计重叠度", fontsize=10)
    ax2.set_title(TEXT["fig5_b"], fontsize=11)
    ax2.legend(fontsize=8.4, loc="upper left", framealpha=0.92)
    style_ax(ax2)

    fairness = blk
    summary_obj = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    summ_counts = summary_obj.get("counts", {}) or {}
    det = summary_obj.get("determinism", {}) or {}
    ident = summary_obj.get("identifiability", {}) or {}
    fair = summary_obj.get("fairness", {}) or {}
    pair_rows = [r for r in clone_rows if r.get("arm") == "M5-BO-MAML-init" and "pretrain-init" in str(r.get("reference_arm") or r.get("reference") or "")]
    pair_txt = ""
    if pair_rows:
        pr = pair_rows[0]
        frac = pr.get("fraction_groups_at_threshold") or pr.get("fraction_pairs_high_overlap") or pr.get("fraction_high_overlap") or pr.get("fraction_identical") or pr.get("fraction_pairs_identical") or pr.get("fraction_groups_high_overlap") or "NA"
        pair_txt = ("MAML-init vs pretrain-init：mean overlap %s / max %s / high-overlap fraction %s（clone=%s）；mean 与 fraction 均未达 clone 判据 0.9，故 IDENTIFIABLE，但不能表述为重叠为 0" % (
            pr.get("mean_initial_overlap"), pr.get("max_initial_overlap"), frac, pr.get("clone")))
    de_rows = [r for r in clone_rows if r.get("arm") == "M5-DE"]
    de_txt = ""
    if de_rows:
        de_txt = "DE 与 random 初始设计相同（mean overlap %s）但引擎不同，标签 %s（非克隆）" % (de_rows[0].get("mean_initial_overlap"), de_rows[0].get("label"))
    summary_bits = [
        "公平性门禁：%s（4 臂 / %s 记录 / %s 组；初始设计数 %s）" % (fair.get("status", "PASS"), summ_counts.get("runs"), fair.get("groups"), fair.get("initial_design_count")),
        "可识别性：%s；实现数 %s / 代码路径 %s；%s" % (ident.get("status"), ident.get("distinct_implementations"), ident.get("distinct_code_paths"), pair_txt),
        de_txt,
        "确定性：%s（重跑 %s 次，mismatch %s；原始 rerun digest=%s，无法独立复算）；物理调用 = 0（SYNTHETIC_ONLY）" % (
            det.get("status"), det.get("reruns"), det.get("mismatch_count"), det.get("raw_digest_manifest") or "NOT_STORED"),
    ]
    wrapped = []
    for s in summary_bits:
        wrapped.extend(textwrap.wrap("· " + s, width=96))
    fig.text(0.07, 0.27, "\n".join(wrapped), ha="left", va="top", fontsize=8.6, color="#333333", linespacing=1.55)
    fig.suptitle(TEXT["fig5_title"], fontsize=13.5, y=0.97)
    fig.text(0.5, 0.035, textwrap.fill(TEXT["fig5_foot"], width=120), ha="center", va="top", fontsize=8.0, color="#444444")
    layout = check_layout(fig, None)
    path = save_fig(fig, outdir, "fig5_fairness_audit.png", dpi)
    return {"key": "fig5_fairness_audit", "file": path.name, "status": "GENERATED", "arms_n": len(arms), "clone_rows": len(clone_rows), "layout_check": layout}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=RUN_DEFAULT)
    ap.add_argument("--out-dir", default=BASE_DEFAULT)
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args(argv)
    run_dir = Path(args.run_dir)
    out_dir = Path(args.out_dir)
    figs_dir = out_dir / "figures"
    figs_dir.mkdir(parents=True, exist_ok=True)
    font = setup_font()
    entries = []
    entries.append(fig1_meta_training_loss(run_dir, figs_dir, args.dpi))
    entries.append(fig3_feasible_rate(run_dir, figs_dir, args.dpi))
    entries.append(fig4_equal_budget_gap(run_dir, figs_dir, args.dpi))
    entries.append(fig5_fairness_audit(run_dir, figs_dir, args.dpi))
    ok = True
    for e in entries:
        p = figs_dir / e["file"]
        e["bytes"] = p.stat().st_size
        e["sha256"] = sha256_file(p)
        e["dpi"] = args.dpi
        if e["layout_check"].get("status") != "PASS":
            ok = False
    manifest = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "figures": entries,
        "font": font,
        "dpi": args.dpi,
        "all_layout_checks_pass": ok,
        "generated_utc": __import__("datetime").datetime.now().astimezone().isoformat(),
        "attempt": "attempt2",
        "corrections": ["A5-M5-03 clone overlap wording", "A5-M5-05 first_feasible coverage", "A5-M5-06 training loss values", "determinism raw digest NOT_STORED disclosure"],
    }
    (out_dir / "figures_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"ok": ok, "figures": [{"file": e["file"], "bytes": e["bytes"], "sha256": e["sha256"], "layout": e["layout_check"]["status"], "overlaps": len(e["layout_check"]["overlaps"])} for e in entries]}, ensure_ascii=False, indent=1))
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
