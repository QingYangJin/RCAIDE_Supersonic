"""O1 evaluator: the same two-start real VSPAERO recipe as O0, parameterised by task.

O1 compares three warm-start arms on ONE new task (Mach 1.90 for the first pairing).
Nothing here is allowed to differ between arms except which three extra initialisation
designs the arm proposes: the coarse bracket, the refine window, the lift tolerance,
the audit and the admission gate are byte-identical code for every arm and the shared
support designs.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
sys.path.insert(0, str(REPO))

from research.concorde_metaopt.aircraft.geometry_model import build_geometry  # noqa: E402
from research.concorde_metaopt.dreal001.geometry import openvsp_model  # noqa: E402
from research.concorde_metaopt.dreal001.geometry import solver_runner  # noqa: E402
from research.concorde_metaopt.dreal001.meta.task_spec import TaskSpec  # noqa: E402
from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0  # noqa: E402

RUN_ID = "DRECOVER001-O1-20261124-01"
AUTH_ID = "AUTH-DREAL005-O1-20261124-01"
OWNER_REF = ("Issue #15 (2026-11-24) section 6 + acceptance comment 7122663062 "
             "+ Owner m16075 one-shot budget approval")
WINDOW_END = "2026-11-26T00:00:00Z"
GEOM = "08c1341bdab944dd2a6e20985553e8eafc1d35ce50105a022c0a816da018f35b"
LIFT = 1333704.4
ALT = 18288.0
BASE_MACH = 2.02
BASE_VINF = 596.0373972278921
BASE_RHO = 0.1153178340089936
BASE_RECREF = 89397005.8767656
EXE = Path(r"D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe")
AUDIT_SCRIPT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py")
ADMIT_SCRIPT = RUN / "scripts" / "o1_admit_case.py"

# Mach 1.90 is the first-pairing candidate named in Issue #15 section 6. Mach 2.10 is
# registered here so the physics hash can be checked, but the first pairing spends on
# 1.90 only (the contract asks for one new task, seed 7, in the first pairing).
TASK_REGISTRY = {
    "O1-M190": {"task_id": "O1-M190", "mach": 1.90, "split": "train"},
    "O1-M210": {"task_id": "O1-M210", "mach": 2.10, "split": "train"},
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canon(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def task_def(task_key: str) -> Dict[str, Any]:
    if task_key not in TASK_REGISTRY:
        raise KeyError("unknown O1 task %r" % (task_key,))
    return dict(TASK_REGISTRY[task_key])


def flow_for(mach: float) -> Dict[str, float]:
    vinf = mach * (BASE_VINF / BASE_MACH)
    recref = BASE_RECREF * (vinf / BASE_VINF)
    q = 0.5 * BASE_RHO * vinf * vinf
    return {"vinf_m_s": vinf, "rho_kg_m3": BASE_RHO, "recref": recref, "q_pa": q}


def task_spec(task_key: str, split: str = "") -> TaskSpec:
    spec = task_def(task_key)
    mach = float(spec["mach"])
    return TaskSpec(task_id=spec["task_id"], split=(split or spec["split"]), mach=mach,
                    altitude_m=ALT, dynamic_pressure_pa=flow_for(mach)["q_pa"],
                    lift_target_n=LIFT, geometry_contract_sha256=GEOM,
                    lift_tolerance_rel=1e-3)


def case_dir_for(task_key: str, group: str, case_id: str) -> Path:
    return RUN / "cases" / task_key / group / case_id


def cl_target_for(task_key: str, x12: List[float]) -> float:
    spec = task_def(task_key)
    flow = flow_for(float(spec["mach"]))
    geom = build_geometry(list(o0.PHYSICAL_15_NAMES), o0.physical_15(x12))
    return LIFT / (flow["q_pa"] * float(geom.wing.area_m2))


def make_case(task_key: str, group: str, x12: List[float], tag: str, stage: str,
              alphas: List[float], cl_target: float, alpha_center: float,
              n_wake_nodes: int = 8, partition: str = "query") -> Dict[str, Any]:
    """Write one solver case (plan/approval/task_spec) for the given alpha grid.

    The partition is written into the task spec honestly: the three shared support designs are
    support rows, every other design is a query row. The certificate copies whatever the spec
    says, so a support design that claimed to be a query row would be a mislabelled record.
    """
    spec = task_def(task_key)
    mach = float(spec["mach"])
    case_id = "o1-%s-%s" % (tag, stage)
    case_dir = case_dir_for(task_key, group, case_id)
    if case_dir.exists():
        real = sorted(p.name for p in case_dir.glob("*.polar"))
        if real:
            raise SystemExit("refusing to overwrite paid solver output in %s (%s); "
                             "use a fresh group/tag" % (case_dir, ", ".join(real)))
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    vals = o0.physical_15(x12)
    geom = build_geometry(list(o0.PHYSICAL_15_NAMES), vals)
    sref = float(geom.wing.area_m2)
    flow = flow_for(mach)
    openvsp_model.prepare_case(geom, case_dir, case_id, geometry_set="thin",
                               alphas_deg=alphas, tess_u=12, tess_w=25,
                               n_wake_nodes=n_wake_nodes, mach_values=[mach],
                               flow_conditions={"vinf_m_s": flow["vinf_m_s"],
                                                "rho_kg_m3": flow["rho_kg_m3"],
                                                "recref": flow["recref"]})
    vspgeom = case_dir / (case_id + ".vspgeom")
    vkey = case_dir / (case_id + ".vkey")
    vspaero = case_dir / (case_id + ".vspaero")
    design_id = o0.design_identity(x12)["design_id"]
    plan = {
        "schema": "dreal001.solver_plan.v1", "run_id": RUN_ID,
        "batch_id": "%s-%s" % (RUN_ID, group), "task_id": spec["task_id"],
        "case_id": case_id,
        "purpose": "D-REAL-EXP-003 O1 three-arm warm start, task %s, group %s, %s stage"
                   % (spec["task_id"], group, stage),
        "solver": {"path": str(EXE), "sha256": sha(EXE), "cwd": str(case_dir),
                   "version_banner": openvsp_model.EXPECTED_VSPAERO_VERSION,
                   "omp_threads": 1, "timeout_s": 600,
                   "solver_config_hash": sha(vspaero)},
        "command": {"argv": [str(EXE), "-omp", "1", case_id]},
        "geometry": {"files": {"vspgeom": {"path": str(vspgeom), "sha256": sha(vspgeom)},
                               "vkey": {"path": str(vkey), "sha256": sha(vkey)},
                               "vspaero": {"path": str(vspaero), "sha256": sha(vspaero)}},
                     "sref_m2": sref, "geometry_sha256": sha(vspgeom),
                     "design_hash": design_id},
        "design": {"design_hash": design_id, "x12": list(x12)},
        "budget": {"physical_solver_starts_max": 1,
                   "expected_internal_cases": len(alphas),
                   "max_internal_cases": 64},
    }
    payload = json.dumps(plan, indent=2, ensure_ascii=False).encode() + b"\n"
    (case_dir / "plan.json").write_bytes(payload)
    stamp = datetime.now(timezone.utc)
    approval = {
        "schema": "dreal001.solver_approval.v1", "approved": True,
        "authorization_id": AUTH_ID, "owner_message_ref": OWNER_REF,
        "run_id": RUN_ID, "batch_id": "%s-%s" % (RUN_ID, group), "case_id": case_id,
        "plan_sha256": hashlib.sha256(payload).hexdigest(), "max_starts": 1,
        "window": {"start_utc": (stamp - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "end_utc": WINDOW_END, "token": AUTH_ID + "-WINDOW"},
        "window_token": AUTH_ID + "-WINDOW",
    }
    (case_dir / "approval.json").write_text(
        json.dumps(approval, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    task = task_spec(task_key)
    tspec = {
        "schema": "dreal001.r2_task_spec.v1", "task_id": spec["task_id"],
        "split": spec["split"], "partition": partition, "case_id": case_id,
        "design": tag, "group": group,
        "design_id": design_id, "x12": list(x12),
        "mach": mach, "altitude_m": ALT, "dynamic_pressure_pa": flow["q_pa"],
        "lift_target_n": LIFT, "geometry_contract_sha256": GEOM,
        "lift_tolerance_rel": 1e-3,
        "flow_conditions": {"vinf_m_s": flow["vinf_m_s"],
                            "rho_kg_m3": flow["rho_kg_m3"],
                            "recref": flow["recref"]},
        "alpha_center_deg": alpha_center, "alpha_grid_deg": list(alphas),
        "cl_target": cl_target, "sref_m2": sref,
        "task_physics_sha256": task.physics_sha256, "stage": stage,
    }
    (case_dir / "task_spec.json").write_text(
        json.dumps(tspec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"case_id": case_id, "case_dir": str(case_dir), "sref_m2": sref,
            "q_pa": flow["q_pa"], "cl_target": cl_target,
            "alpha_points": len(alphas), "x12": list(x12), "stage": stage,
            "n_wake_nodes": int(n_wake_nodes),
            "task_physics_sha256": task.physics_sha256,
            "plan_sha256": hashlib.sha256(payload).hexdigest(),
            "vspgeom_sha256": sha(vspgeom)}


def run(case: Dict[str, Any], attempt_id: str, dry_run: bool = False) -> Dict[str, Any]:
    case_dir = Path(case["case_dir"])
    return solver_runner.run_case(case_dir / "plan.json", case_dir / "approval.json",
                                  attempt_id, dry_run=dry_run,
                                  timeout_s=o0.CAPS["solver_timeout_s"])


def bracket_rows(result: Dict[str, Any]) -> List[List[float]]:
    payload = result.get("case_result")
    if isinstance(payload, (str, Path)):
        payload = json.loads(Path(payload).read_text(encoding="utf-8"))
    rows = ((payload or {}).get("evaluation") or {}).get("rows") or []
    out = []
    for row in rows:
        if row.get("valid") is False:
            continue
        if "alpha_deg" not in row or "CLtot" not in row:
            continue
        out.append([float(row["alpha_deg"]), float(row["CLtot"])])
    return out


def audit_case(case_id: str, group: str, task_key: str, audit_id: str,
               verdict: str = "ADMIT_REAL_LABEL") -> Dict[str, Any]:
    case_dir = case_dir_for(task_key, group, case_id)
    argv = [sys.executable, str(AUDIT_SCRIPT), "--case-dir", str(case_dir),
            "--audit-id", audit_id, "--reviewer", "o1-lead-audit",
            "--reviewer-role", "SEPARATE_LOCAL_REIMPLEMENTATION",
            "--created-utc", now(), "--verdict", verdict,
            "--geometry-contract", GEOM, "--lift-target", str(LIFT),
            "--lift-tolerance", "0.001"]
    proc = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True)
    audit_path = case_dir / "audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else None
    return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:], "audit_id": audit_id,
            "audit_path": str(audit_path),
            "audit_sha256": sha(audit_path) if audit_path.exists() else None,
            "audit": audit}


def admit_case(case_id: str, group: str, task_key: str, admission_id: str,
               audit_id: str, tag: str, partition: str = "query",
               split: str = "train") -> Dict[str, Any]:
    case_dir = case_dir_for(task_key, group, case_id)
    argv = [sys.executable, str(ADMIT_SCRIPT), "--case-dir", str(case_dir),
            "--admission-id", admission_id, "--audit-ref", audit_id,
            "--evaluator-id", "vspaero-3.55.0-v7.2.2-omp1",
            "--solver-started-utc", now(), "--partition", partition,
            "--split", split, "--performance-tag", tag]
    proc = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True)
    cert_path = case_dir / "admission_certificate.json"
    cert = json.loads(cert_path.read_text(encoding="utf-8")) if cert_path.exists() else None
    return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:], "admission_id": admission_id,
            "certificate_path": str(cert_path),
            "certificate_sha256": sha(cert_path) if cert_path.exists() else None,
            "certificate": cert}
