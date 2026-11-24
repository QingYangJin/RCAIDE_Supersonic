"""Draw the O1 three-arm deliverable figures from the exported STL files.

Three configurations must be handed over, not only the winner (Issue #15 §7): the
baseline, the Sobol+BO best, and the model-ranked best. Each gets the same four views
at the same scale, plus a planform overlay of every candidate against the baseline, and
the CL-alpha / CDi-alpha curves read from the real VSPAERO polars with every work point
marked.

All geometry is read back from the STL OpenVSP wrote for the delivered .vsp3, so a figure
cannot drift from the file that is being delivered.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

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


def read_stl(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if data[:5].lower() == b"solid" and b"facet" in data[:2048]:
        vertices: List[Tuple[float, float, float]] = []
        for line in data.decode("ascii", errors="replace").splitlines():
            parts = line.strip().split()
            if len(parts) == 4 and parts[0] == "vertex":
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        if not vertices or len(vertices) % 3:
            raise ValueError("malformed ASCII STL: %s" % path)
        return np.array(vertices, dtype=float).reshape(-1, 3, 3)
    count = struct.unpack("<I", data[80:84])[0]
    if len(data) != 84 + count * 50:
        raise ValueError("binary STL size mismatch: %s" % path)
    triangles = np.zeros((count, 3, 3), dtype=float)
    offset = 84
    for index in range(count):
        triangles[index] = np.array(struct.unpack("<12f", data[offset:offset + 48])[3:]).reshape(3, 3)
        offset += 50
    return triangles


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


def gather(cases: List[Path]) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    for case in cases:
        polars = sorted(case.glob("*.polar"))
        if not polars:
            raise SystemExit("case has no .polar: %s" % case)
        rows.extend(parse_polar(polars[0]))
    rows.sort(key=lambda r: r["AoA"])
    return rows


def draw_views(tri: np.ndarray, title: str, stem: str, out: Path, note: str) -> None:
    points = tri.reshape(-1, 3)
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    specs = (
        (axes[0][0], (0, 1), "俯视图（X 前向, Y 展向）", "X (m)", "Y (m)", "#1565c0"),
        (axes[0][1], (0, 2), "侧视图（X 前向, Z 垂向）", "X (m)", "Z (m)", "#2e7d32"),
        (axes[1][0], (1, 2), "正视图（Y 展向, Z 垂向）", "Y (m)", "Z (m)", "#6a1b9a"),
    )
    for ax, pair, text, xlabel, ylabel, color in specs:
        ax.add_collection(PolyCollection(tri[:, :, list(pair)], facecolors=color,
                                         edgecolors="#1a1a1a", linewidths=0.15, alpha=0.85))
        ax.autoscale_view()
        ax.set_title(text, fontsize=12)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=0.2)
    ax = axes[1][1]
    ax.axis("off")
    ax3 = fig.add_subplot(2, 2, 4, projection="3d")
    step = max(1, len(tri) // 4000)
    ax3.add_collection3d(Poly3DCollection(tri[::step], alpha=0.35, facecolor="#90caf9",
                                          edgecolor="#1565c0", linewidths=0.05))
    ax3.set_xlim(x.min(), x.max())
    ax3.set_ylim(y.min(), y.max())
    ax3.set_zlim(z.min(), z.max())
    ax3.set_box_aspect((x.max() - x.min(), y.max() - y.min(), max(z.max() - z.min(), 1.0)))
    ax3.set_title("三维视图", fontsize=12)
    ax3.view_init(elev=22, azim=-60)
    fig.suptitle(title, fontsize=13.5)
    fig.text(0.01, 0.01, note, fontsize=8.5, color="#444444")
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    fig.savefig(out / (stem + "_views.png"))
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--config", action="append", required=True,
                        help="label|stl|color|ascii_stem, repeated once per delivered configuration")
    parser.add_argument("--curve-series", action="append", default=[],
                        help="label|cert.json|case_dir1,case_dir2")
    parser.add_argument("--cl-target", type=float, default=None)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    configs = []
    # Fields are separated by "|" and not ":", because a Windows path starts with a
    # drive letter and "D:/..." would make the label parse into a bare "D".
    for spec in args.config:
        label, stl, color, stem = spec.split("|", 3)
        configs.append({"label": label, "stl": stl, "color": color, "stem": stem,
                        "triangles": read_stl(Path(stl))})

    # The output stem is deliberately ASCII: a CJK file name is fine on this host but it
    # makes the hand-off fragile for anyone who unzips the package on a different code page.
    for cfg in configs:
        draw_views(cfg["triangles"], "%s（full：主翼 + 垂尾 + 机身）" % cfg["label"],
                   cfg["stem"], out,
                   "数据来源：%s（冻结几何模型经 OpenVSP 导出的 STL 直接读取，非概念渲染）。"
                   % Path(cfg["stl"]).name)

    baseline = configs[0]
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.0))
    for ax, pair, labels in ((axes[0], (0, 1), ("X (m)", "Y (m)", "俯视平面形状叠加")),
                             (axes[1], (0, 2), ("X (m)", "Z (m)", "侧视轮廓叠加"))):
        for cfg in [baseline] + configs[1:]:
            ax.add_collection(PolyCollection(cfg["triangles"][:, :, list(pair)],
                                             facecolors=cfg["color"], edgecolors=cfg["color"],
                                             linewidths=0.1, alpha=0.35, label=cfg["label"]))
        ax.autoscale_view()
        ax.set_xlabel(labels[0])
        ax.set_ylabel(labels[1])
        ax.set_title(labels[2], fontsize=12)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=0.25)
        ax.legend(markerscale=20, fontsize=9.5)
    fig.suptitle("基准与各臂最佳构型几何叠加（同一视角与同一比例尺）", fontsize=13)
    fig.text(0.01, 0.01, "所有构型由同一冻结建模板导出；差异只来自本批活动的两个后掠参数。",
             fontsize=8.5, color="#444444")
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))
    fig.savefig(out / "geometry_overlay_all_arms.png")
    plt.close(fig)

    report = {"configurations": {c["label"]: {"stl": c["stl"],
                                              "triangles": int(len(c["triangles"]))}
                                 for c in configs}}

    if args.curve_series:
        series = []
        for spec in args.curve_series:
            label, cert_path, case_list = spec.split("|", 2)
            cert = json.loads(Path(cert_path).read_text(encoding="utf-8"))
            rows = gather([Path(p) for p in case_list.split(",")])
            series.append({"label": label, "cert": cert, "rows": rows})
        palette = ["#1565c0", "#c62828", "#2e7d32", "#6a1b9a"]
        markers = ["o", "s", "^", "D"]
        fig, axes = plt.subplots(1, 2, figsize=(14.5, 5.8))
        for ax, key, ylabel, title in (
            (axes[0], "CLtot", "CL (总升力系数)", "(a) 真实 CL-α 曲线与同升力工作点"),
            (axes[1], "CDi", "CDi (诱导阻力系数)", "(b) 真实 CDi-α 曲线与同升力工作点"),
        ):
            for i, s in enumerate(series):
                ax.plot([r["AoA"] for r in s["rows"]], [r[key] for r in s["rows"]],
                        marker=markers[i % 4], ms=3.0, lw=1.2, color=palette[i % 4],
                        label=s["label"])
                point = min(s["rows"], key=lambda r: abs(r["AoA"] - s["cert"]["alpha_deg"]))
                ax.plot([point["AoA"]], [point[key]], markers[i % 4], ms=10, mfc="none",
                        mec=palette[i % 4], mew=1.8)
            ax.set_xlabel("α (deg)")
            ax.set_ylabel(ylabel)
            ax.set_title(title, fontsize=11.5)
            ax.grid(alpha=0.25)
            ax.legend(fontsize=9)
        if args.cl_target is not None:
            axes[0].axhline(args.cl_target, color="#455a64", ls="--", lw=1.1)
            axes[0].annotate("目标升力 CL=%.6f" % args.cl_target,
                             xy=(series[0]["rows"][0]["AoA"], args.cl_target),
                             xytext=(3, 8), textcoords="offset points",
                             fontsize=8.5, color="#455a64")
        fig.suptitle("同升力条件下的原始求解器曲线（VSPAERO 真实 polar，非拟合）", fontsize=13)
        fig.text(0.01, 0.01,
                 "数据来源：各工况目录内 VSPAERO 直接写出的 .polar（coarse 7 行 + refine 13 行按 α 拼接）；"
                 "空心标记为准入证书里的 α*。", fontsize=8.2, color="#444444")
        fig.tight_layout(rect=(0, 0.04, 1, 0.93))
        fig.savefig(out / "cl_alpha_and_cdi_alpha_all_arms.png")
        plt.close(fig)
        report["curves"] = {s["label"]: {"alpha_star_deg": s["cert"]["alpha_deg"],
                                         "cl": s["cert"]["cl"],
                                         "cdi": s["cert"]["cdi"],
                                         "di_n": s["cert"]["di_n"],
                                         "polar_rows": len(s["rows"])}
                            for s in series}
        report["curve_figure"] = "cl_alpha_and_cdi_alpha_all_arms.png"

    report["figures"] = sorted(p.name for p in out.glob("*.png"))
    (out / "figure_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
