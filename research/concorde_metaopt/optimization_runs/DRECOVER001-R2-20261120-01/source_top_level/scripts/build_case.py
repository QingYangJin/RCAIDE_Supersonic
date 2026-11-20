import argparse, hashlib, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/drecover001-20261117")
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.dreal001.geometry import openvsp_model

RUN_ID = "DRECOVER001-R2-20261120-01"
BATCH_ID = "DRECOVER001-R2-20261120-01-B01"
AUTH_ID = "AUTH-DRECOVER001-R2-20261120-01"
RUN_ROOT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
CASE_ROOT = RUN_ROOT / "cases"

NAMES = ["wing_area","aspect_ratio","sweep_1","sweep_2","sweep_3","span_location_2",
         "span_location_3","chord_ratio_2","chord_ratio_3","tip_twist",
         "vertical_tail_area","vertical_tail_sweep_delta","fuselage_length",
         "fuselage_fineness","fuselage_height_width_ratio"]
VALUES = [358.25,1.83,67.0,48.0,71.0,0.480469,0.945313,0.408284,0.130178,0.0,
          33.91,0.0,61.66,4.30,1.152778]
X12 = VALUES[:12]

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""): h.update(chunk)
    return h.hexdigest()

def canon(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--basename", required=True)
    ap.add_argument("--alphas", required=True, help="comma-separated alpha grid")
    ap.add_argument("--purpose", required=True)
    ap.add_argument("--max-starts", type=int, default=12)
    ap.add_argument("--expected-internal", type=int, required=True)
    ap.add_argument("--max-internal", type=int, default=128)
    args = ap.parse_args()
    alphas = [float(x) for x in args.alphas.split(",")]
    case_dir = CASE_ROOT / args.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    geometry = build_geometry(NAMES, VALUES)
    record = openvsp_model.prepare_case(
        geometry, case_dir, args.basename, geometry_set="thin",
        alphas_deg=alphas, tess_u=12, tess_w=25, n_wake_nodes=8,
    )
    exe = Path(r"D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe")
    vspgeom = case_dir / (args.basename + ".vspgeom")
    vkey = case_dir / (args.basename + ".vkey")
    vspaero = case_dir / (args.basename + ".vspaero")
    argv = [str(exe), "-omp", "1", args.basename]
    plan = {
      "schema": "dreal001.solver_plan.v1",
      "run_id": RUN_ID, "batch_id": BATCH_ID,
      "task_id": "concorde-fixed-cruise-dreal001-real-v1",
      "case_id": args.case_id,
      "purpose": args.purpose,
      "solver": {"path": str(exe), "sha256": sha(exe), "cwd": str(case_dir),
                 "version_banner": openvsp_model.EXPECTED_VSPAERO_VERSION,
                 "omp_threads": 1, "timeout_s": 1200,
                 "solver_config_hash": sha(vspaero)},
      "command": {"argv": argv},
      "geometry": {"files": {
           "vspgeom": {"path": str(vspgeom), "sha256": sha(vspgeom)},
           "vkey": {"path": str(vkey), "sha256": sha(vkey)},
           "vspaero": {"path": str(vspaero), "sha256": sha(vspaero)}},
         "sref_m2": float(geometry.wing.area_m2),
         "geometry_sha256": sha(vspgeom),
         "design_hash": sha(vspgeom)},
      "design": {"design_hash": canon(X12), "x12": X12},
      "budget": {"physical_solver_starts_max": args.max_starts,
                  "expected_internal_cases": args.expected_internal,
                  "max_internal_cases": args.max_internal},
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
      "run_id": RUN_ID, "batch_id": BATCH_ID, "case_id": args.case_id,
      "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
      "max_starts": args.max_starts,
      "window": {"start_utc": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "end_utc": (now + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "token": AUTH_ID + "-B01-WINDOW"},
      "window_token": AUTH_ID + "-B01-WINDOW",
    }
    approval_path = case_dir / "approval.json"
    approval_path.write_text(json.dumps(approval, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
      "case_id": args.case_id, "case_dir": str(case_dir),
      "alphas": alphas, "expected_internal": args.expected_internal,
      "geometry_sha256": plan["geometry"]["geometry_sha256"],
      "vspgeom_header": record["vspgeom_header"],
      "mesh": record.get("mesh"),
      "plan_sha256": approval["plan_sha256"],
      "plan": str(plan_path), "approval": str(approval_path),
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
