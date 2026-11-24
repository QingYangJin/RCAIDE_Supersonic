"""Draw the aircraft views for final_aircraft/ from the exported STL files.

Top, side, front, and a 3D view of the actual exported geometry, plus the wing planform
overlay between baseline and optimized. Everything is read back from the STL that OpenVSP
wrote, so the figures cannot drift from the deliverable geometry.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

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


def read_stl(path: Path) -> np.ndarray:
    """Return an (n, 3, 3) triangle array from an ASCII or binary STL."""
    data = path.read_bytes()
    if data[:5].lower() == b"solid" and b"facet" in data[:2048]:
        text = data.decode("ascii", errors="replace")
        vertices: List[Tuple[float, float, float]] = []
        for line in text.splitlines():
            parts = line.strip().split()
            if len(parts) == 4 and parts[0] == "vertex":
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        if not vertices or len(vertices) % 3:
            raise ValueError("malformed ASCII STL: %s" % path)
        return np.array(vertices, dtype=float).reshape(-1, 3, 3)
    count = struct.unpack("<I", data[80:84])[0]
    expected = 84 + count * 50
    if len(data) != expected:
        raise ValueError("binary STL size mismatch: %s (%d != %d)"
                         % (path, len(data), expected))
    triangles = np.zeros((count, 3, 3), dtype=float)
    offset = 84
    for index in range(count):
        values = struct.unpack("<12f", data[offset:offset + 48])
        triangles[index] = np.array(values[3:]).reshape(3, 3)
        offset += 50
    return triangles


def project(tri: np.ndarray, axes: Tuple[int, int]):
    return tri[:, :, list(axes)]


def draw_views(tri: np.ndarray, title: str, stem: str) -> None:
    points = tri.reshape(-1, 3)
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    specs = (
        (axes[0][0], (0, 1), "俯视图（X 前向, Y 展向）", "X (m)", "Y (m)", "#1565c0"),
        (axes[0][1], (0, 2), "侧视图（X 前向, Z 垂向）", "X (m)", "Z (m)", "#2e7d32"),
        (axes[1][0], (1, 2), "正视图（Y 展向, Z 垂向）", "Y (m)", "Z (m)", "#6a1b9a"),
    )
    for ax, pair, title_text, xlabel, ylabel, color in specs:
        polys = project(tri, pair)
        collection = PolyCollection(polys, facecolors=color, edgecolors="#1a1a1a",
                                    linewidths=0.15, alpha=0.85)
        ax.add_collection(collection)
        ax.autoscale_view()
        ax.set_title(title_text, fontsize=12)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=0.2)

    ax = axes[1][1]
    ax.axis("off")
    ax3 = fig.add_subplot(2, 2, 4, projection="3d")
    step = max(1, len(tri) // 4000)
    polys = tri[::step]
    collection = Poly3DCollection(polys, alpha=0.35, facecolor="#90caf9",
                                  edgecolor="#1565c0", linewidths=0.05)
    ax3.add_collection3d(collection)
    ax3.set_xlim(x.min(), x.max())
    ax3.set_ylim(y.min(), y.max())
    ax3.set_zlim(z.min(), z.max())
    ax3.set_box_aspect((x.max() - x.min(), y.max() - y.min(),
                        max(z.max() - z.min(), 1.0)))
    ax3.set_title("三维视图", fontsize=12)
    ax3.view_init(elev=22, azim=-60)

    fig.suptitle(title, fontsize=13.5)
    fig.text(0.01, 0.01,
             "数据来源：%s（由冻结几何模型经 OpenVSP 导出的 STL 直接读取，非概念渲染）。"
             % stem, fontsize=8.5, color="#444444")
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    fig.savefig(FIG / (stem + "_views.png"))
    plt.close(fig)


def draw_planform_overlay(baseline: np.ndarray, optimized: np.ndarray) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.0))
    for ax, axis_pair, labels in (
        (axes[0], (0, 1), ("X (m)", "Y (m)", "俯视平面形状叠加")),
        (axes[1], (0, 2), ("X (m)", "Z (m)", "侧视轮廓叠加")),
    ):
        for tri, label, color in ((baseline, "基准构型", "#1565c0"),
                                  (optimized, "优化构型", "#c62828")):
            polys = project(tri, axis_pair)
            ax.add_collection(PolyCollection(polys, facecolors=color,
                                             edgecolors=color, linewidths=0.1,
                                             alpha=0.35, label=label))
        ax.autoscale_view()
        ax.set_xlabel(labels[0])
        ax.set_ylabel(labels[1])
        ax.set_title(labels[2], fontsize=12)
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=0.25)
        ax.legend(markerscale=20, fontsize=10)
    fig.suptitle("基准与优化构型几何叠加（同一视角与同一比例尺）", fontsize=13)
    fig.text(0.01, 0.01,
             "两组几何均由同一冻结建模板导出；红色为优化后活动参数（后掠）改变后的实际几何。",
             fontsize=8.5, color="#444444")
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))
    fig.savefig(FIG / "geometry_before_after_overlay.png")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-stl", required=True)
    parser.add_argument("--optimized-stl", default=None)
    args = parser.parse_args()
    FIG.mkdir(parents=True, exist_ok=True)
    baseline = read_stl(Path(args.baseline_stl))
    draw_views(baseline, "基准构型（full：主翼 + 垂尾 + 机身）", "baseline")
    report = {"baseline_triangles": int(len(baseline)),
              "baseline_stl": args.baseline_stl}
    if args.optimized_stl:
        optimized = read_stl(Path(args.optimized_stl))
        draw_views(optimized, "优化构型（full：主翼 + 垂尾 + 机身）", "optimized")
        draw_planform_overlay(baseline, optimized)
        report.update({"optimized_triangles": int(len(optimized)),
                       "optimized_stl": args.optimized_stl})
    report["figures"] = sorted(p.name for p in FIG.glob("*.png"))
    (FIG / "figure_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
