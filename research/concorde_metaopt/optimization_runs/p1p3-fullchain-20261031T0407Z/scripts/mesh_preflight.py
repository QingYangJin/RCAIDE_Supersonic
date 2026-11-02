"""Pre-flight structural validation of a 3D SU2 ASCII mesh (no solver start).

Checks the invariants that SU2's ASCII reader enforces, so that an invalid mesh is
caught before a budgeted solver start:
  * NDIME=3, volume elements are type 10 (tet), boundary elements are type 5 (triangle)
  * all node indices in [0, NPOIN), all nodes referenced
  * every tetrahedron positively oriented
  * boundary triangles are exactly the free faces of the tet mesh (each boundary
    face belongs to exactly one tet, every interior face shared by exactly two tets)
  * each marker triangle set is non-empty; marker faces partition the free faces
Writes a JSON summary and exits non-zero on any failure.
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path


def parse_su2(path):
    text = Path(path).read_text(errors="replace").splitlines()
    i = 0
    data = {"elem_type_counts": Counter(), "markers": {}}
    n = len(text)
    while i < n:
        line = text[i].strip()
        if line.startswith("NDIME="):
            data["ndime"] = int(line.split("=")[1])
            i += 1
        elif line.startswith("NELEM="):
            nelem = int(line.split("=")[1])
            i += 1
            elems = []
            for _ in range(nelem):
                parts = [int(v) for v in text[i].split()]
                data["elem_type_counts"][parts[0]] += 1
                elems.append(parts)
                i += 1
            data["elements"] = elems
        elif line.startswith("NPOIN="):
            npoin = int(line.split("=")[1])
            i += 1
            nodes = []
            for _ in range(npoin):
                parts = text[i].split()
                nodes.append((float(parts[0]), float(parts[1]), float(parts[2])))
                i += 1
            data["nodes"] = nodes
        elif line.startswith("NMARK="):
            nmark = int(line.split("=")[1])
            i += 1
            for _ in range(nmark):
                assert text[i].strip().startswith("MARKER_TAG="), text[i]
                tag = text[i].strip().split("=", 1)[1].strip()
                i += 1
                while not text[i].strip().startswith("MARKER_ELEMS="):
                    i += 1
                count = int(text[i].strip().split("=")[1])
                i += 1
                tris = []
                for _ in range(count):
                    parts = [int(v) for v in text[i].split()]
                    data["elem_type_counts"]["marker_%d" % parts[0]] += 1
                    tris.append(parts)
                    i += 1
                data["markers"][tag] = tris
        else:
            i += 1
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--su2", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--expected-tets", type=int, default=None)
    args = ap.parse_args()

    d = parse_su2(args.su2)
    nodes = d["nodes"]
    npoin = len(nodes)
    tets = [e for e in d["elements"] if e[0] == 10]
    non_tets = [e for e in d["elements"] if e[0] != 10]
    problems = []

    if d.get("ndime") != 3:
        problems.append("NDIME is not 3")
    if non_tets:
        problems.append("%d volume elements are not type 10" % len(non_tets))
    if args.expected_tets is not None and len(tets) != args.expected_tets:
        problems.append("expected %d tets, found %d" % (args.expected_tets, len(tets)))

    max_node = -1
    used = [False] * npoin
    for e in tets:
        for nid in e[1:5]:
            if nid < 0 or nid >= npoin:
                problems.append("tet node index out of range: %d" % nid)
                continue
            used[nid] = True
            max_node = max(max_node, nid)
    unused = used.count(False)
    if unused:
        problems.append("%d nodes are not referenced by any tet" % unused)

    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def cross(u, v):
        return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])

    def dot(u, v):
        return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]

    volumes = []
    negative = 0
    for e in tets:
        a, b, c, dd = [nodes[nid] for nid in e[1:5]]
        v = dot(sub(b, a), cross(sub(c, a), sub(dd, a))) / 6.0
        volumes.append(v)
        if v <= 0.0:
            negative += 1
    if negative:
        problems.append("%d tetrahedra have non-positive volume" % negative)

    # face -> list of (tet index)
    def face_key(tri):
        return tuple(sorted(tri))

    face_count = Counter()
    tet_faces = {}
    for ti, e in enumerate(tets):
        a, b, c, dd = e[1:5]
        faces = [face_key([a, b, c]), face_key([a, b, dd]), face_key([a, c, dd]), face_key([b, c, dd])]
        tet_faces[ti] = faces
        for f in faces:
            face_count[f] += 1
    free_faces = {f for f, cnt in face_count.items() if cnt == 1}
    over_shared = {f: cnt for f, cnt in face_count.items() if cnt > 2}
    if over_shared:
        problems.append("%d faces are shared by more than two tets" % len(over_shared))
    interior = sum(1 for cnt in face_count.values() if cnt == 2)
    if interior + len(free_faces) != len(face_count):
        problems.append("some faces are shared by exactly one or more than two tets inconsistently")

    marker_faces = {}
    marker_problems = []
    all_marker_faces = []
    for tag, tris in d["markers"].items():
        if not tris:
            marker_problems.append("marker %s is empty" % tag)
            continue
        bad_type = [t for t in tris if t[0] != 5]
        if bad_type:
            marker_problems.append("marker %s has %d non-triangle elements (types: %s)" %
                                   (tag, len(bad_type), sorted({t[0] for t in bad_type})))
        fk = set()
        for t in tris:
            for nid in t[1:4]:
                if nid < 0 or nid >= npoin:
                    marker_problems.append("marker %s node index out of range: %d" % (tag, nid))
            key = face_key(t[1:4])
            fk.add(key)
            all_marker_faces.append(key)
        missing = fk - free_faces
        if missing:
            marker_problems.append("marker %s has %d faces that are not free faces of the volume mesh"
                                   % (tag, len(missing)))
        marker_faces[tag] = len(fk)
    dup_marker = len(all_marker_faces) - len(set(all_marker_faces))
    if dup_marker:
        marker_problems.append("%d marker faces are listed more than once across markers" % dup_marker)
    unassigned = free_faces - set(all_marker_faces)
    if unassigned:
        marker_problems.append("%d free faces are not assigned to any marker" % len(unassigned))

    problems.extend(marker_problems)

    def tri_area(tri):
        a, b, c = [nodes[nid] for nid in tri[1:4]]
        return 0.5 * math.sqrt(dot(cross(sub(b, a), sub(c, a)), cross(sub(b, a), sub(c, a))))

    summary = {
        "su2": str(args.su2),
        "bytes": Path(args.su2).stat().st_size,
        "ndime": d.get("ndime"),
        "npoin": npoin,
        "nelem": len(d["elements"]),
        "tets": len(tets),
        "volume_element_types": dict(d["elem_type_counts"]),
        "max_node_index": max_node,
        "unused_nodes": unused,
        "negative_tet_volumes": negative,
        "total_tet_volume": sum(volumes),
        "min_tet_volume": min(volumes) if volumes else None,
        "max_tet_volume": max(volumes) if volumes else None,
        "faces_total": len(face_count),
        "faces_interior": interior,
        "faces_free": len(free_faces),
        "marker_face_counts": marker_faces,
        "marker_area_m2": {tag: sum(tri_area(t) for t in tris) for tag, tris in d["markers"].items()},
        "problems": problems,
        "pass": not problems,
    }
    Path(args.out).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0 if summary["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())