"""O0 case construction and the real (injected) evaluator for D-REAL-EXP-003.

One design evaluation costs two charged VSPAERO starts:

  1. a 7-point coarse bracket around the frozen fixed-lift alpha guess;
  2. a 13-point refinement centred on the coarse quadratic prediction.

The second case is the one that is audited and admitted: admission only accepts an
actual raw polar row inside the 1e-3 lift tolerance, never an interpolated value.
Nothing in this module decides to spend a start; the O0 loop calls evaluate().
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
AUDIT_ROOT = RUN / "audits"

# Every batch writes into its own case directory. The first batch (B01) already paid for a
# real case that must survive any later attempt, so a new batch may never overwrite it: the
# label is part of the path, and make_case refuses to delete a directory that holds real
# solver output.
_LABEL = "B02"


def set_label(label: str) -> str:
    """Bind this process to one batch label; all case paths follow it."""
    global _LABEL
    label = str(label).strip()
    if not label or "/" in label or "\\" in label or label in (".", ".."):
        raise ValueError("invalid batch label %r" % (label,))
    _LABEL = label
    return _LABEL


def label() -> str:
    return _LABEL


def batch_id() -> str:
    return "DRECOVER001-O0-20261124-01-%s" % _LABEL


def case_root() -> Path:
    return RUN / "cases" / _LABEL
sys.path.insert(0, str(REPO))

from research.concorde_metaopt.aircraft.geometry_model import build_geometry  # noqa: E402
from research.concorde_metaopt.dreal001.geometry import openvsp_model  # noqa: E402
from research.concorde_metaopt.dreal001.geometry import solver_runner  # noqa: E402
from research.concorde_metaopt.dreal001.geometry.task_spec import TASK_SPEC  # noqa: E402
from research.concorde_metaopt.dreal001.meta.task_spec import TaskSpec  # noqa: E402
from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0  # noqa: E402

RUN_ID = "DRECOVER001-O0-20261124-01"
AUTH_ID = "AUTH-DREAL005-O0-20261124-01"
BATCH_ID_B01 = "DRECOVER001-O0-20261124-01-B01"  # the aborted first batch, kept for reference
OWNER_REF = "Issue #15 (2026-11-24) + comment 1 + Owner m11649"
WINDOW_END = "2026-11-26T00:00:00Z"
GEOM = "08c1341bdab944dd2a6e20985553e8eafc1d35ce50105a022c0a816da018f35b"
LIFT = 1333704.4
ALT = 18288.0
MACH = 2.02
BASE_MACH = 2.02
BASE_VINF = 596.0373972278921
BASE_RHO = 0.1153178340089936
BASE_RECREF = 89397005.8767656
EXE = Path(r"D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe")
AUDIT_SCRIPT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py")
ADMIT_SCRIPT = RUN / "scripts" / "o0_admit_case.py"


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


def flow_for(mach: float = MACH) -> Dict[str, float]:
    vinf = mach * (BASE_VINF / BASE_MACH)
    recref = BASE_RECREF * (vinf / BASE_VINF)
    q = 0.5 * BASE_RHO * vinf * vinf
    return {"vinf_m_s": vinf, "rho_kg_m3": BASE_RHO, "recref": recref, "q_pa": q}


def task_spec() -> TaskSpec:
    return TaskSpec(task_id="O0-M202", split="train", mach=MACH, altitude_m=ALT,
                    dynamic_pressure_pa=flow_for()["q_pa"], lift_target_n=LIFT,
                    geometry_contract_sha256=GEOM, lift_tolerance_rel=1e-3)


def make_case(x12: List[float], tag: str, stage: str, alphas: List[float],
              cl_target: float, alpha_center: float,
              n_wake_nodes: int = 8) -> Dict[str, Any]:
    """Write one solver case (plan/approval/task_spec) for the given alpha grid."""
    case_id = "o0-%s-%s" % (tag, stage)
    case_dir = case_root() / case_id
    if case_dir.exists():
        # A directory that already holds real solver output is evidence, not scratch space:
        # B01's paid case must survive the corrected batch instead of being overwritten.
        real = sorted(p.name for p in case_dir.glob("*.polar"))
        if real:
            raise SystemExit("refusing to overwrite paid solver output in %s (%s); "
                             "use a fresh batch label" % (case_dir, ", ".join(real)))
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    vals = o0.physical_15(x12)
    geom = build_geometry(list(o0.PHYSICAL_15_NAMES), vals)
    sref = float(geom.wing.area_m2)
    flow = flow_for()
    openvsp_model.prepare_case(geom, case_dir, case_id, geometry_set="thin",
                               alphas_deg=alphas, tess_u=12, tess_w=25,
                               n_wake_nodes=n_wake_nodes, mach_values=[MACH],
                               flow_conditions={"vinf_m_s": flow["vinf_m_s"],
                                                "rho_kg_m3": flow["rho_kg_m3"],
                                                "recref": flow["recref"]})
    vspgeom = case_dir / (case_id + ".vspgeom")
    vkey = case_dir / (case_id + ".vkey")
    vspaero = case_dir / (case_id + ".vspaero")
    design_id = o0.design_identity(x12)["design_id"]
    plan = {
        "schema": "dreal001.solver_plan.v1", "run_id": RUN_ID, "batch_id": batch_id(),
        "task_id": "O0-M202", "case_id": case_id,
        "purpose": "D-REAL-EXP-003 O0 fixed-Mach real BO %s stage for design %s"
                   % (stage, tag),
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
        "run_id": RUN_ID, "batch_id": batch_id(), "case_id": case_id,
        "plan_sha256": hashlib.sha256(payload).hexdigest(), "max_starts": 1,
        "window": {"start_utc": (stamp - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "end_utc": WINDOW_END, "token": AUTH_ID + "-WINDOW"},
        "window_token": AUTH_ID + "-WINDOW",
    }
    (case_dir / "approval.json").write_text(
        json.dumps(approval, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    task = task_spec()
    spec = {
        "schema": "dreal001.r2_task_spec.v1", "task_id": "O0-M202", "split": "train",
        "partition": "query", "case_id": case_id, "design": tag,
        "design_id": design_id, "x12": list(x12),
        "mach": MACH, "altitude_m": ALT, "dynamic_pressure_pa": flow["q_pa"],
        "lift_target_n": LIFT, "geometry_contract_sha256": GEOM,
        "lift_tolerance_rel": 1e-3,
        "flow_conditions": {"vinf_m_s": flow["vinf_m_s"],
                            "rho_kg_m3": flow["rho_kg_m3"],
                            "recref": flow["recref"]},
        "alpha_center_deg": alpha_center, "alpha_grid_deg": alphas,
        "cl_target": cl_target, "sref_m2": sref,
        "task_physics_sha256": task.physics_sha256, "stage": stage,
    }
    (case_dir / "task_spec.json").write_text(
        json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
    """Read the alpha/CL bracket pairs from one solver result.

    solver_runner.run_case() reports the case result as a path to case_result.json,
    not as an inline object, so this has to load the file before indexing it.
    Feeding the path straight into .get() is what aborted the first O0-B01 attempt.
    """
    payload = result.get("case_result")
    if isinstance(payload, (str, Path)):
        payload = json.loads(Path(payload).read_text(encoding="utf-8"))
    rows = ((payload or {}).get("evaluation") or {}).get("rows") or []
    out = []
    for row in rows:
        alpha = row.get("alpha_deg")
        cl = row.get("CLtot")
        if alpha is None or cl is None:
            continue
        if row.get("valid") is False:
            continue
        out.append([float(alpha), float(cl)])
    return out


def audit_case(case_id: str, audit_id: str, verdict: str = "ADMIT_REAL_LABEL") -> Dict[str, Any]:
    case_dir = case_root() / case_id
    cmd = [sys.executable, str(AUDIT_SCRIPT), "--case-dir", str(case_dir),
           "--audit-id", audit_id, "--reviewer", "o0-lead-audit",
           "--reviewer-role", "SEPARATE_LOCAL_REIMPLEMENTATION",
           "--created-utc", now(), "--verdict", verdict,
           "--geometry-contract", GEOM, "--lift-target", str(LIFT),
           "--lift-tolerance", "0.001"]
    done = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    record = {"returncode": done.returncode, "stdout": done.stdout[-4000:],
              "stderr": done.stderr[-4000:], "audit_id": audit_id}
    path = case_dir / "audit.json"
    if path.exists():
        record["audit_path"] = str(path)
        record["audit_sha256"] = sha(path)
        record["audit"] = json.loads(path.read_text(encoding="utf-8"))
    return record


def admit_case(case_id: str, admission_id: str, audit_id: str, tag: str,
               split: str = "train") -> Dict[str, Any]:
    case_dir = case_root() / case_id
    cmd = [sys.executable, str(ADMIT_SCRIPT), "--case-dir", str(case_dir),
           "--admission-id", admission_id, "--audit-ref", audit_id,
           "--evaluator-id", "vspaero-3.55.0-v7.2.2-omp1",
           "--solver-started-utc", now(), "--partition", "query",
           "--split", split, "--performance-tag", tag]
    done = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    record = {"returncode": done.returncode, "stdout": done.stdout[-4000:],
              "stderr": done.stderr[-4000:], "admission_id": admission_id}
    path = case_dir / "admission_certificate.json"
    if path.exists():
        record["certificate_path"] = str(path)
        record["certificate_sha256"] = sha(path)
        record["certificate"] = json.loads(path.read_text(encoding="utf-8"))
    return record

# ---------------------------------------------------------------------------
# The evaluated pipeline: two charged starts per design, then audit + admit.
# ---------------------------------------------------------------------------
def design_tag(attempt) -> str:
    """Stable per-design tag used in case ids and case directories."""
    return "d%02d" % int(attempt.design_index)


def cl_target_for(x12) -> float:
    geom = build_geometry(list(o0.PHYSICAL_15_NAMES), o0.physical_15(x12))
    return LIFT / (flow_for()["q_pa"] * float(geom.wing.area_m2))


def evaluate_design(attempt):
    """Run the real ask -> geometry -> VSPAERO -> audit -> admit for one design.

    Two starts are always attempted once the coarse bracket succeeds; both are
    charged even when the design ends up infeasible, and no tolerance is relaxed.
    Returns the same AttemptRecord with terminals filled in.
    """
    tag = design_tag(attempt)
    cl_target = cl_target_for(attempt.x12)
    attempt.starts = 0
    attempt.internal = 0
    attempt.case_ids = []

    # -- start 1: coarse bracket -------------------------------------------
    coarse = o0.coarse_alphas()
    case = make_case(attempt.x12, tag, "coarse", coarse, cl_target,
                     o0.COARSE_ALPHA_GUESS_DEG)
    attempt.case_ids.append(case["case_id"])
    attempt.sref_m2 = case["sref_m2"]
    attempt.q_pa = case["q_pa"]
    result = run(case, "%s-coarse" % tag)
    attempt.starts += int(result.get("physical_solver_starts") or 0)
    attempt.internal += int(result.get("internal_solver_cases") or 0)
    if result.get("status") != "SOLVED":
        attempt.status = "COARSE_%s" % (result.get("status") or "UNKNOWN")
        attempt.feasible = False
        attempt.objective = None
        attempt.failure_kind = "SOLVER_NO_RESULT"
        attempt.detail = "coarse start did not solve: %s" % (
            result.get("refusal_reason") or result.get("status"))
        attempt.coarse = {"case_id": case["case_id"], "status": result.get("status"),
                          "starts": attempt.starts, "internal": attempt.internal}
        return attempt
    rows = bracket_rows(result)
    prediction = o0.predict_alpha(rows, cl_target)
    attempt.coarse = {"case_id": case["case_id"], "status": result.get("status"),
                      "rows": rows, "prediction": prediction,
                      "starts": attempt.starts, "internal": attempt.internal}
    if not prediction.get("ok"):
        attempt.status = "COARSE_BRACKET_NOT_USABLE"
        attempt.feasible = False
        attempt.objective = None
        attempt.failure_kind = "ALPHA_BRACKET"
        attempt.detail = str(prediction.get("reason"))
        return attempt

    # -- start 2: refinement ------------------------------------------------
    center = float(prediction["predicted_alpha_deg"])
    refine = o0.refine_alphas(center)
    case2 = make_case(attempt.x12, tag, "refine", refine, cl_target, center)
    attempt.case_ids.append(case2["case_id"])
    result2 = run(case2, "%s-refine" % tag)
    attempt.starts += int(result2.get("physical_solver_starts") or 0)
    attempt.internal += int(result2.get("internal_solver_cases") or 0)
    if result2.get("status") != "SOLVED":
        attempt.status = "REFINE_%s" % (result2.get("status") or "UNKNOWN")
        attempt.feasible = False
        attempt.objective = None
        attempt.failure_kind = "SOLVER_NO_RESULT"
        attempt.detail = "refine start did not solve: %s" % (
            result2.get("refusal_reason") or result2.get("status"))
        attempt.refine = {"case_id": case2["case_id"], "status": result2.get("status"),
                          "starts": attempt.starts, "internal": attempt.internal}
        return attempt

    # -- strict raw-row audit, then admission ------------------------------
    audit_id = "O0-AUDIT-%s" % case2["case_id"]
    audit = audit_case(case2["case_id"], audit_id)
    attempt.audit_id = audit_id
    attempt.refine = {"case_id": case2["case_id"], "status": result2.get("status"),
                      "alphas": refine, "predicted_alpha_deg": center,
                      "audit_returncode": audit.get("returncode"),
                      "starts": attempt.starts, "internal": attempt.internal}
    if audit.get("returncode") != 0:
        attempt.status = "AUDIT_FAILED"
        attempt.feasible = False
        attempt.objective = None
        attempt.failure_kind = "NO_RAW_ROW_IN_LIFT_TOLERANCE"
        attempt.detail = ("audit refused: %s"
                          % (audit.get("stderr") or "")).strip()[-300:]
        return attempt
    admission_id = "O0-ADM-%s" % case2["case_id"]
    admission = admit_case(case2["case_id"], admission_id, audit_id, tag)
    attempt.admission_id = admission_id
    attempt.refine["admission_returncode"] = admission.get("returncode")
    if admission.get("returncode") != 0:
        attempt.status = "ADMISSION_FAILED"
        attempt.feasible = False
        attempt.objective = None
        attempt.failure_kind = "ADMISSION_CONTRACT"
        attempt.detail = ("admission refused: %s"
                          % (admission.get("stderr") or "")).strip()[-300:]
        return attempt
    cert = admission["certificate"]
    attempt.status = "FEASIBLE_ADMITTED"
    attempt.feasible = True
    attempt.di_n = float(cert["di_n"])
    attempt.objective = attempt.di_n
    attempt.cl = float(cert["cl"])
    attempt.cdi = float(cert["cdi"])
    attempt.alpha_deg = float(cert["alpha_deg"])
    attempt.sref_m2 = float(cert["sref_m2"])
    attempt.q_pa = float(cert["q_pa"])
    attempt.lift_rel_error = abs(float(cert["q_pa"]) * float(cert["sref_m2"])
                                 * float(cert["cl"]) - LIFT) / LIFT
    attempt.detail = "raw row admitted at %.6f deg" % attempt.alpha_deg
    return attempt


def evaluate_design_logged(attempt, log_path):
    """evaluate_design plus an append-only JSONL trace of every attempt."""
    done = evaluate_design(attempt)
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"utc": now(), "attempt": done.as_dict()},
                                ensure_ascii=False) + "\n")
    return done
