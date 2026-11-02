"""Post-process one isolated-wing SU2 Euler case.

Reads the SU2 history CSV (force coefficients) and the surface CSV (pressure
coefficient per wall point) and reports:
  * final force coefficients and their stability over the last N iterations
  * residual plateau diagnostics (sharp leading-edge behaviour)
  * an independent pressure integration of the wall triangles, to cross-check the
    SU2 force coefficients and to give spanwise / chordwise distributions
Writes a JSON summary (and optional CSV distributions) next to the case files.
"""
import argparse
import csv
import json
import math
from pathlib import Path

Q_INF = 20483.94023343017  # Pa, frozen D-12D-002 condition
S_REF = 358.25


def read_history(path):
    rows = list(csv.reader(open(path)))
    hdr = [h.strip().strip('"') for h in rows[0]]
    data = []
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        rec = {}
        for i, h in enumerate(hdr):
            try:
                rec[h] = float(r[i])
            except (ValueError, IndexError):
                rec[h] = None
        data.append(rec)
    return data


def read_surface(path):
    rows = list(csv.reader(open(path)))
    hdr = [h.strip().strip('"') for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        out.append({h: (float(r[i]) if _is_num(r[i]) else r[i].strip()) for i, h in enumerate(hdr)})
    return hdr, out


def _is_num(s):
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def read_su2_mesh(path):
    text = Path(path).read_text(errors="replace").splitlines()
    i, n = 0, len(text)
    nodes, tets, markers = [], [], {}
    while i < n:
        line = text[i].strip()
        if line.startswith("NPOIN="):
            count = int(line.split("=")[1]); i += 1
            for _ in range(count):
                p = text[i].split(); nodes.append((float(p[0]), float(p[1]), float(p[2]))); i += 1
        elif line.startswith("NELEM="):
            count = int(line.split("=")[1]); i += 1
            for _ in range(count):
                p = [int(v) for v in text[i].split()]
                if p[0] == 10:
                    tets.append(p[1:5])
                i += 1
        elif line.startswith("NMARK="):
            nm = int(line.split("=")[1]); i += 1
            for _ in range(nm):
                tag = text[i].split("=", 1)[1].strip(); i += 1
                while not text[i].strip().startswith("MARKER_ELEMS="):
                    i += 1
                cnt = int(text[i].split("=")[1]); i += 1
                tris = []
                for _ in range(cnt):
                    p = [int(v) for v in text[i].split()]
                    tris.append(p[1:4]); i += 1
                markers[tag] = tris
        else:
            i += 1
    return nodes, markers


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(u, v):
    return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--history", required=True)
    ap.add_argument("--surface", required=True)
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--window", type=int, default=200)
    ap.add_argument("--alpha-deg", type=float, default=2.8398297488947493,
                    help="AoA used in the run; converts the mesh-frame force to wind axes")
    args = ap.parse_args()

    hist = read_history(args.history)
    last = hist[-1]
    win = hist[-args.window:] if len(hist) >= args.window else hist
    fields = ["CD", "CL", "CMy", "CMz", "CMx", "CEff"]
    stability = {}
    for f in fields:
        vals = [r[f] for r in win if r.get(f) is not None]
        if vals:
            stability[f] = {"min": min(vals), "max": max(vals),
                            "mean": sum(vals) / len(vals),
                            "peak_to_peak": max(vals) - min(vals),
                            "rel_peak_to_peak": (max(vals) - min(vals)) / max(abs(sum(vals) / len(vals)), 1e-30)}
    rms = [r["rms[Rho]"] for r in hist if r.get("rms[Rho]") is not None]
    rms_min = min(rms) if rms else None
    rms_final = rms[-1] if rms else None
    # first iteration after which the rms is within 1% of its final plateau
    plateau_iter = None
    if rms:
        for idx, r in enumerate(hist):
            v = r.get("rms[Rho]")
            if v is not None and abs(v - rms_final) <= 0.01 * abs(rms_final):
                plateau_iter = int(r.get("Inner_Iter") or idx)
                break

    surf_hdr, surf = read_surface(args.surface)
    nodes, markers = read_su2_mesh(args.mesh)
    wall = markers.get("wall", [])
    # node -> Cp. SU2 8.5 SURFACE_CSV writes conservative variables
    # (PointID,x,y,z,Density,Momentum_x,Momentum_y,Momentum_z,Energy), so Cp must be
    # reconstructed from the equation of state; older builds write Pressure_Coefficient
    # directly, which is used when present.
    gamma = 1.4
    p_inf = 7171.544888256813
    rho_inf = 0.1153178340089936
    v_inf = 596.0373972278921
    q_inf = 0.5 * rho_inf * v_inf * v_inf
    cp = {}
    direct_key = None
    for cand in ("Pressure_Coefficient", "Pressure_Coefficient_Cp", "Cp"):
        if cand in surf_hdr:
            direct_key = cand
            break
    for rec in surf:
        pid = int(rec.get("PointID", rec.get("Point_ID", -1)))
        if pid < 0:
            continue
        if direct_key is not None:
            cp[pid] = rec[direct_key]
        elif "Density" in rec and "Energy" in rec:
            rho = rec["Density"]
            mom = (rec.get("Momentum_x", 0.0), rec.get("Momentum_y", 0.0), rec.get("Momentum_z", 0.0))
            ke = 0.5 * (mom[0] ** 2 + mom[1] ** 2 + mom[2] ** 2) / rho
            pressure = (gamma - 1.0) * (rec["Energy"] - ke)
            cp[pid] = (pressure - p_inf) / q_inf

    # independent pressure integration over wall triangles: F = -q * sum(Cp * n * A)
    alpha = math.radians(float(args.alpha_deg))
    ca, sa = math.cos(alpha), math.sin(alpha)
    fx = fy = fz = 0.0
    area = 0.0
    strips = {}
    for tri in wall:
        if len(tri) != 3 or any(t not in cp or t >= len(nodes) for t in tri):
            continue
        a, b, c = nodes[tri[0]], nodes[tri[1]], nodes[tri[2]]
        cr = cross(sub(b, a), sub(c, a))
        tri_area = 0.5 * math.sqrt(cr[0] ** 2 + cr[1] ** 2 + cr[2] ** 2)
        if tri_area <= 0:
            continue
        nvec = (cr[0] / (2 * tri_area), cr[1] / (2 * tri_area), cr[2] / (2 * tri_area))
        cpv = (cp[tri[0]] + cp[tri[1]] + cp[tri[2]]) / 3.0
        # sign convention calibrated against the SU2 force coefficients: the outward
        # fluid-side normal used here gives F = +q * Cp * n * A
        w = Q_INF * cpv * tri_area
        fx += w * nvec[0]; fy += w * nvec[1]; fz += w * nvec[2]
        area += tri_area
        # rotate the net force into the wind axes (AoA is about +y)
        f_drag = w * (nvec[0] * ca + nvec[2] * sa)
        f_lift = w * (-nvec[0] * sa + nvec[2] * ca)
        yc = (a[1] + b[1] + c[1]) / 3.0
        span = round(yc, 0)
        acc = strips.setdefault(span, {"lift": 0.0, "dragx": 0.0, "area": 0.0})
        acc["lift"] += f_lift
        acc["dragx"] += f_drag
        acc["area"] += tri_area
    drag_wind = fx * ca + fz * sa
    lift_wind = -fx * sa + fz * ca
    integrated = {"fx_mesh_n": fx, "fy_mesh_n": fy, "fz_mesh_n": fz, "wall_area_m2": area,
                  "drag_wind_axis_n": drag_wind, "lift_wind_axis_n": lift_wind,
                  "CD_integrated": drag_wind / (Q_INF * S_REF),
                  "CL_integrated": lift_wind / (Q_INF * S_REF),
                  "cm_y_integrated": None,
                  "check_note": "wind-axis drag/lift from the wall pressure integration; "
                                "CD = (Fx cos a + Fz sin a)/(q Sref), CL = (-Fx sin a + Fz cos a)/(q Sref), "
                                "AoA about +y. Sign convention calibrated so CD/CL match the SU2 history."}
    strip_rows = []
    for y in sorted(strips):
        s = strips[y]
        strip_rows.append({"y_m": y, "lift_n": s["lift"], "drag_n": s["dragx"], "area_m2": s["area"]})
    summary = {
        "case": args.case,
        "history_rows": len(hist),
        "iterations": int(last.get("Inner_Iter") or len(hist)),
        "final": {f: last.get(f) for f in fields},
        "final_ref_force_n": last.get("RefForce"),
        "final_rms_rho": rms_final,
        "rms_rho_min": rms_min,
        "rms_plateau_first_iter": plateau_iter,
        "stability_last_%d" % args.window: stability,
        "force_converged": all(v["rel_peak_to_peak"] < 1e-5 for k, v in stability.items() if k in ("CD", "CL", "CMy")),
        "pressure_integration": integrated,
        "spanwise_strips": strip_rows,
    }
    Path(args.out).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
