# -*- coding: utf-8 -*-
from pathlib import Path
p = Path("C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/d12d005/a2/batch2_figures/gen_figures.py")
s = p.read_text(encoding="utf-8")
start = s.index("def fig5():")
end = s.index("def main():")
new = '''def fig5():
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


'''
s = s[:start] + new + s[end:]
p.write_text(s, encoding="utf-8", newline="\n")
print("patched fig5, size", len(s))
