"""LF geometry validation for the D-12D-002 full-chain run.

- binary STL vertex comparison baseline vs W10+2deg (geometry truth)
- DegenGeom CSV surface point comparison
- ISA 18288 m conditions and VSPAERO template preparation
"""
import hashlib
import json
import math
import struct
from pathlib import Path

EXT = Path("C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
CASES = {
    "baseline": EXT / "lf/baseline",
    "w10_plus2": EXT / "lf/w10_plus2",
}
G = 9.80665
R = 287.05
H = 18288.0
MACH = 2.02


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_stl_vertices(path):
    """Read STL vertices (OpenVSP writes ASCII STL: 'solid' header, 'vertex x y z' lines)."""
    data = Path(path).read_bytes()
    verts = []
    if data[:5].lower() == b"solid":
        for line in data.decode("ascii", "strict").splitlines():
            line = line.strip()
            if line.startswith("vertex "):
                parts = line.split()
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
        return verts
    if len(data) < 84:
        raise ValueError("STL too short")
    count = struct.unpack_from("<I", data, 80)[0]
    off = 84
    for _ in range(count):
        values = struct.unpack_from("<12fH", data, off)
        off += 50
        verts.extend([(values[3], values[4], values[5]),
                      (values[6], values[7], values[8]),
                      (values[9], values[10], values[11])])
    return verts


def read_degen_points(path):
    """Return (x, y, z) nodes from every SURFACE_NODE block of the DegenGeom CSV.

    The file is section-based: "# DegenGeom Type,nXsecs, nPnts/Xsec", then
    "SURFACE_NODE,<nXsecs>,<nPnts>", then "# x,y,z,u,w", then nXsecs*nPnts rows.
    """
    lines = Path(path).read_text(encoding="utf-8", errors="strict").splitlines()
    points = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("SURFACE_NODE,"):
            parts = [p.strip() for p in line.split(",")]
            count = int(parts[1]) * int(parts[2])
            i += 1
            while i < len(lines) and not lines[i].startswith("#"):
                i += 1
            i += 1  # skip "# x,y,z,u,w"
            for _ in range(count):
                row = [p.strip() for p in lines[i].split(",")]
                points.append((float(row[0]), float(row[1]), float(row[2])))
                i += 1
        else:
            i += 1
    return points


def isa(h):
    t = 288.15 - 0.0065 * min(h, 11000.0)
    p = 101325.0
    if h <= 11000.0:
        p = 101325.0 * (1 - 0.0065 * h / 288.15) ** 5.25588
    else:
        p11 = 101325.0 * (1 - 0.0065 * 11000.0 / 288.15) ** 5.25588
        p = p11 * math.exp(-G * (h - 11000.0) / (R * 216.65))
        t = 216.65
    rho = p / (R * t)
    a = math.sqrt(1.4 * R * t)
    return {"temperature_k": t, "pressure_pa": p, "density_kg_m3": rho,
            "speed_of_sound_m_s": a, "vinf_m_s": MACH * a}


def mu_sutherland(t):
    return 1.458e-6 * t ** 1.5 / (t + 110.4)


def template_text(sref, cref, bref, mach, alpha, vinf, rho, re_cref):
    return (
        "Sref = %.6f\n" % sref +
        "Cref = %.6f\n" % cref +
        "Bref = %.6f\n" % bref +
        "X_cg = 0.000000\nY_cg = 0.000000\nZ_cg = 0.000000\n" +
        "Mach = %.6f\n" % mach +
        "AoA = %.6f\n" % alpha +
        "Beta = 0.000000\n" +
        "Vinf = %.6f\n" % vinf +
        "Vref = %.6f\n" % vinf +
        "Machref = 0.300000\n" +
        "Rho = %.8f\n" % rho +
        "ReCref = %.6f\n" % re_cref +
        "ClMax = -1.000000\nClo2D = 0.000000\nMaxTurningAngle = -1.000000\n" +
        "Symmetry = NO\n" +
        "FarDist = -1.000000\nNumWakeNodes = -1\nWakeIters = 5\n" +
        "NumberOfRotors = 0\nNumberOfControlGroups = 0\n"
    )


def main():
    sref, cref, bref = 358.25, 18.489893, 25.604638
    atm = isa(H)
    mu = mu_sutherland(atm["temperature_k"])
    re_cref = atm["density_kg_m3"] * atm["vinf_m_s"] * cref / mu
    report = {
        "run_id": "p1p3-fullchain-20261031T0407Z",
        "case": "LF geometry validation (wing-only, thin surface)",
        "conditions": {"mach": MACH, "altitude_m": H, **atm,
                       "viscosity_pa_s": mu, "reynolds_per_cref": re_cref,
                       "sref_m2": sref, "cref_m": cref, "bref_m": bref},
        "cases": {},
        "w10_twist_check": {},
        "status": "UNKNOWN",
    }
    for name, cdir in CASES.items():
        base = cdir / ("main_wing_%s" % name)
        stl = Path(str(base) + ".stl")
        vsp3 = Path(str(base) + ".vsp3")
        degen = Path(str(base) + "_DegenGeom.csv")
        verts = read_stl_vertices(stl)
        degen_pts = read_degen_points(degen)
        report["cases"][name] = {
            "stl": {"path": str(stl.name), "bytes": stl.stat().st_size, "sha256": sha256(stl),
                    "format": "ascii", "triangles": len(verts) // 3, "vertices": len(verts)},
            "vsp3": {"path": str(vsp3.name), "bytes": vsp3.stat().st_size, "sha256": sha256(vsp3)},
            "degen_geom_csv": {"path": str(degen.name), "bytes": degen.stat().st_size,
                               "sha256": sha256(degen), "surface_points": len(degen_pts)},
            "request_sha256": sha256(cdir / "request.json"),
            "worker_result_sha256": sha256(cdir / "worker_result.json"),
        }
        # Prepare a locked VSPAERO template for a single-point alpha sweep.
        template = template_text(sref, cref, bref, MACH, 1.0, atm["vinf_m_s"], atm["density_kg_m3"], re_cref)
        (cdir / ("main_wing_%s_DegenGeom.vspaero" % name)).write_text(template, encoding="utf-8")
    # W10 twist delta from STL vertices (index-preserving tessellation expected).
    vb = read_stl_vertices(CASES["baseline"] / "main_wing_baseline.stl")
    vw = read_stl_vertices(CASES["w10_plus2"] / "main_wing_w10_plus2.stl")
    same_count = len(vb) == len(vw)
    stats = {"vertex_count_baseline": len(vb), "vertex_count_w10": len(vw),
             "same_vertex_count": same_count}
    if same_count:
        d = [(wx - bx, wy - by, wz - bz) for (bx, by, bz), (wx, wy, wz) in zip(vb, vw)]
        moved = [v for v in d if abs(v[0]) + abs(v[1]) + abs(v[2]) > 1e-9]
        stats.update({
            "max_abs_dx_m": max(abs(v[0]) for v in d),
            "max_abs_dy_m": max(abs(v[1]) for v in d),
            "max_abs_dz_m": max(abs(v[2]) for v in d),
            "moved_vertices": len(moved),
            "expected_max_abs_dz_m": math.sin(math.radians(2.0)) * 0.973136,
        })
        stats["dz_matches_twist_within_1e_6"] = abs(stats["max_abs_dz_m"] - stats["expected_max_abs_dz_m"]) <= 1e-6
        stats["dy_negligible"] = stats["max_abs_dy_m"] < 1e-6
    # DegenGeom surface point delta.
    pb = read_degen_points(CASES["baseline"] / "main_wing_baseline_DegenGeom.csv")
    pw = read_degen_points(CASES["w10_plus2"] / "main_wing_w10_plus2_DegenGeom.csv")
    stats["degen_point_count_baseline"] = len(pb)
    stats["degen_point_count_w10"] = len(pw)
    if len(pb) == len(pw):
        md = [(wx - bx, wy - by, wz - bz) for (bx, by, bz), (wx, wy, wz) in zip(pb, pw)]
        stats["degen_max_abs_dz_m"] = max(abs(v[2]) for v in md)
        stats["degen_max_abs_dy_m"] = max(abs(v[1]) for v in md)
        stats["degen_max_abs_dx_m"] = max(abs(v[0]) for v in md)
        stats["degen_dz_matches_twist_within_1e_5"] = (
            abs(stats["degen_max_abs_dz_m"] - stats["expected_max_abs_dz_m"]) <= 1e-5)
    report["w10_twist_check"] = stats
    ok = (stats.get("same_vertex_count")
          and stats.get("dz_matches_twist_within_1e_6")
          and stats.get("dy_negligible")
          and stats.get("degen_dz_matches_twist_within_1e_5"))
    report["status"] = "GEOMETRY_VALIDATED_WITH_WARNINGS" if ok else "GEOMETRY_CHECK_FAILED"
    report["warnings"] = [
        "LF geometry is wing-only; fuselage and vertical tail are not in the LF thin surface (owner decision 4 / D-12D-002 lifting-surfaces-only).",
        "OpenVSP thin-surface DegenGeom is a geometry idealisation, not aerodynamic evidence.",
        "CG is provisional; the VSPAERO template uses X/Y/Z_cg = 0 and moments are reported about that provisional point.",
    ]
    out = EXT / "lead" / "geometry_validation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "conditions": report["conditions"],
                      "w10": stats}, indent=1))


if __name__ == "__main__":
    main()
