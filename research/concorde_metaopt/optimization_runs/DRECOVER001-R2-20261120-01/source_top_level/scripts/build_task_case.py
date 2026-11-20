import argparse, hashlib, json, math, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/drecover001-20261117")
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.dreal001.geometry import openvsp_model
from research.concorde_metaopt.dreal001.geometry.task_spec import TASK_SPEC
from research.concorde_metaopt.dreal001.meta.task_spec import TaskSpec

RUN_ID = "DRECOVER001-R2-20261120-01"
BATCH_ID = "DRECOVER001-R2-20261120-01-B01"  # default; override with --batch-id
AUTH_ID = "AUTH-DRECOVER001-R2-20261120-01"
RUN_ROOT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
CASE_ROOT = RUN_ROOT / "cases"
GEOMETRY_CONTRACT = "5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15"
LIFT_N = 1333704.4
ALT_M = 18288.0
BASE_MACH = 2.02
BASE_VINF = 596.0373972278921
BASE_RHO = 0.1153178340089936
BASE_RECREF = 89397005.8767656
BASE_CL_AT_518125 = 0.181741590896
BASE_SLOPE_PER_DEG = 0.03439426999999901

NAMES = ["wing_area","aspect_ratio","sweep_1","sweep_2","sweep_3","span_location_2",
         "span_location_3","chord_ratio_2","chord_ratio_3","tip_twist",
         "vertical_tail_area","vertical_tail_sweep_delta","fuselage_length",
         "fuselage_fineness","fuselage_height_width_ratio"]
BASELINE = [358.25,1.83,67.0,48.0,71.0,0.480469,0.945313,0.408284,0.130178,0.0,
            33.91,0.0,61.66,4.30,1.152778]
DESIGNS = {
    "d00": BASELINE[:],
    "d01": BASELINE[:],   # wing area +1%
    "d02": BASELINE[:],   # sweep_1 +0.5 deg
    "d03": BASELINE[:],   # wing area -1%
    "d04": BASELINE[:],   # sweep_1 -0.5 deg
}
DESIGNS["d01"][0] = 361.8325
DESIGNS["d02"][2] = 67.5
DESIGNS["d03"][0] = 354.6675
DESIGNS["d04"][2] = 66.5

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def canon(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--basename", required=True)
    ap.add_argument("--mach", type=float, required=True)
    ap.add_argument("--split", required=True, choices=["train", "val", "test"])
    ap.add_argument("--partition", required=True, choices=["support", "query"])
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--design", default="d00", choices=sorted(DESIGNS))
    ap.add_argument("--alpha-center", type=float, default=None)
    ap.add_argument("--alpha-points", type=int, default=15)
    ap.add_argument("--alpha-step", type=float, default=0.0025)
    ap.add_argument("--max-starts", type=int, default=12)
    ap.add_argument("--batch-id", default=BATCH_ID)
    ap.add_argument("--window-token", default=AUTH_ID + "-B01-WINDOW")
    ap.add_argument("--window-end", default="2026-11-20T18:44:39Z")
    ap.add_argument("--purpose", required=True)
    a = ap.parse_args()

    values = DESIGNS[a.design][:]
    x12 = values[:12]
    geometry = build_geometry(NAMES, values)
    sref = float(geometry.wing.area_m2)

    vinf = a.mach * (BASE_VINF / BASE_MACH)
    recref = BASE_RECREF * (vinf / BASE_VINF)
    q_pa = 0.5 * BASE_RHO * vinf * vinf
    cl_target = LIFT_N / (q_pa * sref)
    if a.alpha_center is None:
        alpha_center = 5.18125 + (cl_target - BASE_CL_AT_518125) / BASE_SLOPE_PER_DEG
    else:
        alpha_center = float(a.alpha_center)
    n = int(a.alpha_points)
    if n < 3 or n % 2 == 0:
        raise SystemExit("--alpha-points must be odd and >=3")
    half = (n - 1) / 2.0
    alphas = [round(alpha_center + (i - half) * a.alpha_step, 10) for i in range(n)]
    low, high = TASK_SPEC.alpha_window_deg
    if min(alphas) < low or max(alphas) > high:
        raise SystemExit("alpha grid outside window %r: %r" % ((low, high), (min(alphas), max(alphas))))

    case_dir = CASE_ROOT / a.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    flow = {"vinf_m_s": vinf, "rho_kg_m3": BASE_RHO, "recref": recref}
    record = openvsp_model.prepare_case(
        geometry, case_dir, a.basename, geometry_set="thin",
        alphas_deg=alphas, tess_u=12, tess_w=25, n_wake_nodes=8,
        mach_values=[a.mach], flow_conditions=flow,
    )
    exe = Path(r"D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe")
    vspgeom = case_dir / (a.basename + ".vspgeom")
    vkey = case_dir / (a.basename + ".vkey")
    vspaero = case_dir / (a.basename + ".vspaero")
    argv = [str(exe), "-omp", "1", a.basename]
    design_id = canon(x12)
    plan = {
      "schema": "dreal001.solver_plan.v1",
      "run_id": RUN_ID, "batch_id": a.batch_id,
      "task_id": a.task_id,
      "case_id": a.case_id,
      "purpose": a.purpose,
      "solver": {"path": str(exe), "sha256": sha(exe), "cwd": str(case_dir),
                 "version_banner": openvsp_model.EXPECTED_VSPAERO_VERSION,
                 "omp_threads": 1, "timeout_s": 1200,
                 "solver_config_hash": sha(vspaero)},
      "command": {"argv": argv},
      "geometry": {"files": {
           "vspgeom": {"path": str(vspgeom), "sha256": sha(vspgeom)},
           "vkey": {"path": str(vkey), "sha256": sha(vkey)},
           "vspaero": {"path": str(vspaero), "sha256": sha(vspaero)}},
         "sref_m2": sref,
         "geometry_sha256": sha(vspgeom),
         "design_hash": design_id},
      "design": {"design_hash": design_id, "x12": x12},
      "budget": {"physical_solver_starts_max": a.max_starts,
                  "expected_internal_cases": len(alphas),
                  "max_internal_cases": 128},
    }
    plan_path = case_dir / "plan.json"
    plan_bytes = json.dumps(plan, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    plan_path.write_bytes(plan_bytes)
    now = datetime.now(timezone.utc)
    approval = {
      "schema": "dreal001.solver_approval.v1",
      "approved": True,
      "authorization_id": AUTH_ID,
      "owner_message_ref": "m05968",
      "run_id": RUN_ID, "batch_id": a.batch_id, "case_id": a.case_id,
      "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
      "max_starts": a.max_starts,
      "window": {"start_utc": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "end_utc": a.window_end,
                  "token": a.window_token},
      "window_token": a.window_token,
    }
    approval_path = case_dir / "approval.json"
    approval_path.write_text(json.dumps(approval, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    task = TaskSpec(task_id=a.task_id, split=a.split, mach=a.mach, altitude_m=ALT_M,
                    dynamic_pressure_pa=q_pa, lift_target_n=LIFT_N,
                    geometry_contract_sha256=GEOMETRY_CONTRACT,
                    lift_tolerance_rel=1e-3)
    spec = {
      "schema": "dreal001.r2_task_spec.v1",
      "task_id": a.task_id, "split": a.split, "partition": a.partition,
      "case_id": a.case_id, "design": a.design, "design_id": design_id,
      "x12": x12, "mach": a.mach, "altitude_m": ALT_M,
      "dynamic_pressure_pa": q_pa, "lift_target_n": LIFT_N,
      "geometry_contract_sha256": GEOMETRY_CONTRACT, "lift_tolerance_rel": 1e-3,
      "flow_conditions": flow, "alpha_center_deg": alpha_center,
      "alpha_grid_deg": alphas, "cl_target": cl_target, "sref_m2": sref,
      "task_physics_sha256": task.physics_sha256,
    }
    (case_dir / "task_spec.json").write_text(
        json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
      "case_id": a.case_id, "case_dir": str(case_dir), "mach": a.mach,
      "split": a.split, "partition": a.partition, "design": a.design,
      "design_id": design_id, "sref_m2": sref, "q_pa": q_pa,
      "vinf_m_s": vinf, "recref": recref, "cl_target": cl_target,
      "alpha_center_deg": alpha_center, "alphas": alphas,
      "geometry_sha256": plan["geometry"]["geometry_sha256"],
      "vspgeom_header": record["vspgeom_header"], "mesh": record.get("mesh"),
      "plan_sha256": approval["plan_sha256"], "task_physics_sha256": task.physics_sha256,
      "plan": str(plan_path), "approval": str(approval_path),
      "task_spec": str(case_dir / "task_spec.json"),
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
