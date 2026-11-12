"""One real VSPAERO 7.2.2 solver start, fully accounted and parsed (D-REAL-001 A1).

Contract (frozen 2026-11-10, Lead ruling):

* one process start == one physical_solver_start, regardless of how many alpha
  points the single start carries (the -fs list is one start);
* the solver is launched only through this module so that START/END lines are
  appended to solver_attempts.jsonl around the real process;
* every run verifies the approved plan digest, the approval digest, the
  approved window, the executable hash and all solver input hashes BEFORE the
  process is spawned; refusals never touch the ledger;
* outputs (.polar/.history/.lod/.groups/stdout/stderr plus inputs) are hashed
  and recorded; parsing is delegated to polar_parser (no penalty substitution);
* fuel_burn_kg is always null and the evidence scope is SOLVER_LOOP_VERIFIED
  only: this module makes no physical or fuel claim.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

if __package__ in (None, ""):  # direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    from research.concorde_metaopt.dreal001.geometry import design_identity, ledger, polar_parser
    from research.concorde_metaopt.dreal001.geometry.task_spec import TASK_SPEC
else:
    from . import design_identity, ledger, polar_parser
    from .task_spec import TASK_SPEC

REPO_ROOT = Path(__file__).resolve().parents[4]
EVALUATION_SCHEMA = "dreal001.aero_eval.v1"
CASE_RESULT_SCHEMA = "dreal001.solver_case_result.v1"


class PreflightError(RuntimeError):
    """Raised when the plan/approval/input contract does not match the disk state."""


def _load_json(path: Path) -> Tuple[Dict[str, Any], str, int]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        # fail-closed with a typed preflight refusal (CLI exit 2), never a traceback:
        # a missing plan/approval must not look like an infrastructure crash.
        raise PreflightError("required file missing: %s" % path) from exc
    return json.loads(raw.decode("utf-8")), ledger.sha256_bytes(raw), len(raw)


SUFFIX_BY_LABEL = {
    "vspgeom": ".vspgeom", "vkey": ".vkey", "vspaero": ".vspaero",
    "csf": ".csf", "vsp3": ".vsp3", "geom_csv": "_vspaero_geom.csv",
}


def _verify_file_hashes(spec: Dict[str, Any], base_dir: Path, label: str,
                        basename: Optional[str] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for name, entry in (spec or {}).items():
        expected = entry.get("sha256") if isinstance(entry, dict) else str(entry)
        relative = entry.get("path") if isinstance(entry, dict) else None
        if relative:
            candidate = Path(relative)
        else:
            suffix = SUFFIX_BY_LABEL.get(name, "." + name)
            candidate = base_dir / ((basename + suffix) if basename else name)
        if not candidate.is_file():
            raise PreflightError("%s file missing: %s" % (label, candidate))
        actual = ledger.sha256_file(candidate)
        if expected and actual != expected:
            raise PreflightError("%s hash mismatch for %s: disk %s != plan %s"
                                 % (label, candidate.name, actual, expected))
        result[name] = {"path": str(candidate), "bytes": candidate.stat().st_size, "sha256": actual}
    return result


def preflight(plan_path: Path, approval_path: Path, attempt_id: str) -> Dict[str, Any]:
    """Validate plan/approval/disk consistency without spawning anything."""
    plan, plan_sha, plan_bytes = _load_json(plan_path)
    approval, approval_sha, approval_bytes = _load_json(approval_path)
    if not attempt_id:
        raise PreflightError("attempt_id is required")
    if approval.get("approved") is not True:
        raise PreflightError("approval is not approved")
    if approval.get("plan_sha256") != plan_sha:
        raise PreflightError("plan sha256 %s != approval.plan_sha256 %s"
                             % (plan_sha, approval.get("plan_sha256")))
    if approval.get("run_id") != plan.get("run_id") or approval.get("case_id") != plan.get("case_id"):
        raise PreflightError("approval run_id/case_id does not match the plan")
    status = ledger.window_status(approval)
    solver = plan.get("solver") or {}
    exe = Path(solver.get("path", ""))
    if not exe.is_file():
        raise PreflightError("solver executable missing: %s" % exe)
    exe_sha = ledger.sha256_file(exe)
    if solver.get("sha256") and exe_sha != solver["sha256"]:
        raise PreflightError("solver executable sha256 %s != plan %s" % (exe_sha, solver["sha256"]))
    declared_cwd = Path(solver.get("cwd", ""))
    cwd = declared_cwd if declared_cwd.is_absolute() else REPO_ROOT / declared_cwd
    if not cwd.is_dir():
        raise PreflightError("solver cwd missing: %s" % cwd)
    argv = [str(item) for item in (plan.get("command") or {}).get("argv") or []]
    if not argv:
        raise PreflightError("plan.command.argv is empty")
    basename = argv[-1]
    for suffix in (".vspgeom", ".vkey", ".vspaero"):
        if not (cwd / (basename + suffix)).is_file():
            raise PreflightError("solver input missing: %s" % (cwd / (basename + suffix)))
    geometry_files = _verify_file_hashes((plan.get("geometry") or {}).get("files") or {}, cwd, "geometry", basename=basename)
    return {
        "plan": plan, "plan_sha256": plan_sha, "plan_bytes": plan_bytes,
        "approval": approval, "approval_sha256": approval_sha, "approval_bytes": approval_bytes,
        "window": status, "exe": exe, "exe_sha256": exe_sha, "cwd": cwd,
        "argv": argv, "basename": basename, "geometry_files": geometry_files,
        "solver_config_sha256": geometry_files.get("vspaero", {}).get("sha256"),
        "geometry_sha256": geometry_files.get("vspgeom", {}).get("sha256"),
    }


def _run_process(argv: Sequence[str], cwd: Path, timeout_s: float, log_dir: Path,
                 attempt_id: str) -> Dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / (attempt_id + ".stdout.log")
    stderr_path = log_dir / (attempt_id + ".stderr.log")
    started = time.perf_counter()
    timed_out = False
    with open(stdout_path, "wb") as out_handle, open(stderr_path, "wb") as err_handle:
        process = subprocess.Popen(list(argv), cwd=str(cwd), stdout=out_handle,
                                   stderr=err_handle, stdin=subprocess.DEVNULL)
        try:
            exit_code: Optional[int] = process.wait(timeout=float(timeout_s))
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            exit_code = process.wait(timeout=60)
    wall_s = time.perf_counter() - started
    return {
        "exit_code": exit_code, "timed_out": timed_out, "wall_s": round(wall_s, 3),
        "stdout_path": str(stdout_path), "stderr_path": str(stderr_path),
        "stdout_bytes": stdout_path.stat().st_size, "stderr_bytes": stderr_path.stat().st_size,
        "stdout_sha256": ledger.sha256_file(stdout_path),
        "stderr_sha256": ledger.sha256_file(stderr_path),
    }


def _collect_outputs(cwd: Path, basename: str) -> Dict[str, Any]:
    outputs: Dict[str, Any] = {}
    candidates = [basename + suffix for suffix in
                  (".polar", ".history", ".lod", ".groups", ".adb", ".csf",
                   ".vspgeom", ".vkey", ".vspaero")]
    candidates += [path.name for path in cwd.glob(basename + ".group.*")]
    for name in sorted(set(candidates)):
        path = cwd / name
        if path.is_file():
            outputs[name] = {"path": str(path), "bytes": path.stat().st_size,
                             "sha256": ledger.sha256_file(path)}
    return outputs


def _interp_alpha(rows: Sequence[Dict[str, Any]], cl_target: float) -> Dict[str, Any]:
    raw_points: List[Tuple[float, float]] = []
    for row in rows:
        alpha = polar_parser.field(row, "AoA")
        cl = polar_parser.cltot(row)
        if alpha is None or cl is None:
            continue
        if math.isfinite(float(alpha)) and math.isfinite(float(cl)):
            raw_points.append((float(alpha), float(cl)))
    # 重复 alpha 不得静默折叠：Mach 扫描会在同一 alpha 上出现多行，
    # 若直接排序插值会得到 a1 == a0 的伪斜率（P1-05 崩溃根因）。
    collapsed: Dict[float, List[float]] = {}
    for alpha, cl in raw_points:
        collapsed.setdefault(round(alpha, 9), []).append(cl)
    duplicate_alphas = sorted(a for a, values in collapsed.items() if len(values) > 1)
    if duplicate_alphas:
        return {
            "status": "DEGENERATE_ALPHA_ROWS",
            "duplicate_alpha_deg": duplicate_alphas,
            "duplicate_alpha_count": len(duplicate_alphas),
            "note": "同一 alpha 出现多行（多 Mach 扫描）；拒绝插值，objective 置空",
        }
    points = sorted((alpha, values[0]) for alpha, values in collapsed.items())
    if len(points) < 2:
        return {"status": "INSUFFICIENT_ALPHA_POINTS", "points": points}
    alphas = [point[0] for point in points]
    clos = [point[1] for point in points]
    if not (min(clos) <= cl_target <= max(clos)):
        return {"status": "CL_TARGET_OUTSIDE_POLAR", "cl_target": cl_target,
                "cl_min": min(clos), "cl_max": max(clos), "points": points}
    for index in range(len(points) - 1):
        a0, cl0 = points[index]
        a1, cl1 = points[index + 1]
        if cl0 == cl1:
            continue
        if (cl0 - cl_target) * (cl1 - cl_target) <= 0.0:
            fraction = (cl_target - cl0) / (cl1 - cl0)
            alpha = a0 + fraction * (a1 - a0)
            slope = (cl1 - cl0) / (a1 - a0)
            low, high = TASK_SPEC.alpha_window_deg
            return {
                "status": "LIFT_MATCHED_BY_INTERPOLATION",
                "cl_target": cl_target, "alpha_deg": alpha, "bracket_alpha_deg": [a0, a1],
                "bracket_cl": [cl0, cl1], "local_dcl_dalpha_per_deg": slope,
                "alpha_in_preregistered_window": bool(low <= alpha <= high),
                "lift_residual_rel_at_alpha": 0.0,
                "note": "alpha is interpolated inside one polar; no extra solver start",
            }
    return {"status": "INTERPOLATION_FAILED", "cl_target": cl_target, "points": points}


def _interp_field_at_alpha(rows: Sequence[Dict[str, Any]], alpha: float,
                           field_name: str) -> Optional[float]:
    """Linear interpolation of one polar field at a given alpha (post-processing only)."""
    valid = [row for row in rows
             if polar_parser.row_is_valid(row) and polar_parser.field(row, "AoA") is not None]
    valid = sorted(valid, key=lambda row: float(polar_parser.field(row, "AoA")))
    for low, high in zip(valid, valid[1:]):
        a0 = float(polar_parser.field(low, "AoA"))
        a1 = float(polar_parser.field(high, "AoA"))
        if a0 <= alpha <= a1 and a1 != a0:
            v0 = polar_parser.field(low, field_name)
            v1 = polar_parser.field(high, field_name)
            if v0 is None or v1 is None:
                return None
            fraction = (alpha - a0) / (a1 - a0)
            return float(v0) + fraction * (float(v1) - float(v0))
    return None


def _internal_case_info(cwd: Path, basename: str,
                         polar: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Count the cases VSPAERO actually solved inside one process start.

    Primary source is <base>.adb.cases (one line per solved case: Mach AoA Beta);
    fallback is the raw .polar row count.  The 7.2.2 append-merge behaviour of the
    -fs lists can multiply the preregistered matrix, so this must be recorded and
    compared with the approved expected/max internal case counts.
    """
    cases_path = cwd / (basename + ".adb.cases")
    breakdown: Dict[str, Any] = {"source": None, "count": 0,
                                 "mach_values": [], "aoa_values": [], "beta_values": []}
    if cases_path.is_file():
        machs: List[float] = []
        aoas: List[float] = []
        betas: List[float] = []
        for line in cases_path.read_text(encoding="utf-8", errors="replace").splitlines():
            tokens = line.split()
            if len(tokens) < 3:
                continue
            try:
                mach, aoa, beta = (float(tokens[0]), float(tokens[1]), float(tokens[2]))
            except ValueError:
                continue
            machs.append(mach); aoas.append(aoa); betas.append(beta)
        if machs:
            breakdown.update({
                "source": cases_path.name, "count": len(machs),
                "mach_values": sorted(set(round(value, 9) for value in machs)),
                "aoa_values": sorted(set(round(value, 9) for value in aoas)),
                "beta_values": sorted(set(round(value, 9) for value in betas)),
            })
    if not breakdown["count"] and polar:
        breakdown.update({"source": "polar_rows", "count": int(polar.get("row_count") or 0),
                          "mach_values": sorted({round(float(row.get("Mach", float("nan"))), 9)
                                                 for row in polar.get("rows", [])}),
                          "aoa_values": sorted({round(float(row.get("AoA", float("nan"))), 9)
                                                for row in polar.get("rows", [])}),
                          "beta_values": sorted({round(float(row.get("Beta", float("nan"))), 9)
                                                 for row in polar.get("rows", [])})})
    if polar:
        unique = polar.get("unique_case_rows")
        if not unique:
            # A5 B21: unique_flow_conditions must be the real count (7 for a 7-alpha start),
            # not 0 just because unique_case_rows is filled in after this helper runs.
            seen = set()
            unique = []
            for row in polar.get("rows") or []:
                key = tuple(round(float(polar_parser.field(row, label) or float("nan")), 9)
                            for label in ("Mach", "AoA", "Beta"))
                if key in seen:
                    continue
                seen.add(key)
                unique.append(row)
        breakdown["unique_flow_conditions"] = len(unique)
        breakdown["raw_polar_rows"] = int(polar.get("row_count") or 0)
    return breakdown


def build_evaluation(preflight_record: Dict[str, Any], process: Dict[str, Any],
                     outputs: Dict[str, Any], polar: Optional[Dict[str, Any]],
                     attempt_id: str, status: str) -> Dict[str, Any]:
    plan = preflight_record["plan"]
    geometry = plan.get("geometry") or {}
    sref = float(geometry.get("sref_m2") or TASK_SPEC.sref_baseline_m2)
    q = TASK_SPEC.q_pa
    rows_out: List[Dict[str, Any]] = []
    unique_rows = (polar.get("unique_case_rows") or polar["rows"]) if polar else []
    if polar:
        for row in unique_rows:
            alpha = polar_parser.field(row, "AoA")
            cl = polar_parser.cltot(row)
            cdi = polar_parser.field(row, "CDi")
            cdtot = polar_parser.field(row, "CDtot")
            cdo = polar_parser.field(row, "CDo")
            valid = polar_parser.row_is_valid(row)
            entry: Dict[str, Any] = {
                "alpha_deg": alpha, "CLtot": cl, "CDo": cdo, "CDi": cdi, "CDtot": cdtot,
                "valid": bool(valid), "invalid_tokens": row.get("_invalid_tokens") or {},
            }
            if valid:
                lift_n = q * sref * float(cl)
                di_n = q * sref * float(cdi)
                dtotal_n = q * sref * float(cdtot)
                entry.update({
                    "L_N": lift_n, "D_i_N": di_n, "D_total_N": dtotal_n,
                    "lift_rel_error_vs_Lref": (lift_n - TASK_SPEC.l_ref_n) / TASK_SPEC.l_ref_n,
                    "lift_match_initial_tol": TASK_SPEC.lift_matched(sref, float(cl)),
                })
            rows_out.append(entry)
    cl_target = TASK_SPEC.l_ref_n / (q * sref)
    # Mach 扫描案（P1-05 的 1.8/2.0/2.2）没有 Mach 2.02 行：按最近的 Mach 取子集插值，
    # 绝不把不同 Mach 的行混在一起插值（P1-05 崩溃根因）。
    mach_values: List[float] = []
    for row in unique_rows:
        mach = polar_parser.field(row, "Mach")
        if mach is not None and math.isfinite(float(mach)):
            mach_values.append(float(mach))
    mach_values = sorted({round(float(m), 9) for m in mach_values})
    match_mach: Optional[float] = None
    match_rows: List[Dict[str, Any]] = []
    if mach_values:
        target_mach = float(TASK_SPEC.mach)
        match_mach = min(mach_values, key=lambda m: abs(m - target_mach))
        match_rows = [
            row for row in unique_rows
            if polar_parser.field(row, "Mach") is not None
            and abs(float(polar_parser.field(row, "Mach")) - match_mach) < 1e-9
        ]
    objective_scope = "MACH_SWEEP_NEAREST_MACH" if len(mach_values) > 1 else "SINGLE_MACH"
    if not polar:
        match: Dict[str, Any] = {"status": "NO_POLAR"}
    elif not match_rows:
        match = {
            "status": "INSUFFICIENT_MACH_ROWS",
            "cl_target": cl_target,
            "polar_mach_values": mach_values,
            "note": "polar 中没有可用 Mach 行；不回落全部行，objective 置空",
        }
    else:
        match = _interp_alpha(match_rows, cl_target)
    match["polar_mach_values"] = mach_values
    match["lift_match_mach"] = match_mach
    match["objective_scope"] = objective_scope
    if len(mach_values) > 1:
        match["lift_match_mach_note"] = (
            "本 polar 为 Mach 扫描（多 Mach 行）；按离 TASK_SPEC.mach=2.02 最近的 Mach 取子集，"
            "不增加任何求解器启动，也不跨 Mach 插值"
        )
    objective: Dict[str, Any] = {"name": "D_i_N_at_matched_lift", "value": None}
    constraints: Dict[str, Any] = {"lift_matched": False, "alpha_in_window": False,
                                   "drag_positive": None}
    if match.get("status") == "LIFT_MATCHED_BY_INTERPOLATION":
        alpha_match = float(match["alpha_deg"])
        cdi_match = _interp_field_at_alpha(match_rows, alpha_match, "CDi")
        cdtot_match = _interp_field_at_alpha(match_rows, alpha_match, "CDtot")
        cl_match = _interp_field_at_alpha(match_rows, alpha_match, "CLtot")
        if cdi_match is not None:
            objective = {
                "name": "D_i_N_at_matched_lift",
                "value": q * sref * float(cdi_match),
                "cdi_at_matched_lift": float(cdi_match),
                "cdtot_at_matched_lift": cdtot_match,
                "cltot_at_matched_lift": cl_match,
                "alpha_deg": alpha_match,
                "sref_m2": sref, "q_pa": q,
                "lift_rel_error": 0.0,
                "lift_match_mach": match_mach,
                "objective_scope": objective_scope,
                "note": "interpolated inside the single polar; no extra solver start",
            }
        constraints = {
            "lift_matched": True,
            "alpha_in_window": bool(match.get("alpha_in_preregistered_window")),
            "drag_positive": bool(cdi_match is not None and float(cdi_match) >= 0.0),
            "cm_trimming": "DISABLED_UNTIL_MASS_CG_FROZEN",
        }
    return {
        "schema": EVALUATION_SCHEMA,
        "backend": "REAL_VSPAERO",
        "source_kind": "REAL_VSPAERO",
        "cache_hit": False,
        "cache_key": None,
        "labels_visible_to_arm": ["CLtot", "CDi", "CDtot", "CMz", "alpha_deg",
                                  "L_N", "D_i_N", "lift_match", "status"],
        "labels_hidden_from_arm": ["fuel_burn_kg", "external_physics_supported"],
        "objective": objective,
        "constraints": constraints,
        "lift_match_status": match.get("status"),
        "lift_match_mach": match_mach,
        "polar_mach_values": mach_values,
        "objective_scope": objective_scope,
        "run_id": plan.get("run_id"), "case_id": plan.get("case_id"),
        "task_id": plan.get("task_id"), "attempt_id": attempt_id,
        "purpose": plan.get("purpose"),
        "status": status,
        "solver": {
            "version": (plan.get("solver") or {}).get("version_banner", "VSPAERO v.7.2.2"),
            "executable_sha256": preflight_record["exe_sha256"],
            "argv": preflight_record["argv"], "cwd": str(preflight_record["cwd"]),
            "omp_threads": (plan.get("solver") or {}).get("omp_threads"),
            "timeout_s": (plan.get("solver") or {}).get("timeout_s"),
        },
        "geometry_set": geometry.get("geometry_set", TASK_SPEC.default_geometry_set),
        "geometry_sha256": preflight_record.get("geometry_sha256")
                            or geometry.get("geometry_sha256")
                            or (preflight_record.get("case_inputs") or {}).get("geometry_sha256"),
        "design_hash": preflight_record.get("geometry_sha256")
                       or geometry.get("geometry_sha256")
                       or (preflight_record.get("case_inputs") or {}).get("geometry_sha256"),
        "design_hash_definition": "sha256(raw bytes of the case .vspgeom) = geometry identity "
                                  "for a REAL_VSPAERO evaluation; equal to geometry_sha256",
        "solver_config_sha256": preflight_record.get("solver_config_sha256")
                               or (plan.get("solver") or {}).get("solver_config_hash")
                               or (preflight_record.get("case_inputs") or {}).get("solver_config_sha256"),
        "raw_artifacts": outputs,
        "tessellation": geometry.get("tessellation"),
        "reference": {
            "sref_m2": sref, "cref_m": TASK_SPEC.cref_m, "bref_m": TASK_SPEC.bref_m,
            "xcg_m": TASK_SPEC.xcg_m, "reference_frame": TASK_SPEC.reference_frame,
            "mach": TASK_SPEC.mach, "vinf_m_s": TASK_SPEC.vinf_m_s,
            "rho_kg_m3": TASK_SPEC.rho_kg_m3, "q_pa": q, "recref": TASK_SPEC.recref,
            "l_ref_n": TASK_SPEC.l_ref_n, "cl_target": cl_target,
            "units": {"L_N": "N", "D_i_N": "N", "sref_m2": "m2", "q_pa": "Pa"},
        },
        "alpha_list_deg": geometry.get("alpha_list_deg") or (plan.get("command") or {}).get("alphas"),
        "accounting": {
            "physical_solver_starts": 1,
            "internal_solver_cases": (polar or {}).get("internal_solver_cases"),
            "unique_flow_conditions": len(unique_rows) if polar else 0,
            "raw_polar_rows": (polar or {}).get("row_count"),
            "internal_case_breakdown": (polar or {}).get("internal_case_breakdown"),
            "fs_cli_used": any(token in ("-fs", "-mach") for token in (preflight_record["argv"] or [])),
            "note": "physical starts are process starts; internal cases are the solver sub-cases "
                    "solved inside that process (VSPAERO merges -fs lists with .vspaero lists)",
        },
        "rows": rows_out,
        "lift_match": match,
        "lift_tolerance_rel": TASK_SPEC.lift_tolerance_rel,
        "physical_solver_starts": 1,
        "process": {key: process[key] for key in
                    ("exit_code", "timed_out", "wall_s", "stdout_sha256", "stderr_sha256")},
        "outputs": outputs,
        "evidence_tier": "SOLVER_LOOP_VERIFIED",
        "evidence_split": {"solver_loop_verified": "ELIGIBLE_AFTER_P0_P1",
                           "internal_aero_optimization_gain": "NOT_CLAIMED",
                           "external_physics_supported": "NOT_CLAIMED",
                           "fuel_burn_kg": None,
                           "scope": "SOLVER_LOOP_VERIFIED_ONLY"},
        "note": "VSPAERO-internal wing-model aerodynamics only; not a fuel-burn or full-aircraft result",
    }


def prepare_case(plan_path: str | Path, approval_path: str | Path,
                 attempt_id: str) -> Dict[str, Any]:
    """Zero-physical preparation of one case: load + validate plan/approval/inputs.

    Returns the pre mapping accepted by spawn_case.  Nothing is spawned and no ledger
    line is written here; the caller owns accounting.
    """
    plan_path = Path(plan_path).resolve()
    approval_path = Path(approval_path).resolve()
    return preflight(plan_path, approval_path, attempt_id)


def spawn_case(pre: Dict[str, Any], attempt_id: str, dry_run: bool = False,
               timeout_s: Optional[float] = None,
               omp_override: Optional[int] = None) -> Dict[str, Any]:
    """Spawn exactly one VSPAERO process and parse its outputs (no ledger writes).

    Accounting stays with the caller (see run_case and the P1 batch driver).
    dry_run=True never launches a process and reports status=DRY_RUN_OK.
    """
    plan = pre["plan"]
    argv = list(pre["argv"])
    if omp_override is not None:
        if "-omp" in argv:
            position = argv.index("-omp") + 1
            if position < len(argv):
                argv[position] = str(int(omp_override))
    timeout = float(timeout_s if timeout_s is not None else
                    (plan.get("solver") or {}).get("timeout_s", 600))
    if dry_run:
        return {"status": "DRY_RUN_OK", "physical_solver_starts": 0, "argv": argv,
                "cwd": str(pre["cwd"]), "attempt_id": attempt_id,
                "plan_sha256": pre["plan_sha256"],
                "approval_sha256": pre["approval_sha256"]}
    process = _run_process(argv, pre["cwd"], timeout, pre["cwd"] / "logs", attempt_id)
    outputs = _collect_outputs(pre["cwd"], pre["basename"])
    polar = None
    polar_error = None
    if (pre["cwd"] / (pre["basename"] + ".polar")).is_file():
        try:
            polar = polar_parser.parse_polar_file(pre["cwd"] / (pre["basename"] + ".polar"))
        except polar_parser.PolarParseError as exc:
            polar_error = str(exc)
    internal = _internal_case_info(pre["cwd"], pre["basename"], polar)
    if polar is not None:
        polar["unique_case_rows"] = polar_parser.unique_case_rows(polar["rows"])
        polar["case_multiplicity"] = polar_parser.case_multiplicity(polar["rows"])
        polar["internal_solver_cases"] = internal["count"]
        polar["internal_case_breakdown"] = internal
    if process["timed_out"]:
        status = "TIMEOUT"
    elif process["exit_code"] not in (0,):
        status = "SOLVER_EXIT_%s" % process["exit_code"]
    elif polar is None:
        status = "MISSING_OR_UNPARSED_POLAR"
    elif polar["invalid_row_count"] > 0:
        status = "POLAR_HAS_INVALID_ROWS"
    else:
        status = "SOLVED"
    evaluation = build_evaluation(pre, process, outputs, polar, attempt_id, status)
    evaluation["polar_parse_error"] = polar_error
    budget = plan.get("budget") or {}
    expected_internal = budget.get("expected_internal_cases")
    max_internal = budget.get("max_internal_cases")
    accounting_flags: List[str] = []
    if expected_internal is not None and int(internal["count"]) != int(expected_internal):
        accounting_flags.append("ACCOUNTING_MISMATCH_EXPECTED_INTERNAL_CASES")
    if max_internal is not None and int(internal["count"]) > int(max_internal):
        accounting_flags.append("INTERNAL_CASES_EXCEED_MAX")
    evaluation["accounting"]["expected_internal_cases"] = expected_internal
    evaluation["accounting"]["max_internal_cases"] = max_internal
    evaluation["accounting"]["accounting_flags"] = accounting_flags
    return {
        "schema": CASE_RESULT_SCHEMA, "status": status, "argv": argv,
        "cwd": str(pre["cwd"]), "attempt_id": attempt_id,
        "plan_sha256": pre["plan_sha256"], "approval_sha256": pre["approval_sha256"],
        "window": pre["window"], "process": process, "outputs": outputs,
        "polar": polar, "internal": internal, "evaluation": evaluation,
        "accounting_flags": accounting_flags, "physical_solver_starts": 1,
    }


def _code_sha() -> str:
    """HEAD of the worktree, recorded in the dry-run audit file (A5 B22)."""
    try:
        import subprocess
        root = Path(__file__).resolve().parents[4]
        completed = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                   capture_output=True, text=True, timeout=15)
        return completed.stdout.strip() or "UNKNOWN"
    except Exception:  # pragma: no cover - git is absent only on exotic checkouts
        return "UNKNOWN"


def _design_context(pre: Dict[str, Any]) -> Dict[str, Any]:
    """Case identity for the ledger start line (A5 B21).

    x12/design_hash come from the plan when the case is a design point; a P0R tooling
    smoke has no design vector, so the fields stay null and the geometry source says so.
    """
    plan = pre.get("plan") or {}
    geometry = plan.get("geometry") or {}
    case_inputs = pre.get("case_inputs") or {}
    design = plan.get("design") or {}
    mesh = case_inputs.get("mesh") or {}
    if mesh.get("rebuild_strategy"):
        source = "REBUILT_FROM_X12_VSPGEOM"
    elif geometry.get("geometry_source"):
        source = str(geometry["geometry_source"])
    else:
        source = "PLAN_GEOMETRY_AS_PREPARED"
    return {
        "batch_id": plan.get("batch_id") or plan.get("run_id"),
        "design_hash": design.get("design_hash") or geometry.get("design_hash")
                       or case_inputs.get("design_hash"),
        "x12": design.get("x12") or geometry.get("x12"),
        "geometry_source": source,
        "solver_version": (plan.get("solver") or {}).get("version_banner"),
    }


def _write_dry_run_record(run_dir: Path, result: Dict[str, Any], plan: Dict[str, Any],
                          pre: Dict[str, Any]) -> Path:
    """A5 B22: a dry-run leaves an auditable record instead of only a chat message."""
    payload = dict(result)
    payload.update({
        "schema": "dreal001.dry_run.v1",
        "created_utc": ledger.iso_utc(),
        "code_sha": _code_sha(),
        "run_id": plan.get("run_id"),
        "batch_id": plan.get("batch_id") or plan.get("run_id"),
        "window": pre.get("window"),
        "physical_solver_starts": 0,
        "internal_solver_cases": 0,
        "note": "preflight-only dry run: no process spawned, no ledger start line",
    })
    path = run_dir / "dry_run.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
                    encoding="utf-8")
    return path


def run_case(plan_path: str | Path, approval_path: str | Path, attempt_id: str,
             dry_run: bool = False, timeout_s: Optional[float] = None,
             omp_override: Optional[int] = None) -> Dict[str, Any]:
    pre = prepare_case(plan_path, approval_path, attempt_id)
    plan = pre["plan"]
    argv = list(pre["argv"])
    if omp_override is not None and "-omp" in argv:
        position = argv.index("-omp") + 1
        if position < len(argv):
            argv[position] = str(int(omp_override))
    run_dir = Path(plan_path).resolve().parent
    case_id = str(plan.get("case_id"))
    result: Dict[str, Any] = {
        "schema": CASE_RESULT_SCHEMA,
        "plan_sha256": pre["plan_sha256"], "approval_sha256": pre["approval_sha256"],
        "window": pre["window"], "argv": argv, "cwd": str(pre["cwd"]),
        "attempt_id": attempt_id, "dry_run": bool(dry_run),
        "preflight_ok": True,
    }
    if dry_run:
        result.update({"status": "DRY_RUN_OK", "physical_solver_starts": 0})
        result["dry_run_file"] = str(_write_dry_run_record(run_dir, result, plan, pre))
        return result
    ledger_obj = ledger.SolverLedger(run_dir, str(plan.get("run_id")), str(plan.get("task_id")))
    max_starts = int((plan.get("budget") or {}).get("physical_solver_starts_max", 1))
    context = _design_context(pre)
    try:
        start_record = ledger_obj.begin_attempt(
            attempt_id=attempt_id, case_id=case_id, argv=argv, cwd=pre["cwd"],
            approval=pre["approval"], plan_sha256=pre["plan_sha256"],
            approval_sha256=pre["approval_sha256"],
            input_hashes=pre["geometry_files"], exe_sha256=pre["exe_sha256"],
            max_starts=max_starts,
            extra={"basename": pre["basename"], "solver_config_sha256": pre["solver_config_sha256"],
                   "purpose": plan.get("purpose")},
            batch_id=context["batch_id"], design_hash=context["design_hash"],
            x12=context["x12"], geometry_source=context["geometry_source"],
            solver_version=context["solver_version"],
            stdout_path=str(pre["cwd"] / "logs" / (attempt_id + ".stdout.log")),
            stderr_path=str(pre["cwd"] / "logs" / (attempt_id + ".stderr.log")),
        )
    except ledger.AccountingError as exc:
        result.update({"status": "REFUSED", "refusal_reason": str(exc),
                       "physical_solver_starts": 0})
        return result
    spawned = spawn_case(pre, attempt_id, dry_run=False, timeout_s=timeout_s,
                         omp_override=omp_override)
    process = spawned["process"]
    internal = spawned["internal"]
    evaluation = spawned["evaluation"]
    ledger_obj.end_attempt(attempt_id, process["exit_code"], spawned["status"], process["wall_s"],
                           outputs=spawned["outputs"], note=plan.get("purpose"),
                           internal_solver_cases=internal["count"],
                           internal_case_breakdown=internal,
                           unique_flow_conditions=internal.get("unique_flow_conditions"),
                           case_id=case_id)
    ledger_obj.write_evaluation(evaluation)
    case_result_path = pre["cwd"] / "case_result.json"
    case_result_path.write_text(json.dumps(
        {"schema": CASE_RESULT_SCHEMA, "attempt": start_record, "process": process,
         "outputs": spawned["outputs"], "polar": spawned["polar"], "evaluation": evaluation,
         "physical_solver_starts": 1}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result.update({
        "status": spawned["status"],
        "physical_solver_starts": 1,
        "exit_code": process["exit_code"], "timed_out": process["timed_out"],
        "wall_s": process["wall_s"],
        "polar_rows": (spawned["polar"] or {}).get("row_count"),
        "polar_format": (spawned["polar"] or {}).get("format_version"),
        "internal_solver_cases": internal["count"],
        "unique_flow_conditions": internal.get("unique_flow_conditions"),
        "accounting_flags": spawned["accounting_flags"],
        "lift_match": evaluation["lift_match"],
        "outputs": spawned["outputs"],
        "case_result": str(case_result_path),
        "ledger_starts_total": ledger_obj.count_starts(),
        "stdout_log": process["stdout_path"], "stderr_log": process["stderr_path"],
    })
    return result

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="One real VSPAERO start with accounting (D-REAL-001 A1)")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run one approved solver case")
    run.add_argument("--plan", required=True)
    run.add_argument("--approval", required=True)
    run.add_argument("--attempt-id", required=True)
    run.add_argument("--dry-run", action="store_true", help="preflight only; no process, no ledger line")
    run.add_argument("--timeout", type=float, default=None)
    run.add_argument("--omp", type=int, default=None)
    sub.add_parser("summary", help="print ledger summary")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "summary":
        print(json.dumps({"usage": "pass --plan to locate run dir"}, indent=2))
        return 0
    try:
        result = run_case(args.plan, args.approval, args.attempt_id, dry_run=args.dry_run,
                          timeout_s=args.timeout, omp_override=args.omp)
    except PreflightError as exc:
        print(json.dumps({"status": "PREFLIGHT_REFUSED", "reason": str(exc)}, indent=2))
        return 2
    printable = dict(result)
    printable.pop("outputs", None)
    print(json.dumps(printable, indent=2, default=str))
    if result["status"] == "DRY_RUN_OK":
        return 0
    return 0 if result.get("status") == "SOLVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
