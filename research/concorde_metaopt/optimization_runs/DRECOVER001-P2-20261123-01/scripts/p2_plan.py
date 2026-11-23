
"""Freeze the P2 supplement matrix (16 starts) from zero-physical G2 stage-1 polars."""
import hashlib, json, sys
from pathlib import Path
REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
G2 = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01")
OUT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.dreal001.geometry.polar_rows import read_polar_rows

LIFT = 1333704.4
BASE_MACH, BASE_VINF, BASE_RHO = 2.02, 596.0373972278921, 0.1153178340089936
NAMES = ["wing_area","aspect_ratio","sweep_1","sweep_2","sweep_3","span_location_2",
         "span_location_3","chord_ratio_2","chord_ratio_3","tip_twist",
         "vertical_tail_area","vertical_tail_sweep_delta","fuselage_length",
         "fuselage_fineness","fuselage_height_width_ratio"]
BASELINE = [358.25,1.83,67.0,48.0,71.0,0.480469,0.945313,0.408284,0.130178,0.0,
            33.91,0.0,61.66,4.30,1.152778]
DES = {k: BASELINE[:] for k in ("d00","d01","d02","d03")}
DES["d01"][0] = 361.8325
DES["d02"][2] = 67.5
DES["d03"][0] = 354.6675
TAGS = {140: "m140", 160: "m160", 180: "m180", 200: "m200", 202: "m202", 220: "m220", 240: "m240", 260: "m260"}
# 16 frozen starts: task mach, design, partition
PLAN = []
for mach in (140, 220, 260):
    for d in ("d00","d01","d02"):
        PLAN.append({"mach": mach, "design": d, "partition": "support"})
    PLAN.append({"mach": mach, "design": "d03", "partition": "query"})
PLAN += [{"mach": 240, "design": d, "partition": "support"} for d in ("d01","d03")]
PLAN += [{"mach": 202, "design": "d02", "partition": "support"}]
PLAN += [{"mach": 180, "design": "d02", "partition": "support"}]
assert len(PLAN) == 16, len(PLAN)

def can(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

rows_out = []
for item in PLAN:
    mach = item["mach"]; d = item["design"]
    tag = TAGS[mach]
    case = G2 / "cases" / ("g2-%s-%s-support-s1" % (tag, d))
    if not case.exists():
        case = G2 / "cases" / ("g2-%s-%s-query-s1" % (tag, d))
    polar = next(case.glob("*.polar"))
    rows = read_polar_rows(polar, mach=mach / 100.0)
    vals = DES[d]
    geom = build_geometry(NAMES, vals)
    sref = float(geom.wing.area_m2)
    vinf = (mach / 100.0) * (BASE_VINF / BASE_MACH)
    q = 0.5 * BASE_RHO * vinf * vinf
    clt = LIFT / (q * sref)
    srt = sorted((r.alpha_deg, r.cl) for r in rows)
    br = None
    for (a1,c1),(a2,c2) in zip(srt, srt[1:]):
        if c1 <= clt <= c2:
            br = (a1,c1,a2,c2,(c2-c1)/(a2-a1)); break
    assert br, (mach, d, clt)
    a1,c1,a2,c2,slope = br
    alpha_t = a1 + (clt - c1) / slope
    half = 0.004
    # Every probe must stay inside the raw coarse bracket: clamp the centre, never extrapolate.
    center = min(max(alpha_t, a1 + half), a2 - half)
    alphas = [round(center + off, 6) for off in (-half, 0.0, half)]
    assert a1 <= min(alphas) and max(alphas) <= a2, (mach, d, alphas, a1, a2)
    assert all(-2.0 <= a <= 10.0 for a in alphas), alphas
    assert min(r[0] for r in srt) <= min(alphas) and max(alphas) <= max(r[0] for r in srt), (mach, d, alphas, srt[-1])
    alpha_t = center
    rows_out.append({"mach": mach, "tag": tag, "design": d, "partition": item["partition"],
                     "task_id": "P2-CANON-M%d" % mach,
                     "split": "train" if mach in (140,160,200,202) else ("val" if mach in (180,220) else "test"),
                     "stage1_case_dir": str(case), "stage1_polar": str(polar),
                     "stage1_polar_sha256": hashlib.sha256(polar.read_bytes()).hexdigest(),
                     "q_pa": q, "sref_m2": sref, "cl_target": clt,
                     "bracket_alpha_deg": [a1, a2], "bracket_cl": [c1, c2],
                     "slope_cl_per_deg": slope, "alpha_target_deg": alpha_t,
                     "alpha_grid_deg": alphas, "design_x12": vals[:12],
                     "design_id": can(vals[:12])})
plan = {"schema": "dreal004.p2_supplement_plan.v1",
        "run_id": "DRECOVER001-P2-20261123-01",
        "batch_id": "DRECOVER001-P2-20261123-01-B01",
        "authorization_id": "AUTH-DREAL004-P2-20261123-01",
        "created_utc": "2026-11-23T15:10:00Z",
        "max_starts": 16, "starts": len(rows_out),
        "max_internal_solver_cases": 48, "max_alpha_probes_per_start": 3,
        "parallelism": 1, "timeout_s_per_start": 600, "retries": 0,
        "wall_clock_max_s": 9600,
        "bracket_provenance": "zero-physical G2 stage-1 polars (49 alpha rows, Mach per task); no solver start used",
        "starts_plan": rows_out}
p = OUT / "p2_supplement_plan.json"
p.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print("wrote", p)
for r in rows_out:
    print(r["task_id"], r["design"], r["partition"], "clt=%.6f" % r["cl_target"], "alpha_t=%.4f" % r["alpha_target_deg"], r["alpha_grid_deg"])
