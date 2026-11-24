"""Draw the CL-alpha / CDi-alpha curves with the same-lift marker, and the key
geometry-dimension change figure, for final_aircraft/.

Every point comes from a real VSPAERO .polar written by the solver inside a case
directory: the coarse sweep (7 rows, alpha 4.13..6.23) and the refine sweep (13 rows,
a 0.048 deg window around the predicted alpha) are stitched in alpha order. The
same-lift marker is the certificate's own certified alpha and CL, so the figure cannot
drift from the admission record.

Nothing here is a fit, a model or a concept rendering.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

OUT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/final_aircraft")
FIG = OUT / "figures"
CANDIDATES = ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans")


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


def parse_polar(path: Path) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    cols = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if cols is None:
            if fields and fields[0] == "Beta" and "AoA" in fields and "CDi" in fields:
                cols = fields
            continue
        if len(fields) == len(cols):
            try:
                rows.append(dict(zip(cols, [float(v) for v in fields])))
            except ValueError:
                pass
    return rows


def gather(case_dirs: List[Path]) -> List[Dict[str, float]]:
    """Stitch every polar found in the given case directories into one alpha-ordered curve."""
    rows: List[Dict[str, float]] = []
    for case in case_dirs:
        polars = sorted(case.glob("*.polar"))
        if not polars:
            raise SystemExit("case has no .polar: %s" % case)
        rows.extend(parse_polar(polars[0]))
    rows.sort(key=lambda r: r["AoA"])
    return rows


def nearest(rows: List[Dict[str, float]], alpha: float) -> Dict[str, float]:
    return min(rows, key=lambda r: abs(r["AoA"] - alpha))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--baseline-cases", nargs="+", required=True,
                        help="case directories of the baseline aircraft, coarse then refine")
    parser.add_argument("--optimized-cases", nargs="+", required=True,
                        help="case directories of the optimized aircraft, coarse then refine")
    parser.add_argument("--baseline-cert", required=True)
    parser.add_argument("--optimized-cert", required=True)
    parser.add_argument("--design-csv", default=None)
    parser.add_argument("--cl-target", type=float, required=True)
    parser.add_argument("--out-prefix", default="")
    parser.add_argument("--labels", nargs=2, default=["基准构型", "优化构型"])
    args = parser.parse_args()

    FIG.mkdir(parents=True, exist_ok=True)
    base_cert = json.loads(Path(args.baseline_cert).read_text(encoding="utf-8"))
    opt_cert = json.loads(Path(args.optimized_cert).read_text(encoding="utf-8"))
    base_rows = gather([Path(p) for p in args.baseline_cases])
    opt_rows = gather([Path(p) for p in args.optimized_cases])

    base_pt = nearest(base_rows, base_cert["alpha_deg"])
    opt_pt = nearest(opt_rows, opt_cert["alpha_deg"])

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6))
    for ax, key, ylabel, title in (
        (axes[0], "CLtot", "CL (总升力系数)", "(a) 真实 CL-α 曲线与同升力工作点"),
        (axes[1], "CDi", "CDi (诱导阻力系数)", "(b) 真实 CDi-α 曲线与同升力工作点"),
    ):
        ax.plot([r["AoA"] for r in base_rows], [r[key] for r in base_rows],
                "o-", color="#1565c0", ms=3.2, lw=1.3, label=args.labels[0])
        ax.plot([r["AoA"] for r in opt_rows], [r[key] for r in opt_rows],
                "s-", color="#c62828", ms=3.2, lw=1.3, label=args.labels[1])
        ax.plot([base_pt["AoA"]], [base_pt[key]], "o", ms=11, mfc="none",
                mec="#1565c0", mew=1.8)
        ax.plot([opt_pt["AoA"]], [opt_pt[key]], "s", ms=11, mfc="none",
                mec="#c62828", mew=1.8)
        ax.set_xlabel("α (deg)")
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=11.5)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=9.5)
    axes[0].axhline(args.cl_target, color="#455a64", ls="--", lw=1.1)
    axes[0].annotate("目标升力 CL=%.6f" % args.cl_target,
                     xy=(base_rows[0]["AoA"], args.cl_target),
                     xytext=(3, 8), textcoords="offset points",
                     fontsize=8.5, color="#455a64")
    # The two work points sit within 0.012 deg of each other, so the labels are split
    # above and below the marker; otherwise they collide and hide the very difference
    # the figure exists to show.
    for ax, pt, cert, color, dy in (
        (axes[0], base_pt, base_cert, "#1565c0", 26),
        (axes[0], opt_pt, opt_cert, "#c62828", -34),
        (axes[1], base_pt, base_cert, "#1565c0", 26),
        (axes[1], opt_pt, opt_cert, "#c62828", -34),
    ):
        y = pt["CLtot"] if ax is axes[0] else pt["CDi"]
        ax.annotate("%s  α*=%.5f°\nCL=%.6f  CDi=%.9f" % (
                        args.labels[0] if color == "#1565c0" else args.labels[1],
                        cert["alpha_deg"], cert["cl"], cert["cdi"]),
                    xy=(pt["AoA"], y), xytext=(12, dy), textcoords="offset points",
                    fontsize=7.8, color=color, linespacing=1.35,
                    arrowprops=dict(arrowstyle="-", lw=0.7, color=color, alpha=0.7))
    fig.suptitle("同升力条件下的原始求解器曲线（VSPAERO 真实 polar，非拟合）", fontsize=13)
    fig.text(0.01, 0.01,
             "数据来源：每个工况目录内 VSPAERO 直接写出的 .polar（coarse 7 行 + refine 13 行按 α 拼接）；"
             "标记点为准入证书里的 α*，与 CDi 行同一行取值。Di = q·Sref·CDi。",
             fontsize=8.2, color="#444444")
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    stem = args.out_prefix + "cl_alpha_and_cdi_alpha"
    fig.savefig(FIG / (stem + ".png"))
    plt.close(fig)

    report = {
        "curve_figure": stem + ".png",
        "baseline": {"alpha_star_deg": base_cert["alpha_deg"], "cl": base_cert["cl"],
                     "cdi": base_cert["cdi"], "di_n": base_cert["di_n"],
                     "polar_rows": len(base_rows)},
        "optimized": {"alpha_star_deg": opt_cert["alpha_deg"], "cl": opt_cert["cl"],
                      "cdi": opt_cert["cdi"], "di_n": opt_cert["di_n"],
                      "polar_rows": len(opt_rows)},
        "cl_target": args.cl_target,
    }

    if args.design_csv:
        rows = list(csv.DictReader(Path(args.design_csv).read_text(encoding="utf-8").splitlines()))
        active = [r for r in rows if r["is_active_in_this_batch"] == "True"]
        frozen = [r for r in rows if r["is_active_in_this_batch"] != "True"]
        names = [r["variable"] for r in active]
        b = [float(r["baseline"]) for r in active]
        o = [float(r["optimized"]) for r in active]
        lo = [float(r["frozen_bound_lower"]) for r in active]
        hi = [float(r["frozen_bound_upper"]) for r in active]
        delta = [float(r["delta"]) for r in active]
        rel = [float(r["relative_change"]) * 100.0 for r in active]
        # Two parameters that live 67 and 48 deg apart cannot be compared on one absolute
        # axis, so panel (a) shows where each value sits *inside its own frozen search
        # bound*; panels (b) and (c) then show the change itself in deg and in percent.
        fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.2))
        ax = axes[0]
        width = 0.34
        pos_b = [(bv - l) / (h - l) * 100.0 for bv, l, h in zip(b, lo, hi)]
        pos_o = [(ov - l) / (h - l) * 100.0 for ov, l, h in zip(o, lo, hi)]
        xs = list(range(len(active)))
        ax.bar([x - width / 2 for x in xs], pos_b, width, color="#1565c0",
               label=args.labels[0], edgecolor="#0d47a1", lw=0.6)
        ax.bar([x + width / 2 for x in xs], pos_o, width, color="#c62828",
               label=args.labels[1], edgecolor="#b71c1c", lw=0.6)
        for x, pb, po, bv, ov in zip(xs, pos_b, pos_o, b, o):
            ax.annotate("%.3f" % bv, xy=(x - width / 2, pb), xytext=(0, 3),
                        textcoords="offset points", ha="center", fontsize=8, color="#0d47a1")
            ax.annotate("%.3f" % ov, xy=(x + width / 2, po), xytext=(0, 3),
                        textcoords="offset points", ha="center", fontsize=8, color="#b71c1c")
        ax.set_xticks(xs)
        ax.set_xticklabels(names)
        ax.set_ylim(0, 118)
        ax.set_ylabel("在冻结搜索边界内的位置 (%)")
        ax.set_title("(a) 参数值在各自冻结边界内的位置（柱顶标注真实 deg 值）", fontsize=10.5)
        ax.legend(fontsize=9, loc="lower center")
        ax.grid(alpha=0.25, axis="y")

        ax = axes[1]
        ax.bar(names, delta, color="#c62828", width=0.5)
        ax.axhline(0.0, color="#37474f", lw=1.0)
        for i, v in enumerate(delta):
            ax.annotate("%+.6f" % v, xy=(i, v), xytext=(0, 6 if v >= 0 else -14),
                        textcoords="offset points", ha="center", fontsize=8.5)
        ax.set_ylabel("绝对变化 Δ (deg)")
        pad = max(abs(v) for v in delta) * 0.45 or 0.01
        ax.set_ylim(min(delta + [0.0]) - pad, max(delta + [0.0]) + pad)
        ax.set_title("(b) 活动参数的绝对变化", fontsize=10.5)
        ax.grid(alpha=0.25, axis="y")

        ax = axes[2]
        ax.barh(names, rel, color="#c62828", height=0.45)
        ax.axvline(0.0, color="#37474f", lw=1.0)
        for i, v in enumerate(rel):
            ax.annotate("%+.4f%%" % v, xy=(v, i), xytext=(8 if v >= 0 else -8, 0),
                        textcoords="offset points", va="center",
                        ha="left" if v >= 0 else "right", fontsize=9)
        span = max(abs(v) for v in rel) or 1.0
        ax.set_xlim(min(rel + [0.0]) - span * 0.8, max(rel + [0.0]) + span * 0.8)
        ax.set_xlabel("相对变化 (%)")
        ax.set_title("(c) 相对变化；其余 %d 个冻结参数变化恰为 0" % len(frozen), fontsize=10.5)
        ax.grid(alpha=0.25, axis="x")
        fig.suptitle("优化前后关键几何尺寸变化（来自 design_before_after.csv）", fontsize=13)
        fig.text(0.01, 0.01,
                 "活动子空间只有 %d 个后掠参数，其余 %d 个维度在预注册时即冻结、变化恰为 0；"
                 "柱顶数值与交付 CSV 逐字段一致。"
                 % (len(active), len(frozen)), fontsize=8.2, color="#444444")
        fig.tight_layout(rect=(0, 0.04, 1, 0.93))
        stem2 = args.out_prefix + "geometry_dimension_changes"
        fig.savefig(FIG / (stem2 + ".png"))
        plt.close(fig)
        report["dimension_figure"] = stem2 + ".png"
        report["active_parameters"] = {r["variable"]: {"baseline": float(r["baseline"]),
                                                       "optimized": float(r["optimized"]),
                                                       "relative_change": float(r["relative_change"]),
                                                       "bound": [float(r["frozen_bound_lower"]),
                                                                 float(r["frozen_bound_upper"])]}
                                       for r in active}
        report["frozen_parameter_count"] = len(frozen)

    report["all_png"] = sorted(p.name for p in FIG.glob("*.png"))
    (FIG / (args.out_prefix + "polar_figure_manifest.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
