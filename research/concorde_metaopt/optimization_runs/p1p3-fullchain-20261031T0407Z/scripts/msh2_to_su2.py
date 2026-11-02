"""Convert a Gmsh msh2 file (no physical groups required) into a SU2 3D mesh.

Boundary triangles are classified as 'farfield' when their centroid lies on one of
the six planes of the enclosing box, otherwise as 'wall' (the embedded wing).
Outputs a .su2 file plus a JSON summary with mesh validation statistics.
"""
import argparse
import json
import math
import sys
from pathlib import Path


def parse_msh2(path):
    text = Path(path).read_text(errors="replace").splitlines()
    i = 0
    nodes = {}
    triangles = []
    tets = []
    n = len(text)
    while i < n:
        line = text[i].strip()
        if line == "$Nodes":
            i += 1
            count = int(text[i].strip())
            i += 1
            for c in range(count):
                parts = text[i].split()
                nodes[int(parts[0])] = (float(parts[1]), float(parts[2]), float(parts[3]))
                i += 1
        elif line == "$Elements":
            i += 1
            count = int(text[i].strip())
            i += 1
            for c in range(count):
                parts = [int(v) for v in text[i].split()]
                etype = parts[1]
                ntags = parts[2]
                nids = parts[3:3 + ntags]
                conn = parts[3 + ntags:]
                if etype == 2:
                    triangles.append(conn)
                elif etype == 4:
                    tets.append(conn)
                i += 1
        else:
            i += 1
    return nodes, triangles, tets


def signed_tet_volume(a, b, c, d):
    ax = b[0] - a[0]; ay = b[1] - a[1]; az = b[2] - a[2]
    bx = c[0] - a[0]; by = c[1] - a[1]; bz = c[2] - a[2]
    cx = d[0] - a[0]; cy = d[1] - a[1]; cz = d[2] - a[2]
    det = (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx))
    return det / 6.0


def classify(centroid, planes, tol):
    for plane in planes:
        axis, value = plane
        if abs(centroid[axis] - value) <= tol:
            return "farfield"
    return "wall"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--msh", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--xmin", type=float, required=True)
    ap.add_argument("--xmax", type=float, required=True)
    ap.add_argument("--ymin", type=float, required=True)
    ap.add_argument("--ymax", type=float, required=True)
    ap.add_argument("--zmin", type=float, required=True)
    ap.add_argument("--zmax", type=float, required=True)
    ap.add_argument("--tol", type=float, default=1e-4)
    args = ap.parse_args()

    nodes, triangles, tets = parse_msh2(args.msh)

    # Gmsh SaveAll also writes 1D/2D entities (e.g. the loft section curves) whose
    # nodes are not part of the volume mesh.  Compact the node list to nodes that a
    # tetrahedron actually references, so the SU2 mesh has no orphan points.
    used_nodes = set()
    for conn in tets:
        used_nodes.update(conn)
    if len(used_nodes) != len(nodes):
        print("compacting nodes: %d -> %d (dropping %d orphan points)"
              % (len(nodes), len(used_nodes), len(nodes) - len(used_nodes)))
    order = sorted(used_nodes)
    remap = {old: new for new, old in enumerate(order)}
    nodes = {remap[old]: nodes[old] for old in order}
    tets = [[remap[n] for n in conn] for conn in tets]
    triangles = [[remap[n] for n in conn] for conn in triangles if all(n in remap for n in conn)]
    planes = [(0, args.xmin), (0, args.xmax), (1, args.ymin), (1, args.ymax),
              (2, args.zmin), (2, args.zmax)]
    tol = args.tol * max(args.xmax - args.xmin, args.ymax - args.ymin, args.zmax - args.zmin)

    volumes = []
    negative = 0
    bad_nodes = 0
    for conn in tets:
        pts = []
        ok = True
        for nid in conn:
            p = nodes.get(nid)
            if p is None:
                ok = False
                bad_nodes += 1
                break
            pts.append(p)
        if not ok:
            continue
        v = signed_tet_volume(pts[0], pts[1], pts[2], pts[3])
        volumes.append(v)
        if v <= 0.0:
            negative += 1

    wall = []
    farfield = []
    unclassified = []
    for conn in triangles:
        pts = []
        missing = False
        for nid in conn:
            p = nodes.get(nid)
            if p is None:
                missing = True
                break
            pts.append(p)
        if missing:
            unclassified.append("missing-node")
            continue
        cx = sum(p[0] for p in pts) / 3.0
        cy = sum(p[1] for p in pts) / 3.0
        cz = sum(p[2] for p in pts) / 3.0
        tag = classify((cx, cy, cz), planes, tol)
        (wall if tag == "wall" else farfield).append(conn)

    def tri_area(conn):
        a, b, c = [nodes[n] for n in conn]
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        cx = uy * vz - uz * vy
        cy = uz * vx - ux * vz
        cz = ux * vy - uy * vx
        return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)

    # final 0-based node numbering (independent of the original msh node ids)
    order = sorted(nodes)
    index = {key: i for i, key in enumerate(order)}
    out = []
    out.append("NDIME= 3")
    out.append("NELEM= %d" % len(tets))
    for k, conn in enumerate(tets):
        out.append("10 %d %d %d %d %d" % (index[conn[0]], index[conn[1]], index[conn[2]], index[conn[3]], k))
    out.append("NPOIN= %d" % len(nodes))
    for i, key in enumerate(order):
        p = nodes[key]
        out.append("%.10f %.10f %.10f %d" % (p[0], p[1], p[2], i))
    out.append("NMARK= 2")
    out.append("MARKER_TAG= wall")
    out.append("MARKER_ELEMS= %d" % len(wall))
    for conn in wall:
        out.append("5 %d %d %d" % (index[conn[0]], index[conn[1]], index[conn[2]]))  # VTK 5 = triangle
    out.append("MARKER_TAG= farfield")
    out.append("MARKER_ELEMS= %d" % len(farfield))
    for conn in farfield:
        out.append("5 %d %d %d" % (index[conn[0]], index[conn[1]], index[conn[2]]))  # VTK 5 = triangle
    Path(args.out).write_text("\n".join(out) + "\n")

    def tri_signed_volume(conn):
        a, b, cc = [nodes[n] for n in conn]
        # (1/6) a . (b x c)
        bx = b[1] * cc[2] - b[2] * cc[1]
        by = b[2] * cc[0] - b[0] * cc[2]
        bz = b[0] * cc[1] - b[1] * cc[0]
        return (a[0] * bx + a[1] * by + a[2] * bz) / 6.0

    wall_signed = sum(tri_signed_volume(c) for c in wall) if wall else 0.0
    farfield_signed = sum(tri_signed_volume(c) for c in farfield) if farfield else 0.0
    boundary_signed = wall_signed + farfield_signed

    total_volume = sum(volumes)
    summary = {
        "msh": str(args.msh),
        "su2": str(args.out),
        "nodes": len(nodes),
        "tets": len(tets),
        "boundary_triangles": len(triangles),
        "wall_triangles": len(wall),
        "farfield_triangles": len(farfield),
        "unclassified": len(unclassified),
        "negative_tet_volumes": negative,
        "missing_node_refs": bad_nodes,
        "total_tet_volume": total_volume,
        "min_tet_volume": min(volumes) if volumes else None,
        "max_tet_volume": max(volumes) if volumes else None,
        "wall_surface_area": sum(tri_area(c) for c in wall) if wall else 0.0,
        "farfield_surface_area": sum(tri_area(c) for c in farfield) if farfield else 0.0,
        "box_volume": (args.xmax - args.xmin) * (args.ymax - args.ymin) * (args.zmax - args.zmin),
        "tol_m": tol,
    }
    summary["wall_volume_abs_by_divergence"] = abs(wall_signed)
    summary["farfield_signed_volume"] = farfield_signed
    summary["boundary_signed_volume"] = boundary_signed
    summary["volume_deficit_vs_box"] = summary["box_volume"] - total_volume
    Path(args.summary).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if negative or bad_nodes or len(unclassified):
        print("VALIDATION FAILED: negative=%d bad_nodes=%d unclassified=%d" % (negative, bad_nodes, len(unclassified)))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())