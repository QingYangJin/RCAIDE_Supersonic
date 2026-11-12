"""P1 batch driver: 25 approved VSPAERO starts, sequential, fail-closed (D-REAL-001 A1).

This module is the ready-to-run executor for the P1 case matrix.  It NEVER starts a
solver by itself: every real start requires

  * plan.json (dreal001.solver_plan.v1, frozen byte hash reported to the Lead), and
  * approval.json written by the Lead (approved=true, plan_sha256, window token + window),

and it refuses to write a single ledger line when either is missing, unapproved, for a
different plan digest, or outside the approved window.  --dry-run performs the same
validation and prints the plan without creating run directories, ledger lines or processes.

Contract of a batch run (governance section 12.10, Lead instruction 2026-11-10):

  * one case per directory "<run>/cases/<case_id>/" with its own four-piece inputs,
    copies of the derived case plan/approval, logs and case_result.json;
  * one run-level append-only ledger "<run>/solver_attempts.jsonl": the start line is
    appended BEFORE the process is spawned, the end line after it settles; a timeout or
    a failed process still consumes exactly one physical start;
  * attempt_id is mandatory and unique (no silent retries); at most one infrastructure
    retry per case (exit code/timeout/unparsed polar), each retry a separate billed start;
  * "<run>/evaluations.jsonl" has exactly one line per (Mach, alpha, Beta) flow condition:
    line-level physical_solver_starts=0, attempt_physical_solver_starts=1;
  * the window is re-checked before every start, and any stop condition writes
    stop_report.json with status STOPPED_FAIL_CLOSED and no further starts;
  * fuel_burn_kg is always null and the evidence tier is SOLVER_LOOP_VERIFIED only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    from research.concorde_metaopt.dreal001.geometry import (design_identity, evidence_manifest,
                                                             ledger, solver_runner)
    from research.concorde_metaopt.dreal001.geometry.task_spec import DEFAULT_GEOMETRY_SET, TASK_SPEC
else:
    from . import design_identity, evidence_manifest, ledger, solver_runner
    from .task_spec import DEFAULT_GEOMETRY_SET, TASK_SPEC

BATCH_PLAN_SCHEMA = "dreal001.solver_plan.v1"
CASE_PLAN_SCHEMA = "dreal001.solver_case_plan.v1"
CASE_APPROVAL_SCHEMA = "dreal001.solver_case_approval.v1"
CASE_RESULT_SCHEMA = "dreal001.solver_case_result.v1"
BATCH_RUN_SCHEMA = "dreal001.p1_batch_run.v1"
STOP_REPORT_SCHEMA = "dreal001.stop_report.v1"
DEFAULT_INFRA_RETRIES = 1
# Lead m05126 / A5 m05112: a TIMEOUT is never auto-retried (it fails closed to S1).
# Other infrastructure failures keep at most one automatic retry, and a plan may set
# retry_policy.infra_retries_allowed = 0 to forbid that retry as well.
INPUT_PIECES = ("vspgeom", "vkey", "vspaero", "csf")
SUFFIX = {"vspgeom": ".vspgeom", "vkey": ".vkey", "vspaero": ".vspaero", "csf": ".csf"}
SOLVED = "SOLVED"
INFRA_FAILURES = ("MISSING_OR_UNPARSED_POLAR", "SOLVER_EXIT_")
NON_RETRYABLE_FAILURES = ("TIMEOUT",)
REPEATABILITY_CASES = ("P1-00a", "P1-00b", "P1-00c")
THICK_CASES = ("P1-04", "P1-04b", "P1-04c")
THIN_DENSITY_CASES = ("P1-02a", "P1-02c", "P1-02b")


class BatchRefusal(RuntimeError):
    """Raised before any process start when the batch contract is not satisfied."""


def sha256_bytes(payload: bytes) -> str:
    return ledger.sha256_bytes(payload)

def _infra_retries(plan: Dict[str, Any]) -> int:
    """Automatic retries allowed for infrastructure failures in this plan.

    A plan that does not state retry_policy.infra_retries_allowed keeps the historical
    default (at most one); a plan that states 0 forbids retries entirely. TIMEOUT is
    never retried regardless of this value (it stops the batch through S1).
    """
    policy = plan.get("retry_policy") or {}
    value = policy.get("infra_retries_allowed")
    if value is None:
        return DEFAULT_INFRA_RETRIES
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return DEFAULT_INFRA_RETRIES


def _retryable_failure(status: str) -> bool:
    text = str(status or "")
    if text.startswith(NON_RETRYABLE_FAILURES):
        return False
    return text.startswith(INFRA_FAILURES)


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _write_json(path: Path, payload: Dict[str, Any]) -> bytes:
    data = _json_bytes(payload)
    _write_bytes(path, data)
    return data


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_plan(path: Path) -> Tuple[Dict[str, Any], str, bytes]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), sha256_bytes(raw), raw


def load_batch(run_dir: str | Path) -> Dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    plan_path = run_dir / "plan.json"
    if not plan_path.is_file():
        raise BatchRefusal("plan.json missing: %s" % plan_path)
    plan, plan_sha, plan_bytes = _load_plan(plan_path)
    if plan.get("schema") != BATCH_PLAN_SCHEMA:
        raise BatchRefusal("unexpected plan schema %r" % plan.get("schema"))
    cases = plan.get("case_matrix") or []
    if not cases:
        raise BatchRefusal("plan.case_matrix is empty")
    return {"run_dir": run_dir, "plan": plan, "plan_path": plan_path,
            "plan_sha256": plan_sha, "plan_bytes": len(plan_bytes),
            "cases": [dict(case) for case in cases]}


def effective_caps(plan: Dict[str, Any], approval: Dict[str, Any]) -> Dict[str, int]:
    budget = plan.get("budget") or {}
    max_starts = int(budget.get("max_starts", len(plan.get("case_matrix") or [])))
    max_internal = int(budget.get("max_internal_cases", 0))
    if approval.get("max_starts") is not None:
        max_starts = min(max_starts, int(approval["max_starts"]))
    if approval.get("max_internal_cases") is not None:
        max_internal = min(max_internal, int(approval["max_internal_cases"]))
    return {"max_starts": max_starts, "max_internal_cases": max_internal,
            "max_refine_starts": int(budget.get("max_refine_starts", 0))}


def verify_approval(plan: Dict[str, Any], plan_sha256: str,
                    approval: Dict[str, Any], approval_sha256: str) -> Dict[str, Any]:
    """Fail-closed approval gate; returns the verified caps plus the window snapshot."""
    if approval.get("approved") is not True:
        raise BatchRefusal("approval.json is not approved (approved=%r)" % approval.get("approved"))
    token = ledger.approval_window_token(approval)
    if not token:
        raise BatchRefusal("approval.json carries no window_token (top-level or window.token)")
    stated = approval.get("plan_sha256")
    if stated != plan_sha256:
        raise BatchRefusal("approval.plan_sha256 %s != plan bytes sha256 %s" % (stated, plan_sha256))
    if approval.get("run_id") not in (None, plan.get("run_id")):
        raise BatchRefusal("approval.run_id %r != plan.run_id %r"
                           % (approval.get("run_id"), plan.get("run_id")))
    status = ledger.window_status(approval)
    if not status["open"]:
        raise BatchRefusal("approved window is not open: %s" % status["reason"])
    caps = effective_caps(plan, approval)
    if caps["max_starts"] < 1:
        raise BatchRefusal("effective max_starts is 0")
    return {"approval_sha256": approval_sha256, "window": status,
            "window_token": token,
            "window_token_source": status.get("token_source"), **caps}


def _case_dir(run_dir: Path, case_id: str) -> Path:
    return run_dir / "cases" / case_id


def _preflight_dir(run_dir: Path, config_id: str) -> Path:
    return run_dir / "preflight" / config_id


def _copy_case_inputs(case: Dict[str, Any], run_dir: Path, case_dir: Path,
                      basename: str) -> Dict[str, Any]:
    """Retired (A5 a151061 B1 / Lead L-10). Template copying is forbidden for every batch
    after the 2026-11-10 recovery: each real case is rebuilt from its own x12."""
    raise BatchRefusal("template input copying is retired: every case is rebuilt from its x12 "
                       "(A5 B1, Lead L-10); p1_continue must not drive a recovered batch")


def _mesh_target(case: Dict[str, Any]) -> Tuple[int, int]:
    """Target family of a case, frozen in the plan by that configuration's L-09 selection."""
    block = case.get("mesh_identity") or {}
    raw = block.get("target_mesh_family")
    if not raw:
        raise BatchRefusal("case %s has no frozen target_mesh_family in plan.mesh_identity"
                           % case.get("case_id"))
    if isinstance(raw, str):
        parts = raw.lower().split("x")
    else:
        parts = [str(part) for part in raw]
    try:
        nodes, elements = int(parts[0]), int(parts[1])
    except (IndexError, TypeError, ValueError):
        raise BatchRefusal("unparseable target_mesh_family %r for case %s"
                           % (raw, case.get("case_id")))
    return nodes, elements


def _prepare_case_inputs(case: Dict[str, Any], run_dir: Path, case_dir: Path,
                         basename: str) -> Dict[str, Any]:
    """L-10: rebuild THIS design's inputs from its x12 and verify the frozen mesh family.

    The preflight four-piece set is never copied into a real case: every case is
    rebuilt through the canonical geometry path (x12 -> ConcordeGeometry ->
    OpenVSP -> .vspgeom/.vkey/.vspaero/.csf), roundtrip-rebuilt until the family
    selected for this configuration is obtained (<=12 attempts), and FAIL_CLOSED
    before any start if it is not.
    """
    case_id = str(case.get("case_id"))
    x12 = case.get("x12")
    if not x12 or len(x12) != 12:
        raise BatchRefusal("case %s has no complete 12D x12 in the plan; per-design rebuild "
                           "is impossible" % case_id)
    target = _mesh_target(case)
    pre = _read_preflight(run_dir, str(case["preflight_config_id"]))
    if not pre:
        raise BatchRefusal("preflight record missing for %s" % case.get("preflight_config_id"))
    from . import openvsp_model

    geometry, _space = openvsp_model._geometry_from_design_vector([float(value) for value in x12])
    built = openvsp_model.prepare_case(
        geometry, case_dir, basename,
        geometry_set=str(pre.get("geometry_set") or DEFAULT_GEOMETRY_SET),
        alphas_deg=[float(value) for value in (pre.get("alpha_list_deg") or
                                               TASK_SPEC.alpha_fixed_list_deg)],
        tess_u=_preflight_tess(pre)[0],
        tess_w=_preflight_tess(pre)[1],
        n_wake_nodes=_preflight_wake_nodes(pre),
        write_vsp3=True,
        mach_values=[float(value) for value in (pre.get("mach_list") or [TASK_SPEC.mach])],
        rebuild_strategy="roundtrip",
        target_mesh_family=target,
        max_mesh_attempts=int((case.get("mesh_identity") or {}).get("max_mesh_attempts") or 12),
    )
    mesh = built.get("mesh") or {}
    observed = str(mesh.get("mesh_family"))
    expected = "%dx%d" % target
    if observed != expected:
        raise BatchRefusal("FAIL_CLOSED: %s rebuilt mesh family %s != frozen target %s after %s "
                           "attempts" % (case_id, observed, expected, mesh.get("mesh_attempts")))
    verified: Dict[str, Any] = {}
    for name in INPUT_PIECES:
        entry = (built.get("artifacts") or {}).get(name)
        if entry is None:
            raise BatchRefusal("rebuilt case %s is missing the %s piece" % (case_id, name))
        path = Path(entry["path"])
        actual = ledger.sha256_file(path)
        if actual != str(entry["sha256"]):
            raise BatchRefusal("rebuilt %s changed on disk (%s)" % (path.name, case_id))
        verified[name] = {"path": str(path.resolve()), "bytes": int(entry["bytes"]),
                          "sha256": actual}
    case_inputs = {
        "schema": "dreal001.p1_case_inputs.v2",
        "case_id": case_id,
        "run_id": run_dir.name,
        "design_hash": case.get("design_hash"),
        "x12": [float(value) for value in x12],
        "design_hash_definition": "sha256(canonical x12 JSON)[:16]",
        "geometry_source": "REBUILT_FROM_X12_VIA_CANONICAL_PATH",
        "sref_m2": float(built.get("sref_m2")),
        "geometry_sha256": built.get("geometry_sha256"),
        "mesh": mesh,
        "mesh_family_target": expected,
        "mesh_selection_rule": "per-configuration L-09 selection frozen in plan.mesh_identity",
        "input_pieces": verified,
        "solver_argv": list((built.get("solver_invocation") or {}).get("argv") or []),
        "preregistration_sha256": case.get("preregistration_sha256"),
        "physical_solver_starts": 0,
        "created_utc": ledger.iso_utc(),
    }
    _write_json(case_dir / "case_inputs.json", case_inputs)
    return case_inputs


def _preflight_tess(pre: Dict[str, Any]) -> Tuple[float, float]:
    """Read Tess_U/Tess_W from a preflight record (tolerant of key spelling/case)."""
    tess = pre.get("tessellation")
    candidates = []
    if isinstance(tess, dict):
        for key_u, key_w in (("Tess_U", "Tess_W"), ("tess_u", "tess_w"),
                             ("TessU", "TessW")):
            if key_u in tess or key_w in tess:
                candidates.append((tess.get(key_u), tess.get(key_w)))
    candidates.append((pre.get("tess_u"), pre.get("tess_w")))
    for tu, tw in candidates:
        if tu is not None and tw is not None:
            return float(tu), float(tw)
    raise BatchRefusal("preflight record has no Tess_U/Tess_W pair: %r"
                       % (pre.get("config_id"),))


def _preflight_wake_nodes(pre: Dict[str, Any]):
    """Read NumWakeNodes from a preflight record (num_wake_nodes or n_wake_nodes)."""
    for key in ("num_wake_nodes", "n_wake_nodes"):
        value = pre.get(key)
        if value is not None:
            return int(value)
    return None


def _read_preflight(run_dir: Path, config_id: str) -> Dict[str, Any]:
    path = _preflight_dir(run_dir, config_id) / "preflight.json"
    return _read_json(path) if path.is_file() else {}


def build_case_plan(case: Dict[str, Any], plan: Dict[str, Any], run_dir: Path,
                    case_dir: Path, plan_sha256: str,
                    case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    pre = _read_preflight(run_dir, str(case["preflight_config_id"]))
    breakdown = case.get("internal_case_breakdown") or {}
    basename = str(case["solver_argv"][-1])
    solver = plan.get("solver") or {}
    expected_internal = int(case.get("expected_internal_cases") or 7)
    input_hashes = case_inputs.get("input_pieces") or {}
    sref = float(case_inputs.get("sref_m2") or pre.get("sref_m2") or TASK_SPEC.sref_baseline_m2)
    return {
        "schema": CASE_PLAN_SCHEMA,
        "batch_plan_sha256": plan_sha256,
        "batch_run_id": plan.get("run_id"),
        "run_id": plan.get("run_id"),
        "case_id": case["case_id"],
        "task_id": TASK_SPEC.task_id,
        "purpose": case.get("purpose"),
        "design": case.get("design"),
        "design_hash": case.get("design_hash") or case_inputs.get("design_hash"),
        "x12": list(case.get("x12") or case_inputs.get("x12") or []),
        "geometry": {
            "basename": basename,
            "geometry_source": "REBUILT_FROM_X12_VIA_CANONICAL_PATH",
            "geometry_sha256": case_inputs.get("geometry_sha256"),
            "mesh": case_inputs.get("mesh"),
            "mesh_family_target": case_inputs.get("mesh_family_target"),
            "sref_m2": sref,
            "geometry_set": pre.get("geometry_set") or DEFAULT_GEOMETRY_SET,
            "alpha_list_deg": pre.get("alpha_list_deg") or breakdown.get("alpha_list_deg"),
            "mach_list": breakdown.get("mach_list"),
            "tessellation": pre.get("tessellation"),
            "files": input_hashes,
        },
        "command": {"argv": [str(solver.get("path")), *[str(item) for item in case["solver_argv"][1:]]],
                    "solver_argv": list(case["solver_argv"])},
        "solver": {
            "path": solver.get("path"), "sha256": solver.get("sha256"),
            "version_banner": solver.get("version", "VSPAERO v7.2.2"),
            "cwd": str(case_dir.resolve()),
            "omp_threads": int(case.get("omp_threads") or 1),
            "timeout_s": int(case.get("timeout_seconds") or 900),
        },
        "budget": {
            "physical_solver_starts_max": 1 + _infra_retries(plan),
            "expected_internal_cases": expected_internal,
            "max_internal_cases": expected_internal,
            "batch_max_starts": int((plan.get("budget") or {}).get("max_starts", 0)),
        },
        "reference_quantities": {
            "sref_m2": sref, "cref_m": TASK_SPEC.cref_m, "bref_m": TASK_SPEC.bref_m,
            "xcg_m": TASK_SPEC.xcg_m, "reference_frame": TASK_SPEC.reference_frame,
            "q_pa": TASK_SPEC.q_pa, "l_ref_n": TASK_SPEC.l_ref_n,
            "note": "X_cg is the WING aerodynamic centre, not the geometric CG 28.287395 m",
        },
        "input_set_sha256": case.get("input_set_sha256"),
        "preregistration_sha256": case.get("preregistration_sha256"),
        "created_utc": ledger.iso_utc(),
        "physical_solver_starts": 0,
    }


def build_case_approval(case: Dict[str, Any], batch_approval: Dict[str, Any],
                        batch_plan_sha256: str, batch_approval_sha256: str,
                        case_plan_sha256: str, infra_retries: Optional[int] = None) -> Dict[str, Any]:
    window = batch_approval.get("window") or {}
    return {
        "schema": CASE_APPROVAL_SCHEMA,
        "derived_from_batch_approval": True,
        "derived_note": "derived mechanically from the approved batch approval; never widens "
                        "the approved case matrix, budget or window",
        "approved": True,
        "approved_by": batch_approval.get("approved_by"),
        "run_id": batch_approval.get("run_id"),
        "case_id": case["case_id"],
        "plan_sha256": case_plan_sha256,
        "batch_plan_sha256": batch_plan_sha256,
        "batch_approval_sha256": batch_approval_sha256,
        "window_token": ledger.approval_window_token(batch_approval),
        "window": {"start_utc": window.get("start_utc"), "end_utc": window.get("end_utc"),
                   "token": ledger.approval_window_token(batch_approval)},
        "max_starts": 1 + int(infra_retries if infra_retries is not None else DEFAULT_INFRA_RETRIES),
        "max_internal_cases": int(case.get("expected_internal_cases") or 7),
        "created_utc": ledger.iso_utc(),
    }


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _polar_points(spawned: Dict[str, Any]) -> List[Dict[str, Any]]:
    polar = spawned.get("polar") or {}
    points: List[Dict[str, Any]] = []
    for row in polar.get("rows") or []:
        mach = _number(row.get("Mach"))
        alpha = _number(row.get("AoA"))
        cl = _number(row.get("CLtot"))
        if mach is None or alpha is None or cl is None:
            continue
        points.append({
            "mach": mach, "alpha_deg": alpha,
            "beta_deg": _number(row.get("Beta")) or 0.0, "CLtot": cl,
            "CDi": _number(row.get("CDi")), "CDtot": _number(row.get("CDtot")),
            "CDo": _number(row.get("CDo")),
        })
    return points


def _interp(points: Sequence[Tuple[float, float]], target: float) -> Optional[float]:
    ordered = sorted(points)
    for (a0, v0), (a1, v1) in zip(ordered, ordered[1:]):
        if a0 <= target <= a1 and a1 != a0:
            return v0 + (target - a0) * (v1 - v0) / (a1 - a0)
    return None


def matched_cdi(points: Sequence[Dict[str, Any]], sref: float) -> Optional[float]:
    cl_target = TASK_SPEC.l_ref_n / (TASK_SPEC.q_pa * sref)
    pairs = [(point["CLtot"], point["CDi"]) for point in points
             if point["CDi"] is not None]
    return _interp(pairs, cl_target)


def dcl_dalpha(points: Sequence[Dict[str, Any]]) -> Optional[float]:
    pairs = sorted({(point["alpha_deg"], point["CLtot"]) for point in points})
    if len(pairs) < 2:
        return None
    n = float(len(pairs))
    sum_x = sum(item[0] for item in pairs)
    sum_y = sum(item[1] for item in pairs)
    sum_xx = sum(item[0] * item[0] for item in pairs)
    sum_xy = sum(item[0] * item[1] for item in pairs)
    denominator = n * sum_xx - sum_x * sum_x
    if denominator == 0:
        return None
    return (n * sum_xy - sum_x * sum_y) / denominator


def flatten_conditions(case: Dict[str, Any], case_plan: Dict[str, Any],
                       spawned: Dict[str, Any], attempt_id: str) -> List[Dict[str, Any]]:
    """One row per (Mach, alpha, Beta) flow condition; line-level starts stay 0."""
    points = _polar_points(spawned)
    sref = float((case_plan.get("geometry") or {}).get("sref_m2") or TASK_SPEC.sref_baseline_m2)
    q = TASK_SPEC.q_pa
    rows: List[Dict[str, Any]] = []
    for point in points:
        cl = point["CLtot"]
        cdi = point["CDi"]
        lift_n = q * sref * cl
        rows.append({
            "schema": "dreal001.evaluation_condition.v1",
            "run_id": case_plan.get("run_id"), "case_id": case.get("case_id"),
            "attempt_id": attempt_id, "config_id": case.get("config_id"),
            "task_id": case_plan.get("task_id"),
            "source_kind": "REAL_VSPAERO",
            "evidence_tier": "SOLVER_LOOP_VERIFIED",
            "physical_call_count": 0,
            "physical_solver_starts": 0,
            "attempt_physical_solver_starts": 1,
            "mach": point["mach"], "alpha_deg": point["alpha_deg"],
            "beta_deg": point["beta_deg"],
            "CLtot": cl, "CDi": cdi, "CDtot": point["CDtot"], "CDo": point["CDo"],
            "L_N": lift_n,
            "D_i_N": None if cdi is None else q * sref * cdi,
            "sref_m2": sref, "q_pa": q, "reference_frame": TASK_SPEC.reference_frame,
            "lift_rel_error_vs_Lref": (lift_n - TASK_SPEC.l_ref_n) / TASK_SPEC.l_ref_n,
            "design": case.get("design"),
            "design_hash": case.get("design_hash"),
            # A2 covariate: REAL records must carry the mesh family, never pool across families.
            "mesh_family": (case_plan.get("geometry") or {}).get("mesh_family_target"),
            "mesh": (case_plan.get("geometry") or {}).get("mesh"),
            "normalized_geometry_hash": ((case_plan.get("geometry") or {}).get("mesh") or {})
            .get("canonical_mesh_sha256"),
            "fuel_burn_kg": None,
            "external_physics_supported": False,
            "ts_utc": ledger.iso_utc(),
        })
    return rows


def _append_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def _history_row(case: Dict[str, Any], attempt_id: str, spawned: Dict[str, Any],
                 index: int) -> Dict[str, Any]:
    evaluation = spawned.get("evaluation") or {}
    match = evaluation.get("lift_match") or {}
    process = spawned.get("process") or {}
    internal = spawned.get("internal") or {}
    return {
        "iteration": index, "case_id": case.get("case_id"), "attempt_id": attempt_id,
        "config_id": case.get("config_id"), "status": spawned.get("status"),
        "exit_code": process.get("exit_code"), "wall_s": process.get("wall_s"),
        "internal_solver_cases": internal.get("count"),
        "lift_match_status": match.get("status"), "alpha_deg": match.get("alpha_deg"),
        "objective_D_i_N": (evaluation.get("objective") or {}).get("value"),
        "stop": "",
    }


def evaluate_stop_conditions(case_id: str, spawned: Dict[str, Any],
                             case_points: Sequence[Dict[str, Any]],
                             repeatability: Dict[str, Optional[float]],
                             starts: int, caps: Dict[str, int],
                             internal_total: int) -> List[Dict[str, str]]:
    hits: List[Dict[str, str]] = []
    status = str(spawned.get("status"))
    if status != SOLVED:
        hits.append({"condition": "S1", "detail": "case %s settled as %s" % (case_id, status)})
    negative = [point for point in case_points
                if point["CDi"] is not None and point["CDi"] < -1e-6 and abs(point["CLtot"]) > 0.05]
    if negative:
        label = "S2a" if case_id in THICK_CASES else "S2b"
        hits.append({"condition": label,
                     "detail": "negative CDi %r at %d flow condition(s) in %s"
                               % (negative[0]["CDi"], len(negative), case_id)})
    if starts > caps["max_starts"]:
        hits.append({"condition": "S5", "detail": "starts %d > max %d"
                                                   % (starts, caps["max_starts"])})
    if internal_total > caps["max_internal_cases"]:
        hits.append({"condition": "S5", "detail": "internal %d > max %d"
                                                   % (internal_total, caps["max_internal_cases"])})
    if len(repeatability) == len(REPEATABILITY_CASES):
        values = [value for value in repeatability.values() if value is not None]
        if len(values) == 3:
            spread = max(values) - min(values)
            magnitude = max(abs(value) for value in values)
            relative = spread / magnitude if magnitude else 0.0
            if spread > 1e-3 or relative > 0.01:
                hits.append({"condition": "S3",
                             "detail": "repeatability delta CDi %.3e (%.3f%%) across P1-00a/b/c"
                                       % (spread, relative * 100.0)})
    if case_id == "P1-00a":
        slope = dcl_dalpha(case_points)
        if slope is not None and not (0.03 <= slope <= 0.30):
            hits.append({"condition": "S4",
                         "detail": "dCL/dalpha %.4f per degree outside [0.03, 0.30]" % slope})
    return hits


def _write_run_config(run_dir: Path, batch: Dict[str, Any], approved: Dict[str, Any],
                      environment: Dict[str, Any]) -> None:
    plan = batch["plan"]
    payload = {
        "schema": "dreal001.p1_run_config.v1",
        "run_id": plan.get("run_id"), "batch_id": plan.get("batch_id"),
        "task_id": TASK_SPEC.task_id, "created_utc": ledger.iso_utc(),
        "plan_path": "plan.json", "plan_sha256": batch["plan_sha256"],
        "approval_sha256": approved.get("approval_sha256"),
        "budget": {"expected_starts": (plan.get("budget") or {}).get("expected_starts"),
                   "max_starts": approved.get("max_starts"),
                   "expected_internal_cases": (plan.get("budget") or {}).get("expected_internal_cases"),
                   "max_internal_cases": approved.get("max_internal_cases"),
                   "max_refine_starts": approved.get("max_refine_starts")},
        "solver": plan.get("solver"), "concurrency": 1, "omp_threads": 1,
        "timeout_seconds_per_case": plan.get("timeout_seconds_per_case"),
        "window": approved.get("window"),
        "environment": environment,
        "reference_quantities": {
            "sref_rule": "Sref(x) = exposed main-wing planform area from the frozen 12D space",
            "cref_m": TASK_SPEC.cref_m, "bref_m": TASK_SPEC.bref_m,
            "xcg_m": TASK_SPEC.xcg_m, "reference_frame": TASK_SPEC.reference_frame,
            "q_pa": TASK_SPEC.q_pa, "l_ref_n": TASK_SPEC.l_ref_n,
            "note": "X_cg is the WING aerodynamic centre, not the 28.287395 m geometric CG",
        },
        "labels": {"physical_solver_starts": "process starts",
                   "internal_solver_cases": "solver sub-cases inside one process",
                   "fuel_burn_kg": None, "external_physics_supported": False},
        "evidence_scope": {"evidence_tier": "SOLVER_LOOP_VERIFIED",
                           "internal_aero_optimization_gain": "NOT_CLAIMED",
                           "external_physics_supported": "NOT_CLAIMED",
                           "fuel_burn_kg": None},
        "gates": {"P0_SIGNED": "REQUIRED_BEFORE_FIRST_START",
                  "G-P1-PRE": "PREREG_PASS_REQUIRED_BEFORE_FIRST_START",
                  "LF-M2.02": "NOT_VALIDATED", "BODY-CORR": "BLOCKED",
                  "HF-M2.02": "PARTIAL"},
        "note": "declaration written by the batch driver; it adds no solver start",
    }
    _write_json(run_dir / "run_config.json", payload)


def _write_metrics(run_dir: Path, history: Sequence[Dict[str, Any]]) -> None:
    with open(run_dir / "metrics.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["metric", "value", "unit", "status", "note"])
        solved = [row for row in history if row["status"] == SOLVED]
        values = [row["objective_D_i_N"] for row in solved if row["objective_D_i_N"] is not None]
        best = min(values) if values else None
        writer.writerow(["completed_cases", len(history), "count", "OBSERVED",
                         "cases that returned a polar"])
        writer.writerow(["solved_cases", len(solved), "count", "OBSERVED", "status SOLVED"])
        writer.writerow(["D_i_N_at_matched_lift_best", "" if best is None else best, "N",
                         "OBSERVED" if best is not None else "NOT_RUN",
                         "minimum over solved cases; interpolated inside one polar"])
        for metric in ("drag_polar", "trim_curve", "fuel_burn_physical"):
            writer.writerow([metric, "", "", "NOT_RUN",
                             "requires validated external physics and a frozen mass/CG model"])


def _write_figures_readme(run_dir: Path) -> None:
    text = (
        "# figures（P1 批量运行）\n\n"
        "本目录不预置任何图。所有图必须由求解结果生成，且只有在该 case 的真实 .polar "
        "通过解析与记账校验后才允许绘制。\n\n"
        "- 若本批被停机或某 case 未解决，对应图状态为 NOT_RUN，不补画、不插值伪造。\n"
        "- 允许的图：CL-alpha、CDi-alpha、L/D-alpha；坐标与单位来自 case_result.json 的 "
        "reference 字段。\n"
        "- 禁止：用 VSPAERO 内部系数冒充实测阻力/油耗；禁止 fuel_burn_kg 曲线（恒为 null）；"
        "禁止未标注 Mach/alpha/Beta 的三维曲面。\n"
    )
    _write_bytes(run_dir / "figures" / "README.md", text.encode("utf-8"))


def _environment() -> Dict[str, Any]:
    import platform
    return {"python": platform.python_version(), "platform": platform.platform(),
            "solver": "VSPAERO v7.2.2 (OpenVSP-3.55.0-win64)",
            "omp_threads": 1, "concurrency": 1}


def _code_sha() -> str:
    import subprocess
    try:
        completed = subprocess.run(["git", "-C", str(Path(__file__).resolve().parents[4]),
                                    "rev-parse", "HEAD"],
                                   capture_output=True, text=True, timeout=15)
        return completed.stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _default_spawner(pre: Dict[str, Any], attempt_id: str, timeout_s: float) -> Dict[str, Any]:
    return solver_runner.spawn_case(pre, attempt_id, timeout_s=timeout_s)


def execute_batch(run_dir: str | Path, *, dry_run: bool = False,
                  spawner: Optional[Callable[..., Dict[str, Any]]] = None,
                  environment: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run (or dry-run) the approved P1 matrix.  Zero starts unless approval is valid."""
    batch = load_batch(run_dir)
    run_dir = batch["run_dir"]
    plan = batch["plan"]
    plan_sha = batch["plan_sha256"]
    if dry_run:
        report: Dict[str, Any] = {
            "status": "DRY_RUN", "run_id": plan.get("run_id"),
            "plan_sha256": plan_sha, "plan_bytes": batch["plan_bytes"],
            "case_count": len(batch["cases"]),
            "case_order": [case["case_id"] for case in batch["cases"]],
            "planned_starts": sum(int(case.get("starts") or 1) for case in batch["cases"]),
            "planned_internal_cases": sum(int(case.get("expected_internal_cases") or 0)
                                          for case in batch["cases"]),
            "approval": "ABSENT_OR_NOT_CHECKED_IN_DRY_RUN",
            "physical_solver_starts": 0, "wrote_files": [],
        }
        approval_path = run_dir / "approval.json"
        if approval_path.is_file():
            approval, approval_sha = _load_plan(approval_path)[0:2]
            try:
                report["approval"] = {"state": "VALID", **verify_approval(plan, plan_sha, approval,
                                                                          approval_sha)}
            except BatchRefusal as exc:
                report["approval"] = {"state": "REFUSED", "reason": str(exc)}
        # A5 B22: leave an auditable dry-run record; no case directory and no ledger line.
        report.update({"schema": "dreal001.dry_run.v1", "created_utc": ledger.iso_utc(),
                       "code_sha": _code_sha(),
                       "note": "dry run: no case directories, no ledger start lines",
                       "wrote_files": ["dry_run.json"]})
        dry_path = run_dir / "dry_run.json"
        dry_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
                            encoding="utf-8")
        return report

    approval_path = run_dir / "approval.json"
    if not approval_path.is_file():
        raise BatchRefusal("approval.json missing: P1 must not start without Lead approval")
    approval, approval_sha = _load_plan(approval_path)[0:2]
    approved = verify_approval(plan, plan_sha, approval, approval_sha)
    infra_retries = _infra_retries(plan)
    caps = approved
    spawner = spawner or _default_spawner
    batch_ledger = ledger.SolverLedger(run_dir, str(plan.get("run_id")), TASK_SPEC.task_id)
    if batch_ledger.count_starts():
        raise BatchRefusal("this run directory already has %d start line(s); reruns are refused"
                           % batch_ledger.count_starts())

    history: List[Dict[str, Any]] = []
    repeatability: Dict[str, Optional[float]] = {}
    internal_total = 0
    stop_hits: List[Dict[str, str]] = []
    evaluations_path = run_dir / "evaluations.jsonl"
    if not (run_dir / "figures" / "README.md").is_file():
        _write_figures_readme(run_dir)
    _write_run_config(run_dir, batch, approved, environment or _environment())
    spawned: Dict[str, Any] = {}
    case_points: List[Dict[str, Any]] = []
    case_plan: Dict[str, Any] = {}

    for index, case in enumerate(batch["cases"], start=1):
        case_id = str(case["case_id"])
        case_dir = _case_dir(run_dir, case_id)
        if (case_dir / "case_result.json").is_file():
            raise BatchRefusal("case %s already has case_result.json; reruns are refused" % case_id)
        window = ledger.window_status(approval)
        if not window["open"]:
            stop_hits.append({"condition": "S7",
                              "detail": "window closed before case %s: %s"
                                        % (case_id, window["reason"])})
            break
        case_dir.mkdir(parents=True, exist_ok=True)
        basename = str(case["solver_argv"][-1])
        # L-10: never copy the preflight template; rebuild this design from its x12.
        case_inputs = _prepare_case_inputs(case, run_dir, case_dir, basename)
        case_plan = build_case_plan(case, plan, run_dir, case_dir, plan_sha, case_inputs)
        case_plan_sha = sha256_bytes(_write_json(case_dir / "plan.json", case_plan))
        case_approval = build_case_approval(case, approval, plan_sha, approval_sha, case_plan_sha,
                                            infra_retries=infra_retries)
        _write_json(case_dir / "approval.json", case_approval)
        timeout_s = float((case_plan.get("solver") or {}).get("timeout_s") or 900)
        case_points = []
        spawned = {}
        attempt_number = 1
        while attempt_number <= 1 + infra_retries:
            attempt_id = "%s-a%02d" % (case_id, attempt_number)
            pre = solver_runner.prepare_case(case_dir / "plan.json", case_dir / "approval.json",
                                             attempt_id)
            starts_before = batch_ledger.count_starts()
            if starts_before + 1 > caps["max_starts"]:
                stop_hits.append({"condition": "S5",
                                  "detail": "next start would be %d > max %d"
                                            % (starts_before + 1, caps["max_starts"])})
                break
            expected_internal = int(case.get("expected_internal_cases") or 0)
            if internal_total + expected_internal > caps["max_internal_cases"]:
                stop_hits.append({"condition": "S5",
                                  "detail": "internal cases %d + %d > max %d"
                                            % (internal_total, expected_internal,
                                               caps["max_internal_cases"])})
                break
            batch_ledger.begin_attempt(
                attempt_id=attempt_id, case_id=case_id, argv=list(pre["argv"]),
                cwd=pre["cwd"], approval=approval, plan_sha256=plan_sha,
                approval_sha256=approval_sha, input_hashes=pre["geometry_files"],
                exe_sha256=pre["exe_sha256"], max_starts=caps["max_starts"],
                extra={"basename": basename, "config_id": case.get("config_id"),
                       "purpose": case.get("purpose"), "attempt_number": attempt_number,
                       "window_token": approved.get("window_token"),
                       "p0_signed_required": True},
                batch_id=plan.get("batch_id") or plan.get("run_id"),
                design_hash=case.get("design_hash"),
                x12=case.get("x12"),
                geometry_source="REBUILT_FROM_X12_VSPGEOM",
                solver_version=((plan.get("solver") or {}).get("version_banner")
                                or (plan.get("solver") or {}).get("version")),
                stdout_path=str(case_dir / "logs" / (attempt_id + ".stdout.log")),
                stderr_path=str(case_dir / "logs" / (attempt_id + ".stderr.log")),
            )
            spawned = spawner(pre, attempt_id, timeout_s)
            process = spawned.get("process") or {}
            internal = spawned.get("internal") or {}
            internal_count = int(internal.get("count") or 0)
            case_points = _polar_points(spawned)
            batch_ledger.end_attempt(
                attempt_id, process.get("exit_code"), str(spawned.get("status")),
                float(process.get("wall_s") or 0.0), outputs=spawned.get("outputs"),
                note=case.get("purpose"), internal_solver_cases=internal_count,
                internal_case_breakdown=internal,
                unique_flow_conditions=internal.get("unique_flow_conditions"),
                case_id=case_id)
            internal_total += internal_count
            rows = flatten_conditions(case, case_plan, spawned, attempt_id)
            _append_jsonl(evaluations_path, rows)
            history.append(_history_row(case, attempt_id, spawned, index))
            case_result = {"schema": CASE_RESULT_SCHEMA, "case_id": case_id,
                           "attempt_id": attempt_id, "plan_sha256": case_plan_sha,
                           "approval_sha256": sha256_bytes(_json_bytes(case_approval)),
                           "process": process, "status": spawned.get("status"),
                           "internal": internal, "outputs": spawned.get("outputs"),
                           "evaluation": spawned.get("evaluation"),
                           "design_hash": case.get("design_hash"),
                           "x12": case.get("x12"),
                           "mesh": (case_plan.get("geometry") or {}).get("mesh"),
                           "mesh_family_target": (case_plan.get("geometry") or {})
                           .get("mesh_family_target"),
                           "flow_condition_rows": len(rows),
                           "physical_solver_starts": 1, "ts_utc": ledger.iso_utc()}
            _write_json(case_dir / "case_result.json", case_result)
            status = str(spawned.get("status"))
            if status != SOLVED and attempt_number == 1 and _retryable_failure(status):
                history[-1]["stop"] = "INFRA_RETRY_SCHEDULED"
                attempt_number += 1
                continue
            break
        if case_id in REPEATABILITY_CASES and case_points:
            sref = float((case_plan.get("geometry") or {}).get("sref_m2")
                         or TASK_SPEC.sref_baseline_m2)
            repeatability[case_id] = matched_cdi(case_points, sref)
        if not stop_hits:
            stop_hits = evaluate_stop_conditions(case_id, spawned, case_points, repeatability,
                                                 batch_ledger.count_starts(), caps, internal_total)
        if stop_hits:
            break

    summary: Dict[str, Any] = {
        "schema": BATCH_RUN_SCHEMA, "run_id": plan.get("run_id"),
        "status": "STOPPED_FAIL_CLOSED" if stop_hits else "COMPLETED",
        "plan_sha256": plan_sha, "approval_sha256": approval_sha,
        "case_count": len({row["case_id"] for row in history}),
        "attempt_count": len(history),
        "physical_solver_starts": batch_ledger.count_starts(),
        "internal_solver_cases": internal_total,
        "caps": caps, "stop_hits": stop_hits, "refine_starts_used": 0,
        "refine_policy": "one refine start (7 internal cases) remains available only with an "
                         "explicit Lead instruction; this driver never auto-refines",
        "evaluations_path": "evaluations.jsonl", "history_path": "optimization_history.csv",
        "fuel_burn_kg": None, "evidence_tier": "SOLVER_LOOP_VERIFIED",
        "physical_validation_status": "NOT_VALIDATED", "created_utc": ledger.iso_utc(),
    }
    if stop_hits:
        _write_json(run_dir / "stop_report.json",
                    {"schema": STOP_REPORT_SCHEMA, "status": "STOPPED_FAIL_CLOSED",
                     "run_id": plan.get("run_id"), "plan_sha256": plan_sha,
                     "conditions": stop_hits, "completed_cases": summary["case_count"],
                     "physical_solver_starts": batch_ledger.count_starts(),
                     "internal_solver_cases": internal_total,
                     "created_utc": ledger.iso_utc(),
                     "next_action": "human review; remaining cases must not start"})
    if history:
        with open(run_dir / "optimization_history.csv", "w", encoding="utf-8",
                  newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(history[0].keys()),
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(history)
    if not evaluations_path.is_file():
        _write_bytes(evaluations_path, b"")
    _write_metrics(run_dir, history)
    retention_entries = evidence_manifest.record_retention(run_dir, delete=False)
    _write_json(run_dir / "batch_summary.json", summary)
    totals = evidence_manifest.ledger_totals(run_dir / "solver_attempts.jsonl", run_dir)
    evaluation_rows = sum(1 for line in evaluations_path.read_text(encoding="utf-8").splitlines()
                          if line.strip())
    summary["conservation_check"] = {
        "ledger_starts": totals["physical_solver_starts"],
        "batch_ledger_starts": batch_ledger.count_starts(),
        "ledger_internal_cases": totals["internal_solver_cases"],
        "summed_internal_cases": internal_total,
        "evaluation_rows": evaluation_rows,
        "starts_bounded_by_cap": totals["physical_solver_starts"] <= caps["max_starts"],
        "internal_bounded_by_cap": totals["internal_solver_cases"] <= caps["max_internal_cases"],
        "evaluation_rows_match_internal_cases": evaluation_rows == totals["internal_solver_cases"],
    }
    summary["conservation_check"]["ok"] = bool(
        summary["conservation_check"]["ledger_starts"] == batch_ledger.count_starts()
        and summary["conservation_check"]["ledger_internal_cases"] == internal_total
        and summary["conservation_check"]["starts_bounded_by_cap"]
        and summary["conservation_check"]["internal_bounded_by_cap"])
    _write_json(run_dir / "batch_summary.json", summary)
    evidence_manifest.write_manifest(run_dir, retention_entries=retention_entries,
                                     extra={"batch_summary": summary,
                                            "conservation_check": summary["conservation_check"]})
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="P1 sequential batch driver (D-REAL-001 A1)")
    parser.add_argument("command", choices=("dry-run", "run"))
    parser.add_argument("--run-dir", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        summary = execute_batch(args.run_dir, dry_run=(args.command == "dry-run"))
    except BatchRefusal as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, indent=2,
                         ensure_ascii=False))
        return 2
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 1 if summary.get("status") == "STOPPED_FAIL_CLOSED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
