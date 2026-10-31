"""Generate an isolated-wing HF (Euler) volume mesh.

Builds a closed lifting-surface solid by lofting the NACA 65-203 airfoil through the
7 wing sections of the 12D baseline (4 per side + shared root), subtracts it from a
farfield box, meshes with Gmsh, converts to a SU2 mesh with wall/farfield markers.

Geometry frame: wing-local, leading edge of root section at x=0, chordwise +x,
spanwise +-y, thickness +z. Translation of the wing origin does not affect
lift/drag coefficients of an isolated wing.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
GMSH = r"D:/Program Files/GMesh/gmsh-4.15.2-Windows64/gmsh-4.15.2-Windows64/gmsh.exe"
PROJECT_PY = r"D:/RCAIDE/envs/RCAIDE/python.exe"
AIRFOIL = Path(r"D:/RCAIDE/tutorials/Airfoils_and_Polars/NACA65_203.txt")
CONVERTER = EXT / "lead" / "msh2_to_su2.py"
REQUEST = EXT / "lf" / "baseline" / "request.json"


def read_airfoil(path):
    raw = [l.strip() for l in Path(path).read_text().splitlines() if l.strip()]
    coords = []
    for line in raw[2:]:
        try:
            vals = [float(v) for v in line.split()[:2]]
        except ValueError:
            continue
        coords.append((vals[0], vals[1]))
    n = int(round(len(coords) / 2))
    upper = coords[:n]
    lower = coords[n:2 * n]
    loop = list(upper) + list(reversed(lower[1:-1]))
    return loop


def airfoil_area(loop):
    # polygon area of (x, z) loop, chord-normalised
    area = 0.0
    for k in range(len(loop)):
        x1, z1 = loop[k]
        x2, z2 = loop[(k + 1) % len(loop)]
        area += x1 * z2 - x2 * z1
    return 0.5 * area


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", required=True)
    ap.add_argument("--lcw", type=float, required=True)
    ap.add_argument("--lcm", type=float, required=True)
    ap.add_argument("--growth", type=float, default=0.45)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    req = json.loads(REQUEST.read_text())
    wing = req["components"][0]
    span = float(wing["span_m"])
    half = span / 2.0
    sections = sorted(wing["sections"], key=lambda s: s["percent_span_location"])
    loop2d = read_airfoil(AIRFOIL)
    af_area = airfoil_area(loop2d)

    # ordered sections from -tip to +tip (root appears once)
    stations = []
    for s in reversed(sections[1:]):
        stations.append((-s["percent_span_location"] * half, s))
    stations.append((0.0, sections[0]))
    for s in sections[1:]:
        stations.append((s["percent_span_location"] * half, s))

    outdir = Path(args.outdir) if args.outdir else EXT / "hf" / "wing"
    outdir.mkdir(parents=True, exist_ok=True)
    geo = outdir / ("wing_%s.geo" % args.level)
    msh = outdir / ("wing_%s.msh" % args.level)
    su2 = outdir / ("wing_%s.su2" % args.level)
    summary = outdir / ("wing_%s_mesh.json" % args.level)

    lines = []
    lines.append('SetFactory("OpenCASCADE");')
    lines.append("Mesh.ElementOrder = 1;")
    lines.append("Mesh.Algorithm3D = 10;")
    lines.append("Mesh.MeshSizeFromPoints = 0;")
    lines.append("Mesh.MeshSizeFromCurvature = 0;")
    lines.append("Mesh.MeshSizeExtendFromBoundary = 0;")
    lines.append('lcw = %g;' % args.lcw)
    lines.append('lcm = %g;' % args.lcm)
    lines.append("Field[1] = MathEval;")
    lines.append('Field[1].F = "min(%.6f, %.6f + %.6f*(abs(z) + max(0, abs(y)-12.802318) + max(0, x-31.5) + max(0, -x)))";' % (args.lcm, args.lcw, args.growth))
    lines.append("Background Field = 1;")
    lines.append("Mesh.MeshSizeMax = lcm;")
    lines.append("Mesh.MeshSizeMin = %g;" % (args.lcw * 0.6))
    lines.append("Mesh.OptimizeNetgen = 1;")
    lines.append("Mesh.Smoothing = 5;")
    lines.append("Mesh.SaveAll = 1;")

    curve_ids = []
    loop_ids = []
    for si, (y, sec) in enumerate(stations):
        chord = float(sec["chord_m"])
        le = float(sec["leading_edge_x_m"])
        twist = math.radians(float(sec["twist_deg"]))
        ct, st = math.cos(twist), math.sin(twist)
        base = 1000 + si * 100
        for k, (xa, za) in enumerate(loop2d):
            dx = xa * chord
            dz = za * chord
            x = le + dx * ct - dz * st
            z = dx * st + dz * ct
            lines.append("Point(%d) = {%.10f, %.10f, %.10f, lcw};" % (base + k, x, y, z))
        # loop2d = upper[0..n-1] (LE->TE) then lower[n-2..1] (TE->LE region)
        n = len(loop2d) // 2 + 1
        upper_ids = [base + k for k in range(n)]          # LE .. TE
        lower_ids = [base + k for k in range(n, len(loop2d))]  # near TE .. near LE
        up_id = 2000 + si * 10 + 1
        lo_id = 2000 + si * 10 + 2
        lines.append("BSpline(%d) = {%s};" % (up_id, ", ".join(str(v) for v in upper_ids)))
        lower_chain = [upper_ids[-1]] + lower_ids + [upper_ids[0]]
        lines.append("BSpline(%d) = {%s};" % (lo_id, ", ".join(str(v) for v in lower_chain)))
        curve_ids.extend([up_id, lo_id])
        loop_id = 3000 + si
        lines.append("Curve Loop(%d) = {%d, %d};" % (loop_id, up_id, lo_id))
        loop_ids.append(loop_id)

    lines.append("Ruled ThruSections(4000) = {%d:%d};" % (loop_ids[0], loop_ids[-1]))
    lines.append("Box(5000) = {-40, -60, -60, 140, 120, 120};")
    lines.append("BooleanDifference(5001) = { Volume{5000}; Delete; }{ Volume{4000}; Delete; };")
    lines.append("Physical Volume(1) = {5001};")

    geo.write_text("\n".join(lines) + "\n")

    gmsh_log = outdir / ("wing_%s_gmsh.log" % args.level)
    with gmsh_log.open("w") as log:
        rc = subprocess.call([GMSH, "-3", str(geo), "-format", "msh2", "-o", str(msh),
                              "-v", "3"], stdout=log, stderr=subprocess.STDOUT)
    if rc != 0 or not msh.exists():
        print("GMSH FAILED rc=%s log=%s" % (rc, gmsh_log))
        return 2

    conv = subprocess.run([PROJECT_PY, str(CONVERTER), "--msh", str(msh), "--out", str(su2),
                           "--summary", str(summary),
                           "--xmin", "-40", "--xmax", "100",
                           "--ymin", "-60", "--ymax", "60",
                           "--zmin", "-60", "--zmax", "60"],
                          capture_output=True, text=True)
    if conv.returncode != 0:
        print("CONVERTER FAILED rc=%s" % conv.returncode)
        print(conv.stdout[-3000:])
        print(conv.stderr[-3000:])
        return 3

    stats = json.loads(summary.read_text())
    # analytic wing volume for cross-check: integral of chord(y)^2 * airfoil_area dy
    ys = [y for y, _ in stations]
    chords = [float(s["chord_m"]) for _, s in stations]
    vol = 0.0
    for i in range(len(stations) - 1):
        h = abs(ys[i + 1] - ys[i])
        c0, c1 = chords[i], chords[i + 1]
        vol += h / 3.0 * (c0 * c0 + c0 * c1 + c1 * c1)
    # half-wing integral x2 (mirror) x sectional area coefficient (abs: orientation-independent)
    wing_volume_estimate = vol * abs(af_area)  # stations span the full wing (mirror included)
    stats["level"] = args.level
    stats["lcw"] = args.lcw
    stats["lcm"] = args.lcm
    stats["airfoil_points"] = len(loop2d)
    stats["airfoil_area_chord_units"] = abs(af_area)
    stats["wing_volume_estimate_m3"] = wing_volume_estimate
    stats["wing_planform_area_m2"] = 358.25
    stats["stations_y_m"] = ys
    stats["stations_chord_m"] = chords
    stats["msh_bytes"] = msh.stat().st_size if msh.exists() else None
    stats["su2_bytes"] = su2.stat().st_size
    summary.write_text(json.dumps(stats, indent=2))
    print(json.dumps({k: stats[k] for k in ["level", "nodes", "tets", "wall_triangles",
                                            "farfield_triangles", "negative_tet_volumes",
                                            "total_tet_volume", "box_volume",
                                            "volume_deficit_vs_box", "wing_volume_estimate_m3",
                                            "msh_bytes", "su2_bytes"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())