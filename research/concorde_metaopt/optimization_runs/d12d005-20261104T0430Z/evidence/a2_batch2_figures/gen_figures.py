# -*- coding: utf-8 -*-
"""Generate Chinese 300 dpi figures for D-12D-005 Batch2 from verified evidence numbers (zero solver)."""
import hashlib
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch

BASE = Path("C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/d12d005/a2/batch2_figures")
FIG = BASE / "figures"
FIG.mkdir(parents=True, exist_ok=True)
REC = json.loads((BASE / "recompute.json").read_text(encoding="utf-8"))
CASES = ["S6_STD_M2p02_aoa1", "B2-01", "B2-02", "B2-03", "B2-04", "B2-05", "B2-06", "B2-07"]
SHORT = ["S6诊断", "B2-01", "B2-02", "B2-03", "B2-04", "B2-05", "B2-06", "B2-07"]
GROUP = ["diag", "dens", "dens", "dens", "pert", "pert", "pert", "rep"]
COLORS = {"diag": "#4C72B0", "dens": "#55A868", "pert": "#C44E52", "rep": "#8172B2"}
LABELS = {"diag": "S6 诊断带", "dens": "密度三件套", "pert": "单变量扰动", "rep": "重复性"}
FOOT = "VSPAERO_INTERNAL_ONLY；physical_validation=NOT_VALIDATED；内部一致性，非物理验证"
LAYOUT = {}


def setup_font():
    cands = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"]
    name = None
    for c in cands:
        p = Path(c)
        if p.exists():
            try:
                font_manager.fontManager.addfont(str(p))
                name = font_manager.FontProperties(fname=str(p)).get_name()
                break
            except Exception:
                continue
    if name is None:
        raise SystemExit("no CJK font found")
    plt.rcParams["font.family"] = name
    plt.rcParams["font.sans-serif"] = [name, "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return name


def check_layout(fig, axes, min_gap_px=2.0):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    texts = []
    seen = set()

    def add(t, src):
        if t is None:
            return
        try:
            s = t.get_text()
        except Exception:
            return
        if not s or not s.strip():
            return
        try:
            bb = t.get_window_extent(renderer)
        except Exception:
            return
        key = (round(bb.x0, 2), round(bb.y0, 2), round(bb.x1, 2), round(bb.y1, 2), s)
        if key in seen:
            return
        seen.add(key)
        texts.append({"text": s, "src": src, "bbox": [bb.x0, bb.y0, bb.x1, bb.y1]})

    for ax in axes:
        add(ax.title, "axes_title")
        add(ax.xaxis.label, "xlabel")
        add(ax.yaxis.label, "ylabel")
        for t in ax.texts:
            add(t, "annotation")
        leg = ax.get_legend()
        if leg is not None:
            for t in leg.get_texts():
                add(t, "legend")
    for t in fig.texts:
        add(t, "fig_text")
    overlaps = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i]["bbox"], texts[j]["bbox"]
            ix = min(a[2], b[2]) - max(a[0], b[0])
            iy = min(a[3], b[3]) - max(a[1], b[1])
            if ix > min_gap_px and iy > min_gap_px:
                overlaps.append({"a": texts[i]["text"], "b": texts[j]["text"], "ix": round(ix, 2), "iy": round(iy, 2)})
    fb = fig.get_window_extent(renderer)
    outside = []
    for t in texts:
        bb = t["bbox"]
        if bb[0] < fb.x0 - 2 or bb[1] < fb.y0 - 2 or bb[2] > fb.x1 + 2 or bb[3] > fb.y1 + 2:
            outside.append({"text": t["text"], "src": t["src"]})
    return {"n_texts": len(texts), "overlaps": overlaps, "outside": outside,
            "ok": len(overlaps) == 0 and len(outside) == 0}


def save(fig, name, check_axes):
    check = check_layout(fig, check_axes)
    p = FIG / name
    fig.savefig(p, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    data = p.read_bytes()
    LAYOUT[name] = check
    return {"file": name, "path": str(p), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "width_px": None, "height_px": None, "layout_check": check}


def fig1():
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.4), gridspec_kw={"width_ratios": [1.0, 1.15]})
    ax = axes[0]
    used, cap = 14, 20
    ax.barh(["A 类启动配额"], [used], color="#4C72B0", height=0.5, label="已用 14")
    ax.barh(["A 类启动配额"], [cap - used], left=[used], color="#DDDDDD", height=0.5, label="剩余 6（关闭，未授权）")
    ax.set_xlim(0, cap + 2)
    ax.set_xlabel("启动次数")
    ax.set_title("(a) A 类预算：已用 14 / 上限 20")
    ax.text(used / 2, 0, "14\n(70%)", ha="center", va="center", fontsize=11, color="white", fontweight="bold")
    ax.text(used + (cap - used) / 2, 0, "6\nNOT_AUTHORIZED", ha="center", va="center", fontsize=9, color="#555555")
    ax.legend(loc="lower right", fontsize=8, framealpha=0.9)
    ax = axes[1]
    comp = {"S6 诊断带": 1, "密度三件套": 3, "单变量扰动": 3, "重复性": 1}
    xs = list(comp.keys())
    ys = [comp[k] for k in xs]
    bars = ax.bar(xs, ys, color=["#4C72B0", "#55A868", "#C44E52", "#8172B2"], width=0.6)
    for b, y in zip(bars, ys):
        ax.text(b.get_x() + b.get_width() / 2, y + 0.06, "%d 次" % y, ha="center", va="bottom", fontsize=10)
    ax.set_ylim(0, max(ys) + 0.9)
    ax.set_ylabel("启动次数")
    ax.set_title("(b) 本批 8 次启动构成（共 8 starts / 0 retry）")
    ax.grid(axis="y", alpha=0.25)
    fig.suptitle("图1  D-12D-005 Batch2 预算与批次构成", fontsize=14)
    fig.text(0.5, 0.015, FOOT, ha="center", va="bottom", fontsize=8, color="#444444")
    fig.tight_layout(rect=[0, 0.05, 1, 0.93])
    return save(fig, "fig1_budget_and_scope.png", axes)


def fig2():
    fig, axes = plt.subplots(3, 1, figsize=(12.6, 10.2), sharex=True)
    metrics = [("CLtot", "CLtot（总升力系数）", "%.6f"), ("CDi", "CDi（诱导阻力系数）", "%.6f"), ("CDtot", "CDtot（内部总阻力系数）", "%.6f")]
    for ax, (key, title, fmt) in zip(axes, metrics):
        vals = [REC["cases"][c][key] for c in CASES]
        cols = [COLORS[g] for g in GROUP]
        bars = ax.bar(SHORT, vals, color=cols, width=0.62)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, fmt % v, ha="center", va="bottom", fontsize=7.2, rotation=90)
        ax.set_ylabel(title)
        ax.grid(axis="y", alpha=0.25)
        ax.set_ylim(0, max(vals) * 1.22)
    axes[2].set_xlabel("案件（按执行顺序；颜色：蓝=诊断带，绿=密度三件套，红=单变量扰动，紫=重复性）")
    handles = [Patch(facecolor=COLORS[k], label=LABELS[k]) for k in ("diag", "dens", "pert", "rep")]
    axes[0].legend(handles=handles, loc="upper right", fontsize=8, framealpha=0.9)
    fig.suptitle("图2  Batch2 八案内部系数对比（VSPAERO thin-LF，Mach 2.02）", fontsize=14)
    fig.text(0.5, 0.012, FOOT, ha="center", va="bottom", fontsize=8, color="#444444")
    fig.tight_layout(rect=[0, 0.04, 1, 0.95])
    return save(fig, "fig2_case_coefficients.png", axes)


def fig3():
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.4))
    d = REC["deltas"]
    ax = axes[0]
    tess = ["Tess 3/3\n(B2-01)", "Tess 6/6\n(B2-02)", "Tess 12/12\n(B2-03)"]
    cdi = [REC["cases"]["B2-01"]["CDi"], REC["cases"]["B2-02"]["CDi"], REC["cases"]["B2-03"]["CDi"]]
    bars = ax.bar(tess, cdi, color=["#A6D8A8", "#55A868", "#2E6B3A"], width=0.55)
    for b, v in zip(bars, cdi):
        ax.text(b.get_x() + b.get_width() / 2, v, "%.6f" % v, ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("CDi（内部诱导阻力系数）")
    ax.set_title("(a) 密度三件套 CDi 绝对值")
    ax.set_ylim(0, max(cdi) * 1.2)
    ax.grid(axis="y", alpha=0.25)
    ax = axes[1]
    cats = ["Tess 3/3 → 6/6", "Tess 6/6 → 12/12"]
    series = [("CLtot", [d["density_3_to_6"]["CLtot_pct"], d["density_6_to_12"]["CLtot_pct"]], "#4C72B0"),
              ("CDi", [d["density_3_to_6"]["CDi_pct"], d["density_6_to_12"]["CDi_pct"]], "#55A868"),
              ("CDtot", [d["density_3_to_6"]["CDtot_pct"], d["density_6_to_12"]["CDtot_pct"]], "#C44E52")]
    x = range(len(cats))
    w = 0.26
    for i, (name, vals, col) in enumerate(series):
        pos = [xi + (i - 1) * w for xi in x]
        bars = ax.bar(pos, vals, width=w, color=col, label=name)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + (0.12 if v >= 0 else -0.12), "%+.2f%%" % v,
                    ha="center", va="bottom" if v >= 0 else "top", fontsize=8.5)
    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats)
    ax.set_ylabel("相对变化 / %")
    ax.set_title("(b) 相邻面元密度相对变化")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(axis="y", alpha=0.25)
    fig.suptitle("图3  密度敏感性（仅 SectTess_U 不同，同 12D 合同；内部一致性）", fontsize=14)
    fig.text(0.5, 0.015, FOOT, ha="center", va="bottom", fontsize=8, color="#444444")
    fig.tight_layout(rect=[0, 0.05, 1, 0.93])
    return save(fig, "fig3_density_sensitivity.png", axes)


def fig4():
    fig, ax = plt.subplots(figsize=(12.2, 5.6))
    d = REC["deltas"]
    cats = ["B2-04 W01 翼面积 +5%", "B2-05 W03 后掠 67°→69°", "B2-06 W10 扭转 0°→2°"]
    keys = ["B2-04", "B2-05", "B2-06"]
    series = [("CLtot", "#4C72B0"), ("CDi", "#55A868"), ("CDtot", "#C44E52")]
    x = range(len(cats))
    w = 0.25
    for i, (m, col) in enumerate(series):
        vals = [d[k][m + "_pct"] for k in keys]
        pos = [xi + (i - 1) * w for xi in x]
        bars = ax.bar(pos, vals, width=w, color=col, label=m)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + (0.12 if v >= 0 else -0.12), "%+.2f%%" % v,
                    ha="center", va="bottom" if v >= 0 else "top", fontsize=8.5)
    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats, fontsize=10)
    ax.set_ylabel("相对 B2-03 基线变化 / %")
    ax.set_title("图4  单变量扰动相对 B2-03 基线的内部系数变化（非物理验证）", fontsize=13)
    ax.legend(fontsize=9, loc="upper right")
    ax.grid(axis="y", alpha=0.25)
    ax.set_ylim(min(-4.0, min(d[k][m + "_pct"] for k in keys for m in ("CLtot", "CDi", "CDtot")) - 1.0),
                max(d[k][m + "_pct"] for k in keys for m in ("CLtot", "CDi", "CDtot")) + 1.6)
    fig.text(0.5, 0.015, FOOT, ha="center", va="bottom", fontsize=8, color="#444444")
    fig.tight_layout(rect=[0, 0.05, 1, 1])
    return save(fig, "fig4_perturbation_delta.png", [ax])


def fig5():
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.8), gridspec_kw={"width_ratios": [1.0, 1.15]})
    fig.subplots_adjust(left=0.08, right=0.98, top=0.85, bottom=0.17, wspace=0.32)
    b, r = REC["cases"]["B2-03"], REC["cases"]["B2-07"]
    d = REC["deltas"]["B2-07"]
    ax = axes[0]
    metrics = ["CLtot", "CDi", "CDtot"]
    ratios = [r[m] / b[m] for m in metrics]
    bars = ax.bar(metrics, ratios, color=["#4C72B0", "#55A868", "#C44E52"], width=0.5)
    for bar, ratio in zip(bars, ratios):
        ax.text(bar.get_x() + bar.get_width() / 2, ratio, "%.9f" % ratio, ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0.99955, 1.00005)
    ax.set_ylabel("B2-07 / B2-03（归一化比值）")
    ax.set_title("(a) 重复性：同几何同合同的系数比值")
    ax.grid(axis="y", alpha=0.25)
    ax = axes[1]
    names = ["ΔCLtot", "ΔCDi", "ΔCDtot"]
    deltas = [d["CLtot"], d["CDi"], d["CDtot"]]
    bars = ax.barh(names, deltas, color=["#4C72B0", "#55A868", "#C44E52"], height=0.5)
    ax.axvline(0, color="#333333", linewidth=0.8)
    for bar, v in zip(bars, deltas):
        ax.annotate("%+.3e" % v, xy=(v, bar.get_y() + bar.get_height() / 2), xytext=(8, 0),
                    textcoords="offset points", va="center", ha="left", fontsize=9)
    ax.set_xlabel("B2-07 与 B2-03 的绝对差（内部系数）")
    ax.set_title("(b) 重复性：绝对差（1e-7 量级）")
    ax.grid(axis="x", alpha=0.25)
    ax.set_xlim(-1.5e-6, 0.45e-6)
    fig.suptitle("图5  重复性检查（B2-07 重复 B2-03；仅说明内部可重复，不代表物理精度）", fontsize=12.5, y=0.96)
    fig.text(0.5, 0.025, FOOT, ha="center", va="bottom", fontsize=8, color="#444444")
    return save(fig, "fig5_repeatability.png", axes)


def main():
    name = setup_font()
    figs = [fig1(), fig2(), fig3(), fig4(), fig5()]
    manifest = {
        "schema_version": "d12d005-batch2-figures-1",
        "font_family": name,
        "dpi": 300,
        "figures": figs,
        "layout_checks_all_ok": all(f["layout_check"]["ok"] for f in figs),
        "note": "All numbers from recompute.json (recomputed from raw VSPAERO polar evidence); zero solver; VSPAERO_INTERNAL_ONLY / NOT_VALIDATED.",
    }
    (BASE / "figures_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"font": name, "figures": [(f["file"], f["bytes"]) for f in figs],
                      "all_layout_ok": manifest["layout_checks_all_ok"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
