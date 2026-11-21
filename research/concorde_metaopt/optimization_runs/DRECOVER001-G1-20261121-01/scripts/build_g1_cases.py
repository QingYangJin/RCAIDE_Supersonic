
import argparse, hashlib, json, math, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120")
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.dreal001.geometry import openvsp_model
from research.concorde_metaopt.dreal001.geometry.task_spec import TASK_SPEC
from research.concorde_metaopt.dreal001.meta.task_spec import TaskSpec

RUN_ID = "DRECOVER001-G1-20261121-01"
BATCH_ID = "DRECOVER001-G1-20261121-01-B01"
AUTH_ID = "AUTH-DREAL003-G1-20261121-01"
OWNER_REF = "m07992"
RUN_ROOT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01")
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
WINDOW_END = "2026-11-22T12:00:00Z"

NAMES = ["wing_area","aspect_ratio","sweep_1","sweep_2","sweep_3","span_location_2",
         "span_location_3","chord_ratio_2","chord_ratio_3","tip_twist",
         "vertical_tail_area","vertical_tail_sweep_delta","fuselage_length",
         "fuselage_fineness","fuselage_height_width_ratio"]
BASELINE = [358.25,1.83,67.0,48.0,71.0,0.480469,0.945313,0.408284,0.130178,0.0,
            33.91,0.0,61.66,4.30,1.152778]
DESIGNS = {k: BASELINE[:] for k in ("d00","d01","d02","d03","d04","d05")}
DESIGNS["d01"][0] = 361.8325      # wing area +1%
DESIGNS["d02"][2] = 67.5          # sweep_1 +0.5 deg
DESIGNS["d03"][0] = 354.6675      # wing area -1%
DESIGNS["d04"][2] = 66.5          # sweep_1 -0.5 deg
DESIGNS["d05"][10] = 34.5882      # vertical tail area +2%, lift-neutral intent
TASKS = [
    ("160", "DREAL003-G1-M160", 1.60, "train"),
    ("180", "DREAL003-G1-M180", 1.80, "val"),
    ("202", "DREAL003-G1-M202", 2.02, "train"),
    ("240", "DREAL003-G1-M240", 2.40, "test"),
]
SUPPORT_DESIGNS = ("d00","d01","d02")
QUERY_DESIGNS = ("d03","d04","d05")

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def canon(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()

def spec_for(tag, task_id, mach, split, design, partition):
    values = DESIGNS[design][:]
    x12 = values[:12]
    geometry = build_geometry(NAMES, values)
    sref = float(geometry.wing.area_m2)
    vinf = mach * (BASE_VINF / BASE_MACH)
    recref = BASE_RECREF * (vinf / BASE_VINF)
    q_pa = 0.5 * BASE_RHO * vinf * vinf
    cl_target = LIFT_N / (q_pa * sref)
    alpha_center = 5.18125 + (cl_target - BASE_CL_AT_518125) / BASE_SLOPE_PER_DEG
    n = 17
    step = 0.03
    half = (n - 1) / 2.0
    alphas = [round(alpha_center + (i - half) * step, 10) for i in range(n)]
    low, high = TASK_SPEC.alpha_window_deg
    if min(alphas) < low or max(alphas) > high:
        raise SystemExit("alpha grid outside window %r: %r" % ((low, high), (min(alphas), max(alphas))))
    case_id = "g1-m%s-%s-%s" % (tag, design, partition)
    return dict(case_id=case_id, basename=case_id, task_id=task_id, split=split,
                partition=partition, design=design, mach=mach, values=values, x12=x12,
                sref=sref, vinf=vinf, recref=recref, q_pa=q_pa, cl_target=cl_target,
                alpha_center=alpha_center, alphas=alphas)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    CASE_ROOT.mkdir(parents=True, exist_ok=True)
    specs = []
    for tag, task_id, mach, split in TASKS:
        for design in SUPPORT_DESIGNS:
            specs.append(spec_for(tag, task_id, mach, split, design, "support"))
        for design in QUERY_DESIGNS:
            specs.append(spec_for(tag, task_id, mach, split, design, "query"))
    prereg = {
        "schema": "dreal003.g1_preregistration.v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "owner_message_ref": OWNER_REF,
        "authorization_id": AUTH_ID,
        "run_id": RUN_ID,
        "batch_id": BATCH_ID,
        "branch": "research/dreal003-expanded-aero-meta-20261120",
        "base_commit": "35d1f115637c3aa57521eec8458cef706944c4af",
        "geometry_contract_sha256": GEOMETRY_CONTRACT,
        "solver": {
            "path": r"D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe",
            "name": "vspaero-3.55.0-v7.2.2-omp1",
            "omp_threads": 1,
            "case_timeout_s": 1200,
            "parallelism": 1,
            "retries": 0,
            "planned_starts": 24,
            "mini_batch_max_starts": 8,
            "mini_batch_max_minutes": 60,
        },
        "case_matrix": [
            {"case_id": s["case_id"], "task_id": s["task_id"], "split": s["split"],
             "partition": s["partition"], "design": s["design"], "mach": s["mach"],
             "sref_m2": s["sref"], "q_pa": s["q_pa"], "cl_target": s["cl_target"],
             "alpha_center_deg": s["alpha_center"], "alpha_points": len(s["alphas"]),
             "alpha_step_deg": 0.03, "alpha_min_deg": min(s["alphas"]),
             "alpha_max_deg": max(s["alphas"]),
             "x12": s["x12"]} for s in specs
        ],
        "label_acceptance": {
            "denominator": "successful solver starts with a case_result and polar",
            "target_valid_label_rate": 0.70,
            "lift_tolerance_rel": 1e-3,
            "admission": "RealAdmissionManifest + independent local audit per case; only LIFT_MATCHED rows admitted",
            "failed_cases": "objective=null, no rerun inside G1",
        },
        "stop_conditions": [
            "any start refused by accounting/window/plan validation",
            "any solver timeout or missing process result",
            "two consecutive non-SOLVED cases",
            "accounting ledger not conserved after a mini-batch",
            "any raw file hash mismatch or upload/readback mismatch",
        ],
        "upload": {
            "repository_dir": "research/concorde_metaopt/optimization_runs/DRECOVER001-G1-20261121-01",
            "raw_cases": "raw_cases/<case_id>/",
            "required_tables": ["all_evaluations.csv", "admitted_labels.csv", "failed_or_null.csv", "attempt_ledger.csv"],
            "raw_extensions": [".vspgeom", ".vspaero", ".polar", ".history", ".lod", ".adb", ".vsp3"],
            "after_each_mini_batch": "upload raw+logs+accounting, then read back SHA256SUMS from remote before next mini-batch",
        },
        "a5_requirement": "independent deepseek-flash read-only review of this preregistration and exact case plan SHA256 manifest before first start",
        "physical_solver_starts_actual": 0,
        "status": "PRE_REGISTERED_PENDING_A5_AND_GO",
    }
    pre_path = RUN_ROOT / "g1_preregistration.json"
    pre_path.write_text(json.dumps(prereg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (RUN_ROOT / "operator_authorization.json").write_text(json.dumps({
        "schema": "dreal003.g1_operator_authorization.v1",
        "authorization_id": AUTH_ID, "run_id": RUN_ID, "batch_id": BATCH_ID,
        "owner_message_ref": OWNER_REF,
        "owner_text": "继续执行，把G1阶段也完成，批准实际物理计算",
        "authorized": True, "planned_starts": 24,
        "window": {"start_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "end_utc": WINDOW_END, "token": AUTH_ID + "-WINDOW"},
        "constraints": ["parallel 1", "no retry", "<=8 starts per mini-batch",
                        "upload and remote readback before next mini-batch",
                        "failed case objective=null and no rerun",
                        "A5 pre-review of exact case manifest required before first start"],
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not args.build:
        print(json.dumps({"prereg": str(pre_path), "cases": len(specs),
                          "sha256": sha(pre_path)}, indent=2))
        return 0
    manifest_cases = []
    for s in specs:
        case_dir = CASE_ROOT / s["case_id"]
        if case_dir.exists() and any(case_dir.iterdir()):
            raise SystemExit("case dir already populated: " + str(case_dir))
        case_dir.mkdir(parents=True, exist_ok=True)
        geometry = build_geometry(NAMES, s["values"])
        flow = {"vinf_m_s": s["vinf"], "rho_kg_m3": BASE_RHO, "recref": s["recref"]}
        record = openvsp_model.prepare_case(
            geometry, case_dir, s["basename"], geometry_set="thin",
            alphas_deg=s["alphas"], tess_u=12, tess_w=25, n_wake_nodes=8,
            mach_values=[s["mach"]], flow_conditions=flow,
        )
        exe = Path(r"D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe")
        vspgeom = case_dir / (s["basename"] + ".vspgeom")
        vkey = case_dir / (s["basename"] + ".vkey")
        vspaero = case_dir / (s["basename"] + ".vspaero")
        argv = [str(exe), "-omp", "1", s["basename"]]
        design_id = canon(s["x12"])
        plan = {
          "schema": "dreal001.solver_plan.v1",
          "run_id": RUN_ID, "batch_id": BATCH_ID,
          "task_id": s["task_id"], "case_id": s["case_id"],
          "purpose": "D-REAL-EXP-001 G1 real label generation; %s %s %s" % (s["task_id"], s["design"], s["partition"]),
          "solver": {"path": str(exe), "sha256": sha(exe), "cwd": str(case_dir),
                     "version_banner": openvsp_model.EXPECTED_VSPAERO_VERSION,
                     "omp_threads": 1, "timeout_s": 1200,
                     "solver_config_hash": sha(vspaero)},
          "command": {"argv": argv},
          "geometry": {"files": {
               "vspgeom": {"path": str(vspgeom), "sha256": sha(vspgeom)},
               "vkey": {"path": str(vkey), "sha256": sha(vkey)},
               "vspaero": {"path": str(vspaero), "sha256": sha(vspaero)}},
             "sref_m2": s["sref"], "geometry_sha256": sha(vspgeom),
             "design_hash": design_id},
          "design": {"design_hash": design_id, "x12": s["x12"]},
          "budget": {"physical_solver_starts_max": 1,
                      "expected_internal_cases": len(s["alphas"]),
                      "max_internal_cases": 32},
        }
        plan_bytes = json.dumps(plan, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        (case_dir / "plan.json").write_bytes(plan_bytes)
        now = datetime.now(timezone.utc)
        approval = {
          "schema": "dreal001.solver_approval.v1",
          "approved": True,
          "authorization_id": AUTH_ID,
          "owner_message_ref": OWNER_REF,
          "run_id": RUN_ID, "batch_id": BATCH_ID, "case_id": s["case_id"],
          "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
          "max_starts": 1,
          "window": {"start_utc": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "end_utc": WINDOW_END,
                      "token": AUTH_ID + "-WINDOW"},
          "window_token": AUTH_ID + "-WINDOW",
        }
        (case_dir / "approval.json").write_text(
            json.dumps(approval, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        task = TaskSpec(task_id=s["task_id"], split=s["split"], mach=s["mach"],
                        altitude_m=ALT_M, dynamic_pressure_pa=s["q_pa"],
                        lift_target_n=LIFT_N, geometry_contract_sha256=GEOMETRY_CONTRACT,
                        lift_tolerance_rel=1e-3)
        spec = {
          "schema": "dreal001.r2_task_spec.v1",
          "task_id": s["task_id"], "split": s["split"], "partition": s["partition"],
          "case_id": s["case_id"], "design": s["design"], "design_id": design_id,
          "x12": s["x12"], "mach": s["mach"], "altitude_m": ALT_M,
          "dynamic_pressure_pa": s["q_pa"], "lift_target_n": LIFT_N,
          "geometry_contract_sha256": GEOMETRY_CONTRACT, "lift_tolerance_rel": 1e-3,
          "flow_conditions": flow, "alpha_center_deg": s["alpha_center"],
          "alpha_grid_deg": s["alphas"], "cl_target": s["cl_target"], "sref_m2": s["sref"],
          "task_physics_sha256": task.physics_sha256,
        }
        (case_dir / "task_spec.json").write_text(
            json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest_cases.append({
            "case_id": s["case_id"], "task_id": s["task_id"], "split": s["split"],
            "partition": s["partition"], "design": s["design"], "mach": s["mach"],
            "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "approval_sha256": sha(case_dir / "approval.json"),
            "task_spec_sha256": sha(case_dir / "task_spec.json"),
            "vspgeom_sha256": sha(vspgeom), "vspaero_sha256": sha(vspaero),
            "vkey_sha256": sha(vkey), "case_inputs_sha256": sha(case_dir / "case_inputs.json"),
            "audit_sha256": None, "alpha_grid_deg": s["alphas"],
        })
        print("BUILT", s["case_id"], "sref", s["sref"], "q", s["q_pa"], "alpha", round(s["alpha_center"],6), flush=True)
    manifest = {"schema": "dreal003.g1_case_manifest.v1",
                "run_id": RUN_ID, "batch_id": BATCH_ID, "authorization_id": AUTH_ID,
                "case_count": len(manifest_cases), "cases": manifest_cases,
                "preregistration_sha256": sha(pre_path)}
    mp = RUN_ROOT / "g1_case_manifest.json"
    mp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"case_manifest": str(mp), "case_count": len(manifest_cases), "sha256": sha(mp)}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
