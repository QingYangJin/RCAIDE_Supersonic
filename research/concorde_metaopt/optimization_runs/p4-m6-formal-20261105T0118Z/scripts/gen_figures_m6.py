
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A2 M6 figures: 3 Chinese 300dpi figures from P4-M6 formal run artifacts (read-only)."""
import csv, json, hashlib, os, sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
import numpy as np

RUN = r"D:/RCAIDE-p4-meta-learning/research/concorde_metaopt/optimization_runs/p4-m6-formal-20261105T0118Z"
OUT = r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/p4-m5m6/a2/m6_figures_report"
FIGDIR = os.path.join(OUT, "figures")
os.makedirs(FIGDIR, exist_ok=True)
DPI = 300
VERSION = "1.0.0"

TEXT = {
    "fig2_title": "图2  K-shot 快速适应误差（rmse_norm，中位数与 95% CI）",
    "fig2_x": "adaptation 步数 K（support 样本数）",
    "fig2_y": "任务内标准化 RMSE（rmse_norm）",
    "panel_in_dist": "同分布（meta_test）",
    "panel_ood": "OOD 参数外推（meta_test_ood）",
    "panel_lin": "新函数族 F-LIN",
    "panel_mf": "新函数族 F-MF",
    "arm_M": "M：MAML 一阶元学习",
    "arm_P": "P：监督预训练 + 微调",
    "arm_R": "R：随机初始化",
    "fig2_foot": "合成解析任务；physical_call_count = 0，无真实物理数据。误差棒为发布值中的 95% 置信区间；K=0 表示无 support 适配。",
    "fig6_title": "图6  OOD 诊断与负控制（不构成泛化结论）",
    "fig6_a_title": "OOD 难度匹配：相对差异（容差 ±20%）",
    "fig6_a_y": "OOD 相对 in-dist 差异（%）",
    "fig6_b_title": "K=5 配对差（MAML M 相对基线；负值仅表示误差更低）",
    "fig6_b_x": "均值差（rmse_norm，95% CI）",
    "fig6_c_title": "负控制：NC1 label-shuffle / NC2 K=0",
    "fig6_c_y": "测试指标值",
    "fig6_foot": "H1 难度混杂 = CONFOUND_SUSPECTED，difficulty_matching = POOR_MATCH，attribution = CONFOUNDED，conclusion_allowed = false。合成任务；physical_call_count = 0。",
    "fig7_title": "图7  K 扫描下的配对差（rmse_norm，均值差与 95% CI）",
    "fig7_x": "support 样本数 K",
    "fig7_y": "均值差（rmse_norm）",
    "fig7_foot": "M−R 与 P−R 为任务层级配对均值差；负值仅表示误差更低，不等价于统计显著或 BO 样本效率。\nK=5 主比较中 MAML 相对预训练无显著优势；K=0 时 M/P 显著优于 R 仅反映初始化差异，不代表快速适应优势（* 表示 reject_holm=true）。合成任务；physical_call_count = 0。",
    "mr": "M−R（MAML vs 随机）",
    "pr": "P−R（预训练 vs 随机）",
    "zero": "无差异线",
    "nc1_in": "in-dist 优势",
    "nc1_nc": "负控制优势",
    "nc2_M": "M",
    "nc2_P": "P",
    "nc2_R": "R",
    "signif": "*",
    "not_signif": "（无显著 MAML 优势）",
}

COLORS = {"M": "#1f4e9c", "P": "#c44e00", "R": "#4d4d4d"}
STUDY_COLORS = {"in_dist": "#1f4e9c", "ood": "#c44e00", "F-LIN": "#2e7d32", "F-MF": "#6a1b9a"}

def load_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b: break
            h.update(b)
    return h.hexdigest()

def setup_font():
    cands = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc"]
    all_text = "".join(str(v) for v in TEXT.values())
    chars = sorted(set(ch for ch in all_text if ord(ch) > 127))
    for c in cands:
        if os.path.exists(c):
            font_manager.fontManager.addfont(c)
            fam = font_manager.FontProperties(fname=c).get_name()
            try:
                from matplotlib.ft2font import FT2Font
                ft = FT2Font(c)
                cmap = ft.get_charmap()
                missing = [ch for ch in chars if ord(ch) not in cmap]
            except Exception:
                missing = []
            if not missing:
                plt.rcParams["font.family"] = fam
                plt.rcParams["axes.unicode_minus"] = False
                return {"family": fam, "path": c, "chars_checked": len(chars), "missing": []}
    raise RuntimeError("no usable Chinese font found")

def layout_check(fig, axes):
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    texts = []
    seen = set()
    for ax in axes:
        for t in ax.texts:
            if id(t) in seen: continue
            seen.add(id(t)); texts.append((t.get_text(), t.get_window_extent(rend)))
    for t in fig.texts:
        if id(t) in seen: continue
        seen.add(id(t)); texts.append((t.get_text(), t.get_window_extent(rend)))
    overlaps = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i][1], texts[j][1]
            if a.overlaps(b):
                ix = min(a.x1, b.x1) - max(a.x0, b.x0)
                iy = min(a.y1, b.y1) - max(a.y0, b.y0)
                if ix > 1 and iy > 1:
                    overlaps.append({"a": texts[i][0][:30], "b": texts[j][0][:30], "ix": ix, "iy": iy})
    fb = fig.bbox
    outside = []
    for txt, bb in texts:
        if bb.x0 < fb.x0 - 1 or bb.y0 < fb.y0 - 1 or bb.x1 > fb.x1 + 1 or bb.y1 > fb.y1 + 1:
            outside.append(txt[:30])
    return {"status": "PASS" if not overlaps and not outside else "FAIL",
            "n_texts": len(texts), "n_overlaps": len(overlaps), "overlaps": overlaps, "outside": outside}

def save(fig, name, meta):
    path = os.path.join(FIGDIR, name)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    rec = {"file": name, "path": path, "bytes": os.path.getsize(path), "sha256": sha256_file(path), "dpi": DPI}
    rec.update(meta)
    return rec

summary = json.load(open(os.path.join(RUN, "summary.json"), encoding="utf-8"))
asu = load_rows(os.path.join(RUN, "metrics", "adaptation_summary.csv"))
stat = load_rows(os.path.join(RUN, "metrics", "statistics.csv"))
font_info = setup_font()

# index adaptation_summary
asu_idx = {}
for r in asu:
    asu_idx[(r["study"], r["source_family"], r["arm"], int(r["K"]), r["metric"])] = r

KS = [0, 1, 5, 10, 20]
records = []

def fig2_kshot():
    panels = [("in_dist", "F-QE-feasible-v2", TEXT["panel_in_dist"]),
              ("ood", "F-QE-feasible-v2", TEXT["panel_ood"]),
              ("new_family", "F-LIN", TEXT["panel_lin"]),
              ("new_family", "F-MF", TEXT["panel_mf"])]
    fig, axes = plt.subplots(2, 2, figsize=(11.0, 8.2))
    axes = axes.ravel()
    for ax, (study, fam, title) in zip(axes, panels):
        for arm in ("M", "P", "R"):
            xs = []; ys = []; lo = []; hi = []
            for K in KS:
                r = asu_idx.get((study, fam, arm, K, "rmse_norm"))
                if r is None or r["status"] != "VALID": continue
                xs.append(K); ys.append(float(r["median"])); lo.append(float(r["ci_low"])); hi.append(float(r["ci_high"]))
            if not xs: continue
            yerr = [[max(0.0, y - l) for y, l in zip(ys, lo)], [max(0.0, h - y) for y, h in zip(ys, hi)]]
            ax.errorbar(xs, ys, yerr=yerr, marker="o", markersize=4.0, linewidth=1.6, capsize=3,
                        color=COLORS[arm], label=TEXT["arm_" + arm])
        ax.set_title(title, fontsize=10.5)
        ax.set_xlabel(TEXT["fig2_x"], fontsize=9)
        ax.set_ylabel(TEXT["fig2_y"], fontsize=9)
        ax.set_xticks(KS)
        ax.grid(True, alpha=0.25)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=3, fontsize=9, frameon=False, bbox_to_anchor=(0.5, 0.945))
    fig.suptitle(TEXT["fig2_title"], fontsize=13.5, y=0.995)
    fig.text(0.5, 0.005, TEXT["fig2_foot"], ha="center", va="bottom", fontsize=8, color="#555555")
    fig.subplots_adjust(left=0.07, right=0.985, top=0.86, bottom=0.11, hspace=0.32, wspace=0.20)
    lc = layout_check(fig, list(axes))
    return save(fig, "fig2_K_shot_rmse.png", {"key": "fig2_k_shot_rmse", "layout_check": lc})

def fig6_ood_nc():
    ood = summary["ood_diagnostics"]
    checks = {c["id"]: c for c in ood["checks"]}
    dm = ood["difficulty_matching"]
    fig = plt.figure(figsize=(12.2, 5.2))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.0, 1.35, 0.95], wspace=0.42)
    ax1 = fig.add_subplot(gs[0, 0]); ax2 = fig.add_subplot(gs[0, 1]); ax3 = fig.add_subplot(gs[0, 2])
    # (a) difficulty matching relative differences
    ev = checks["H1"]["evidence"]
    keys = ["query_objective_std", "mean_curvature", "radius", "support_objective_std"]
    labels = ["query 目标\n标准差", "平均曲率", "半径", "support 目标\n标准差"]
    vals = [ev[k]["relative_difference"] * 100.0 for k in keys]
    colors = ["#c44e00" if abs(v) > 20.0 else "#4d7fbf" for v in vals]
    ax1.barh(range(len(keys)), vals, color=colors, height=0.55)
    ax1.axvline(0, color="#333333", linewidth=1.0)
    ax1.axvline(20, color="#999999", linestyle="--", linewidth=1.0)
    ax1.axvline(-20, color="#999999", linestyle="--", linewidth=1.0)
    ax1.set_yticks(range(len(keys))); ax1.set_yticklabels(labels, fontsize=8.5)
    ax1.set_xlabel(TEXT["fig6_a_y"], fontsize=9)
    ax1.set_title(TEXT["fig6_a_title"] + "\nH1 = " + checks["H1"]["status"] + "；匹配 = " + dm["status"], fontsize=9.2)
    ax1.grid(True, axis="x", alpha=0.25)
    # (b) forest plot
    rows = [r for r in stat if r["K"] == "5" and r["metric"] == "rmse_norm"]
    tags = {"in_dist": "同分布", "ood": "OOD", "F-LIN": "F-LIN", "F-MF": "F-MF", "negative_control": "负控制"}
    items = []
    for r in rows:
        fam = r["source_family"] if r["study"] == "new_family" else ""
        label = tags.get(fam or r["study"], r["study"]) + "  " + r["arm"] + "−" + r["reference"]
        items.append((label, float(r["mean_diff"]), float(r["ci_low"]), float(r["ci_high"]), float(r["p_holm"]), r["reject_holm"], r["study"]))
    items = items[::-1]
    ys = list(range(len(items)))
    for y, (label, md, lo, hi, ph, rej, study) in zip(ys, items):
        color = STUDY_COLORS.get(label.split("  ")[0], "#4d4d4d")
        ax2.errorbar([md], [y], xerr=[[max(0.0, md - lo)], [max(0.0, hi - md)]], fmt="o", markersize=4,
                     color=color, capsize=3, linewidth=1.4)
        mark = TEXT["signif"] if rej == "true" else ""
        ax2.text(hi + 0.004, y, "p_holm=%.3g%s" % (ph, mark), va="center", fontsize=6.4, color="#444444")
    ax2.axvline(0, color="#333333", linewidth=1.0)
    ax2.set_yticks(ys); ax2.set_yticklabels([it[0] for it in items], fontsize=7.2)
    ax2.set_xlabel(TEXT["fig6_b_x"], fontsize=9)
    ax2.set_title(TEXT["fig6_b_title"], fontsize=9.2)
    ax2.set_xlim(min(it[2] for it in items) - 0.012, max(it[3] for it in items) + 0.055)
    ax2.grid(True, axis="x", alpha=0.25)
    # (c) negative control
    nc = summary["negative_control"]
    nc1 = [c for c in nc["checks"] if c["id"] == "NC1"][0]["evidence"]
    nc2 = [c for c in nc["checks"] if c["id"] == "NC2"][0]["evidence"]
    groups = np.arange(3)
    width = 0.36
    ax3.bar(groups - width / 2, [nc1["in_dist_advantage_rmse_norm"], nc2["k0_rmse_norm_M"], 0.0],
            width=width, color="#1f4e9c", label="NC1 in-dist 优势 / NC2 K=0 M")
    ax3.bar(groups + width / 2, [nc1["negative_control_advantage_rmse_norm"], nc2["k0_rmse_norm_P"], 0.0],
            width=width, color="#c44e00", label="NC1 负控制优势 / NC2 K=0 P")
    ax3.axhline(0, color="#333333", linewidth=1.0)
    ax3.set_xticks(groups)
    ax3.set_xticklabels(["NC1\nin-dist/负控制", "NC2\nM/P", "NC2\nR 基准"], fontsize=7.6)
    ax3.set_ylabel(TEXT["fig6_c_y"], fontsize=9)
    ax3.set_title(TEXT["fig6_c_title"] + "\n负控制 = " + nc["status"], fontsize=9.2)
    ax3.text(0, max(nc1["in_dist_advantage_rmse_norm"], 0.01) + 0.02, "shrink=%.2f" % nc1["shrink_fraction"],
             ha="center", fontsize=6.8, color="#333333")
    ax3.grid(True, axis="y", alpha=0.25)
    handles = [Patch(color="#1f4e9c", label="NC1 in-dist 优势 / NC2 K=0 M"),
               Patch(color="#c44e00", label="NC1 负控制优势 / NC2 K=0 P"),
               Patch(color="#4d4d4d", label="NC2 K=0 R = %.3f" % nc2["k0_rmse_norm_R"])]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=7.4, frameon=False, bbox_to_anchor=(0.5, 0.005))
    fig.suptitle(TEXT["fig6_title"], fontsize=13.0, y=0.985)
    fig.text(0.5, 0.908, TEXT["fig6_foot"], ha="center", va="bottom", fontsize=7.4, color="#555555")
    fig.subplots_adjust(left=0.13, right=0.985, top=0.845, bottom=0.16)
    lc = layout_check(fig, [ax1, ax2, ax3])
    return save(fig, "fig6_ood_negative_control.png", {"key": "fig6_ood_negative_control", "layout_check": lc})

def fig7_ksweep():
    panels = [("in_dist", None, TEXT["panel_in_dist"]), ("ood", None, TEXT["panel_ood"]),
              ("new_family", "F-LIN", TEXT["panel_lin"]), ("new_family", "F-MF", TEXT["panel_mf"])]
    fig, axes = plt.subplots(2, 2, figsize=(11.0, 8.2))
    axes = axes.ravel()
    for ax, (study, fam, title) in zip(axes, panels):
        # series M-R and P-R
        for series, color, ls, label in [("MR", "#1f4e9c", "-", TEXT["mr"]), ("PR", "#c44e00", "--", TEXT["pr"])]:
            xs = []; ys = []; lo = []; hi = []; marks = []
            for K in KS:
                hit = None
                for r in stat:
                    if r["study"] != study or r["metric"] != "rmse_norm" or int(r["K"]) != K: continue
                    if fam is not None and r["source_family"] != fam: continue
                    if series == "MR" and r["arm"] == "M" and r["reference"] == "R": hit = r
                    if series == "PR" and r["arm"] == "P" and r["reference"] == "R": hit = r
                if hit is None: continue
                xs.append(K); ys.append(float(hit["mean_diff"])); lo.append(float(hit["ci_low"])); hi.append(float(hit["ci_high"]))
                marks.append(hit["reject_holm"] == "true")
            if not xs: continue
            yerr = [[max(0.0, y - l) for y, l in zip(ys, lo)], [max(0.0, h - y) for y, h in zip(ys, hi)]]
            ax.errorbar(xs, ys, yerr=yerr, marker="o", markersize=4.0, linewidth=1.5, capsize=3, color=color, linestyle=ls, label=label)
            for x, y, mk in zip(xs, ys, marks):
                if mk:
                    ax.annotate(TEXT["signif"], (x, y), textcoords="offset points", xytext=(5, 6), fontsize=10, color="#8b1a1a")
        ax.axhline(0, color="#333333", linewidth=1.0)
        ax.set_title(title, fontsize=10.5)
        ax.set_xlabel(TEXT["fig7_x"], fontsize=9)
        ax.set_ylabel(TEXT["fig7_y"], fontsize=9)
        ax.set_xticks(KS)
        ax.grid(True, alpha=0.25)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=2, fontsize=9, frameon=False, bbox_to_anchor=(0.5, 0.945))
    fig.suptitle(TEXT["fig7_title"], fontsize=13.5, y=0.995)
    fig.text(0.5, 0.005, TEXT["fig7_foot"], ha="center", va="bottom", fontsize=7.6, color="#555555")
    fig.subplots_adjust(left=0.075, right=0.985, top=0.86, bottom=0.11, hspace=0.32, wspace=0.21)
    lc = layout_check(fig, list(axes))
    return save(fig, "fig7_k_sweep_delta.png", {"key": "fig7_k_sweep_delta", "layout_check": lc})

records.append(fig2_kshot())
records.append(fig6_ood_nc())
records.append(fig7_ksweep())

manifest = {
    "schema_version": 1,
    "artifact_kind": "A2_M6_FIGURES",
    "run_id": summary["run_id"],
    "run_dir": RUN,
    "generator": "scripts/gen_figures_m6.py",
    "generator_sha256": sha256_file(os.path.abspath(__file__)),
    "version": VERSION,
    "solver_starts": 0,
    "repo_writes": 0,
    "dpi": DPI,
    "font": font_info,
    "figures": records,
    "all_layout_checks_pass": all(r["layout_check"]["status"] == "PASS" for r in records),
    "n_figures": len(records),
    "physical_call_count_source": summary["physical_call_count"],
    "notes": ["仅使用 run 目录 metrics/*.csv 与 summary.json / ood_diagnostics / negative_control；",
              "未重算或伪造任何数值；K-shot 图使用 adaptation_summary 的 group_mean 行（median 与 95% CI 为发布值）；",
              "fig6/fig7 使用 statistics.csv 的 K=5 / 全 K 行（mean_diff 与 95% CI 为发布值）；",
              "结论禁止表述为 MAML 优越或等价；OOD 方向因 CONFOUNDED 不得作为泛化结论。"],
}
with open(os.path.join(OUT, "figures_manifest.json"), "w", encoding="utf-8", newline="\n") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print(json.dumps({"n_figures": manifest["n_figures"], "all_layout_checks_pass": manifest["all_layout_checks_pass"],
                  "font": font_info["family"], "figures": [{"file": r["file"], "bytes": r["bytes"], "sha256": r["sha256"],
                  "layout": r["layout_check"]["status"], "n_texts": r["layout_check"]["n_texts"],
                  "n_overlaps": r["layout_check"]["n_overlaps"]} for r in records]}, ensure_ascii=False))
