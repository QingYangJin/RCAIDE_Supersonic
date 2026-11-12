"""P2A-CAL 标定批驱动器（v1.1，执行码绑定 + 异常闭合 + 预算/S6 门控）。

目的（Lead m05835/m06063）：同一 12D 设计在两个 mesh family 上各启动 3 次真实 VSPAERO，
量化"同设计跨族 CDi 相对差"，为未来 P2a 族政策提供证据。不做 optimizer 推断。
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import ledger, openvsp_model, solver_runner
from .mesh_identity import family_label
from .task_spec import TASK_SPEC

CAL_PLAN_SCHEMA = "dreal001.p2a_cal_plan.v1"
CAL_CASE_PLAN_SCHEMA = "dreal001.solver_case_plan.v1"
CAL_CASE_APPROVAL_SCHEMA = "dreal001.solver_case_approval.v1"
CAL_RESULT_SCHEMA = "dreal001.p2a_cal_result.v1"
CAL_SUMMARY_SCHEMA = "dreal001.p2a_cal_batch_summary.v1"
BATCH_ID = "DREAL001-P2-20261111-04"
RUN_ID = "DREAL001-P2CAL-20261111-02"
MAX_STARTS = 12
MAX_INTERNAL_CASES = 84
MAX_REFINE_STARTS = 0
TIMEOUT_SECONDS = 60
OMP_THREADS = 1
CONCURRENCY = 1
MAX_MESH_ATTEMPTS = 40
BASENAME = "concorde_baseline"
WINDOW_START_UTC = "2026-11-10T21:00:00Z"
WINDOW_END_UTC = "2026-11-11T01:00:00Z"
WINDOW_TOKEN = "WINDOW_OK-P2CAL-20261110T2100Z-20261111T0100Z"
SAME_FAMILY_TOLERANCE = 0.005
TARGET_FAMILIES = ((483, 418), (543, 472))
FAMILY_LABELS = ("483x418", "543x472")
MAX_BATCH_WALL_SECONDS = 7200
MIN_FREE_DISK_BYTES = 50 * 1024 ** 3
EXECUTOR_RELPATH = "research/concorde_metaopt/dreal001/geometry/p2a_cal.py"
PROBES_RELPATH = "research/concorde_metaopt/dreal001/geometry/templates/production/probes_feasibility.json"
P1C_RELPATH = "research/concorde_metaopt/dreal001/geometry/runs/DREAL001-P1C-20261110-01/plan.json"

TASK_SPEC_BLOCK = {
    "path": "configs/dreal001_task_fixed_cruise_REAL.json",
    "raw_sha256": "0aa64eb25d9fd2ed939f7c9f2bdfa9df4b32ee19cbfd9310fbaae56d4976cf27",
    "canonical_sha256": "dca981e2f1c4ce28fb3d4e6feaeb26170c6e58b4cfad6fb8e6ae7ee05c7ca874",
    "raw_bytes": 6025,
    "hash_scope": "raw = file bytes; canonical = sha256(json.dumps(TASK_SPEC.to_dict(), "
                 "sort_keys=True, separators=(',', ':'))). The scopes are not interchangeable.",
}
FROZEN_DESIGN_SPACE_BLOCK = {
    "config_path": "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml",
    "config_sha256": "8b29d1e3833edc2af248d68cd6b7b4c94ebf775f25c86d80062a3850765a499e",
    "freeze_artifact_path": "research/concorde_metaopt/dreal001/geometry/design_space_freeze.json",
    "freeze_artifact_sha256": "fe7e48eba6a70eb76b0b139b1004f775830da68bd5d003604d686e59656e8373",
    "frozen": True,
    "bounds_status": "frozen_for_dreal001_20261110",
}
GEOMETRY_CG_M = 28.287395109126685
SOLVER_CONFIG_CONTRACT = {
    "exe_sha256": "db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad",
    "argv": ["vspaero.exe", "-omp", "1", "concorde_baseline"],
    "timeout_seconds": 60,
    "alpha_list_deg": (-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0),
    "mach_list": (2.02,),
    "tessellation": {"Tess_U": 12.0, "Tess_W": 25.0},
    "num_wake_nodes": 8,
    "geometry_set": "thin",
    "omp_threads": 1,
    "concurrency": 1,
}


class CalRefusal(RuntimeError):
    """Raised when plan/approval/executor/disk contract refuses to start."""


def sha256_bytes(raw: bytes) -> str:
    return ledger.sha256_bytes(raw)


def sha256_file(path: Path) -> str:
    return ledger.sha256_file(path)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def executor_blob_sha256() -> str:
    return sha256_file(Path(__file__))


def verify_executor_binding(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Fail-closed: the on-disk executor bytes must equal plan.executor.blob_sha256."""
    block = plan.get("executor") or {}
    expected = block.get("blob_sha256") or plan.get("executor_sha256")
    if plan.get("executor_sha256") and expected and plan.get("executor_sha256") != expected:
        raise CalRefusal("plan.executor_sha256 != plan.executor.blob_sha256")
    if not expected:
        raise CalRefusal("plan.executor.blob_sha256 is missing: execution code is not bound")
    actual = executor_blob_sha256()
    if actual != expected:
        raise CalRefusal("executor blob sha256 %s != plan %s (code changed after planning)"
                         % (actual, expected))
    return {"path": block.get("path"), "blob_sha256": actual,
            "execution_code_sha": block.get("execution_code_sha")}


def solver_config_hash(contract: Optional[Dict[str, Any]] = None) -> str:
    payload = contract if contract is not None else SOLVER_CONFIG_CONTRACT
    return sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_bytes().decode("utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def _short_tag(case_id: str) -> str:
    tag = case_id.replace("P1-07-", "")
    return tag.replace("-plus", "p").replace("-minus", "m")


def case_id_for(design_tag: str, family: Sequence[int], repeat: int) -> str:
    return "CAL-%s-f%dx%d-r%d" % (_short_tag(design_tag), int(family[0]), int(family[1]), int(repeat))


def select_calibration_designs(probes_path: Path, p1c_plan: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Pre-declared rule: among 14 feasibility probes, keep those whose samples[] contain BOTH
    483x418 and 543x472, sort by design_hash lexicographically ascending, take the first two."""
    probes = _read_json(probes_path).get("probes") or []
    candidates: List[Dict[str, Any]] = []
    for probe in probes:
        families = {str(sample.get("mesh_family")) for sample in (probe.get("samples") or [])}
        if "483x418" in families and "543x472" in families:
            candidates.append({"design_tag": str(probe["case_id"]),
                               "design_hash": str(probe["design_hash"]),
                               "frequency": probe.get("frequency") or {},
                               "sample_count": probe.get("sample_count")})
    candidates.sort(key=lambda item: item["design_hash"])
    chosen = candidates[:2]
    if len(chosen) < 2:
        raise CalRefusal("fewer than two candidate designs observed both families")
    p1c = {str(case["case_id"]): case for case in (_read_json(p1c_plan).get("case_matrix") or [])}
    for item in chosen:
        case = p1c.get(item["design_tag"])
        if not case or len(case.get("x12") or []) != 12:
            raise CalRefusal("P1C plan has no complete x12 for %s" % item["design_tag"])
        item["x12"] = [float(value) for value in case["x12"]]
        item["design"] = case.get("design")
    return chosen, candidates


def build_plan(run_dir: Path, design_space_path: Path, p1c_plan: Path,
               prereg_path: Path, *, execution_code_sha: Optional[str] = None) -> Dict[str, Any]:
    probes_path = repo_root() / PROBES_RELPATH
    designs, candidates = select_calibration_designs(probes_path, p1c_plan)
    cases: List[Dict[str, Any]] = []
    for record in designs:
        for family in TARGET_FAMILIES:
            label = family_label(family)
            for repeat in (1, 2, 3):
                cases.append({
                    "case_id": case_id_for(record["design_tag"], family, repeat),
                    "design": record.get("design"),
                    "design_hash": record["design_hash"],
                    "design_tag": record["design_tag"],
                    "x12": record["x12"],
                    "target_family": label,
                    "target_mesh_family": [int(family[0]), int(family[1])],
                    "repeat": repeat,
                    "starts": 1,
                    "expected_internal_cases": 7,
                    "internal_case_breakdown": {"mach_list": list(SOLVER_CONFIG_CONTRACT["mach_list"]),
                                                "alpha_list_deg": list(SOLVER_CONFIG_CONTRACT["alpha_list_deg"]),
                                                "beta_list_deg": [0.0]},
                    "max_mesh_attempts": MAX_MESH_ATTEMPTS,
                    "timeout_seconds": TIMEOUT_SECONDS,
                    "omp_threads": OMP_THREADS,
                    "config_id": "P2CAL-thin-12x25",
                })
    starts = sum(int(case["starts"]) for case in cases)
    internal = sum(int(case["expected_internal_cases"]) for case in cases)
    if starts != MAX_STARTS or internal != MAX_INTERNAL_CASES:
        raise CalRefusal("case matrix does not match the approved budget: %d/%d" % (starts, internal))
    plan: Dict[str, Any] = {
        "schema": CAL_PLAN_SCHEMA, "plan_version": "v1.2",
        "run_id": RUN_ID, "batch_id": BATCH_ID, "canonical_batch_id": BATCH_ID,
        "task_id": TASK_SPEC.task_id,
        "purpose": "CALIBRATION_ONLY: quantify same-design cross-family CDi relative difference; "
                   "no optimizer inference, no fuel-burn conclusion",
        "requested_by": "a1-aviation-f (A1)",
        "authority": "Lead m05835/m06063 (P2A-CAL 12 starts, W05+W10 lexicographic rule) + "
                     "A5 m05919/m06007 (G-P2CAL-PRE) + A2 audit blockers",
        "status": "PENDING_APPROVAL",
        "approval_state": {"status": "NOT_APPROVED", "approved_by": None,
                           "approved_at_utc": None, "window_token": None},
        "case_count": len(cases),
        "design_selection": {
            "rule": "among the 14 feasibility probes, keep designs whose samples[] contain BOTH "
                    "483x418 and 543x472; sort by design_hash lexicographically ascending; take first two",
            "candidates": candidates, "chosen": [item["design_hash"] for item in designs],
            "evidence": "zero-physical probes_feasibility.json samples[].mesh_family",
            "disclosure": "selection is independent of optimizer performance; no performance bias",
        },
        "designs": [{"design_tag": item["design_tag"], "design_hash": item["design_hash"],
                     "x12": item["x12"]} for item in designs],
        "families": [{"role": "A", "family": FAMILY_LABELS[0]},
                     {"role": "B", "family": FAMILY_LABELS[1]}],
        "protocol": {
            "geometry": "thin", "tess_u": 12.0, "tess_w": 25.0,
            "alpha_list_deg": list(SOLVER_CONFIG_CONTRACT["alpha_list_deg"]),
            "mach_list": list(SOLVER_CONFIG_CONTRACT["mach_list"]), "num_wake_nodes": 8,
            "rebuild_strategy": "direct rebuild loop (<=40 zero-physical attempts) until actual family == target",
            "max_target_family_attempts": MAX_MESH_ATTEMPTS,
            "rebuild_budget_rationale": "observed per-family frequency is 1/3..2/3; 12 attempts do not "
                                        "establish reachability, 40 attempts at 0.27-0.34 s/attempt cost "
                                        "<=13.6 s per cell worst case",
            "unreachable_policy": "record CAL_FAMILY_UNREACHABLE with 0 start, do not consume budget, continue",
            "incomplete_policy": "any of the 12 cells missing -> batch verdict CAL_INCOMPLETE; only "
                                 "descriptive reporting of usable cells; no POOLABLE_CANDIDATE; no rerun; "
                                 "no family swap",
            "starts_per_case": 1, "timeout_seconds": TIMEOUT_SECONDS,
            "retry_policy": "no retry: any non-SOLVED settles the batch (S1)",
            "solver_argv": ["vspaero.exe", "-omp", "1", BASENAME],
            "forbidden_flags": ["-fs", "-mach", "-alpha", "-beta"],
        },
        "solver": {"path": r"D:\OpenVSP-3.55.0\OpenVSP-3.55.0-win64\vspaero.exe",
                   "sha256": "db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad",
                   "version": "VSPAERO v7.2.2 (compiled 2026-10-12)",
                   "parallelism": {"processes": 1, "threads_per_process": OMP_THREADS,
                                   "concurrency": CONCURRENCY, "omp_threads": OMP_THREADS},
                   "timeout_s": TIMEOUT_SECONDS},
        "executor": {"path": EXECUTOR_RELPATH, "blob_sha256": executor_blob_sha256(),
                     "execution_code_sha": execution_code_sha or "PENDING_COMMIT",
                     "binding_note": "dry_run and the first real start both recompute this blob SHA "
                                     "and fail closed on mismatch"},
        "executor_sha256": executor_blob_sha256(),
        "executor_blobs": {EXECUTOR_RELPATH: executor_blob_sha256()},
        "executor_files": {EXECUTOR_RELPATH: {"sha256": executor_blob_sha256(),
                                              "bytes": Path(__file__).stat().st_size}},
        "budget": {"expected_starts": MAX_STARTS, "max_starts": MAX_STARTS,
                   "expected_internal_cases": MAX_INTERNAL_CASES,
                   "max_internal_cases": MAX_INTERNAL_CASES, "max_refine_starts": MAX_REFINE_STARTS},
        "retry_policy": {"automatic_numeric_retry": False, "infra_retries_allowed": 0,
                         "timeout_retry": "none: S1 fail-closed on the first non-SOLVED case"},
        "concurrency": CONCURRENCY, "timeout_seconds_per_case": TIMEOUT_SECONDS,
        "task_spec": dict(TASK_SPEC_BLOCK),
        "frozen_design_space": dict(FROZEN_DESIGN_SPACE_BLOCK),
        "solver_config_hash": solver_config_hash(),
        "reference_quantities": {"sref_m2": None,
                                 "sref_policy": "Sref comes from each design; never a global value",
                                 "cref_m": TASK_SPEC.cref_m, "bref_m": TASK_SPEC.bref_m,
                                 "xcg_m": TASK_SPEC.xcg_m,
                                 "wing_ac_x_m": 16.821978259514246,
                                 "geometry_cg_m": GEOMETRY_CG_M,
                                 "reference_frame": TASK_SPEC.reference_frame,
                                 "q_pa": TASK_SPEC.q_pa, "l_ref_n": TASK_SPEC.l_ref_n,
                                 "note": "X_cg is the WING AC, never the geometric CG 28.287395 m"},
        "calibration": {
            "definition": "per design: r_i = (CDi_B_i - CDi_A_i) / CDi_A_i at matched lift "
                          "(CL_target = L_ref / (q * Sref)) for repeat i = 1..3",
            "statistics": "mean(r) = mean of the 3 r_i; range(r) = max(r_i) - min(r_i)",
            "decision_rule": {
                "r_i_definition": "r_i = (CDi_B_i - CDi_A_i) / CDi_A_i at matched lift, i = 1..3",
                "statistics": "mean(r) = mean of the 3 r_i; range(r) = max(r_i) - min(r_i)",
                "poolable_candidate_if": "abs(mean(r)) <= 0.005 AND range(r) <= 0.005",
                "root_cause_required_if": "abs(mean(r)) > 0.005 OR range(r) > 0.005",
                "incomplete_if": "any of the 12 cells missing -> batch verdict CAL_INCOMPLETE; "
                                 "no POOLABLE_CANDIDATE",
                "note": "identical field names/thresholds/formula to the preregistration",
            },
            "prohibited_conclusions": ["optimizer ranking", "fuel burn", "physical drag validation",
                                       "12D sensitivity closure"],
        },
        "case_matrix": cases,
        "stop_conditions": [
            {"id": "S1", "rule": "any case settles as non-SOLVED (TIMEOUT/EXIT/NO_POLAR) -> stop, no retry"},
            {"id": "S2", "rule": "negative CDi with |CL| > 0.05 -> stop"},
            {"id": "S5", "rule": "starts > 12 or internal cases > 84 -> stop"},
            {"id": "S6", "rule": "batch wall > 2 h or free disk < 50 GB -> stop with stop_report"},
            {"id": "S7", "rule": "approved window closed -> stop (fail-closed)"},
            {"id": "S8", "rule": "infrastructure exception -> end line + stop_report, never an unpaired start"},
        ],
        "window": {"requested_start_utc": WINDOW_START_UTC, "requested_end_utc": WINDOW_END_UTC,
                   "token": WINDOW_TOKEN, "note": "approval.window is authoritative"},
        "approval": {"approval_owner": "lead", "approval_file": "approval.json",
                     "max_starts": MAX_STARTS, "status": "NOT_APPROVED"},
        "preregistration": {"path": None, "sha256": None, "version": "v1.2"},
        "disclosures": [
            "P2a 384-start matrix is NOT_RUN: mesh family is not deterministic; root-cause probes show "
            "family flips come from the x12->model build path.",
            "CAL measures only the same-design cross-family CDi difference; it cannot repair mesh "
            "non-determinism and must not be used as an optimizer result.",
            "P1R is INCOMPLETE_S1_STOPPED_WITH_PROTOCOL_DEVIATION; P1C is "
            "SOLVER_INTERNAL_PASS_CONTINUATION (CONTINUATION_BATCH_ONLY); P1 as a whole is unsigned; "
            "P2 is not authorized; 12D_ACTIVE remains NOT_VALIDATED.",
            "This plan supersedes the DREAL001-P2CAL-20261111-01 package (plan "
            "6629ee438f787269f9203d289c41fb5b5a5a7755af32c812c14aa15a6ce900f4, approval "
            "6383a00087c6755f35a0a74701bb0a3d932792e666c8c3e59156689463035a42, Lead-signed "
            "2026-11-10T18:41:19Z) which was superseded with 0 physical starts after the A2 audit "
            "found blockers and a design-selection factual error.",
        ],
        "physical_solver_starts": 0,
        "created_utc": ledger.iso_utc(),
    }
    exe = Path(plan["solver"]["path"])
    if exe.is_file():
        plan["solver"]["sha256"] = sha256_file(exe)
    if prereg_path.is_file():
        raw = prereg_path.read_bytes()
        plan["preregistration"] = {"path": str(prereg_path), "sha256": sha256_bytes(raw),
                                   "version": "v1.2", "bytes": len(raw)}
    _write_json(run_dir / "plan.json", plan)
    return plan


def load_plan(run_dir: Path) -> Tuple[Dict[str, Any], str, int]:
    path = run_dir / "plan.json"
    if not path.is_file():
        raise CalRefusal("plan.json missing: %s" % path)
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), sha256_bytes(raw), len(raw)


def effective_caps(plan: Dict[str, Any], approval: Dict[str, Any]) -> Dict[str, int]:
    budget = plan.get("budget") or {}
    max_starts = int(budget.get("max_starts") or 0)
    if approval.get("max_starts") is not None:
        max_starts = min(max_starts, int(approval["max_starts"]))
    max_internal = int(budget.get("max_internal_cases") or 0)
    if approval.get("max_internal_cases") is not None:
        max_internal = min(max_internal, int(approval["max_internal_cases"]))
    return {"max_starts": max_starts, "max_internal_cases": max_internal,
            "max_refine_starts": int(budget.get("max_refine_starts") or 0)}


def verify_approval(plan: Dict[str, Any], plan_sha256: str,
                    approval: Dict[str, Any], approval_sha256: str) -> Dict[str, Any]:
    if approval.get("approved") is not True:
        raise CalRefusal("approval.json is not approved (approved=%r)" % approval.get("approved"))
    token = ledger.approval_window_token(approval)
    if not token:
        raise CalRefusal("approval.json carries no window_token (top-level or window.token)")
    if approval.get("plan_sha256") != plan_sha256:
        raise CalRefusal("approval.plan_sha256 %s != plan bytes sha256 %s"
                         % (approval.get("plan_sha256"), plan_sha256))
    if approval.get("run_id") not in (None, plan.get("run_id")):
        raise CalRefusal("approval.run_id %r != plan.run_id %r"
                         % (approval.get("run_id"), plan.get("run_id")))
    status = ledger.window_status(approval)
    if not status["open"]:
        raise CalRefusal("approved window is not open: %s" % status["reason"])
    caps = effective_caps(plan, approval)
    if caps["max_starts"] < 1:
        raise CalRefusal("effective max_starts is 0")
    return {"approval_sha256": approval_sha256, "window": status, "window_token": token, **caps}


def _geometry_for(x12: Sequence[float]):
    geometry, _space = openvsp_model._geometry_from_design_vector([float(value) for value in x12])
    return geometry


def build_case_inputs(case: Dict[str, Any], case_dir: Path) -> Dict[str, Any]:
    geometry = _geometry_for(case["x12"])
    target = tuple(int(value) for value in case["target_mesh_family"])
    target_label = family_label(target)
    attempts: List[Dict[str, Any]] = []
    last: Dict[str, Any] = {}
    for attempt in range(1, int(case.get("max_mesh_attempts") or MAX_MESH_ATTEMPTS) + 1):
        built = openvsp_model.prepare_case(
            geometry, case_dir, BASENAME, geometry_set="thin",
            alphas_deg=list(SOLVER_CONFIG_CONTRACT["alpha_list_deg"]),
            tess_u=12.0, tess_w=25.0, openvsp_root=openvsp_model.DEFAULT_OPENVSP_ROOT,
            n_wake_nodes=8, write_vsp3=True,
            mach_values=list(SOLVER_CONFIG_CONTRACT["mach_list"]), rebuild_strategy="direct")
        mesh = built.get("mesh") or {}
        observed = str(mesh.get("mesh_family"))
        attempts.append({"attempt": attempt, "family": observed,
                         "nodes": mesh.get("nodes"), "elements": mesh.get("elements"),
                         "canonical_mesh_sha256": mesh.get("canonical_mesh_sha256"),
                         "vspgeom_sha256": (built.get("artifacts") or {}).get("vspgeom", {}).get("sha256")})
        last = built
        if observed == target_label:
            return {"status": "MATCHED", "attempts": attempts, "mesh": mesh, "built": built,
                    "target_family": target_label, "rebuild_attempts": attempt}
    return {"status": "CAL_FAMILY_UNREACHABLE", "attempts": attempts, "target_family": target_label,
            "rebuild_attempts": len(attempts),
            "observed_final": attempts[-1]["family"] if attempts else None, "built": last}


def build_case_plan(case: Dict[str, Any], plan: Dict[str, Any], case_dir: Path,
                    plan_sha256: str, case_inputs: Dict[str, Any]) -> Dict[str, Any]:
    mesh = case_inputs.get("mesh") or {}
    artifacts = (case_inputs.get("built") or {}).get("artifacts") or {}
    files = {}
    for name in ("vspgeom", "vkey", "vspaero", "csf"):
        entry = artifacts.get(name) or {}
        files[name] = {"path": entry.get("path"), "bytes": entry.get("bytes"),
                       "sha256": entry.get("sha256")}
    solver = plan.get("solver") or {}
    sref = float((case_inputs.get("built") or {}).get("sref_m2") or 0.0)
    return {
        "schema": CAL_CASE_PLAN_SCHEMA, "batch_plan_sha256": plan_sha256,
        "batch_run_id": plan.get("run_id"), "run_id": plan.get("run_id"),
        "case_id": case["case_id"], "task_id": TASK_SPEC.task_id,
        "purpose": "P2A-CAL same-design cross-family CDi calibration",
        "design": case.get("design"), "design_hash": case.get("design_hash"),
        "x12": list(case.get("x12") or []),
        "geometry": {
            "basename": BASENAME, "geometry_source": "REBUILT_FROM_X12_DIRECT_UNTIL_TARGET_FAMILY",
            "geometry_sha256": files.get("vspgeom", {}).get("sha256"),
            "mesh": mesh, "mesh_family_target": case.get("target_family"),
            "mesh_family_actual": (mesh or {}).get("mesh_family"),
            "rebuild_attempts": case_inputs.get("rebuild_attempts"),
            "sref_m2": sref, "geometry_set": "thin",
            "alpha_list_deg": list(SOLVER_CONFIG_CONTRACT["alpha_list_deg"]),
            "mach_list": list(SOLVER_CONFIG_CONTRACT["mach_list"]),
            "tessellation": {"Tess_U": 12.0, "Tess_W": 25.0}, "num_wake_nodes": 8,
            "files": files,
        },
        "command": {"argv": [str(solver.get("path")), "-omp", str(OMP_THREADS), BASENAME],
                    "solver_argv": ["vspaero.exe", "-omp", str(OMP_THREADS), BASENAME],
                    "forbidden_flags": ["-fs", "-mach", "-alpha", "-beta"]},
        "solver": {"path": solver.get("path"), "sha256": solver.get("sha256"),
                   "version_banner": solver.get("version", "VSPAERO v7.2.2"),
                   "cwd": str(case_dir.resolve()), "omp_threads": OMP_THREADS,
                   "timeout_s": TIMEOUT_SECONDS},
        "budget": {"physical_solver_starts_max": 1, "expected_internal_cases": 7,
                   "max_internal_cases": 7, "batch_max_starts": MAX_STARTS},
        "target_family": case.get("target_family"), "repeat": case.get("repeat"),
        "reference_quantities": {"sref_m2": sref, "cref_m": TASK_SPEC.cref_m,
                                 "bref_m": TASK_SPEC.bref_m, "xcg_m": TASK_SPEC.xcg_m,
                                 "reference_frame": TASK_SPEC.reference_frame,
                                 "q_pa": TASK_SPEC.q_pa, "l_ref_n": TASK_SPEC.l_ref_n,
                                 "note": "X_cg is the WING AC 16.821978 m, not the geometric CG"},
        "created_utc": ledger.iso_utc(), "physical_solver_starts": 0,
    }


def build_case_approval(case: Dict[str, Any], batch_approval: Dict[str, Any],
                        plan_sha256: str, case_plan_sha256: str) -> Dict[str, Any]:
    window = batch_approval.get("window") or {}
    token = ledger.approval_window_token(batch_approval)
    return {
        "schema": CAL_CASE_APPROVAL_SCHEMA, "derived_from_batch_approval": True,
        "derived_note": "derived mechanically from the approved batch approval; never widens "
                        "the case matrix, budget or window",
        "approved": True, "approved_by": batch_approval.get("approved_by"),
        "run_id": batch_approval.get("run_id") or RUN_ID, "case_id": case["case_id"],
        "plan_sha256": case_plan_sha256, "batch_plan_sha256": plan_sha256,
        "window_token": token,
        "window": {"start_utc": window.get("start_utc"), "end_utc": window.get("end_utc"),
                   "token": token},
        "max_starts": 1, "max_internal_cases": 7, "physical_solver_starts": 0,
    }


def _append_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def evaluate_stop_conditions(case_id: str, spawned: Dict[str, Any], starts: int,
                             caps: Dict[str, int], internal_total: int) -> List[Dict[str, str]]:
    hits: List[Dict[str, str]] = []
    status = str(spawned.get("status"))
    if status != "SOLVED":
        hits.append({"condition": "S1", "detail": "case %s settled as %s" % (case_id, status)})
    for row in ((spawned.get("polar") or {}).get("rows") or []):
        cdi = row.get("CDi")
        cl = row.get("CLtot")
        try:
            if cdi is not None and float(cdi) < -1e-6 and abs(float(cl)) > 0.05:
                hits.append({"condition": "S2", "detail": "negative CDi %r in %s" % (cdi, case_id)})
                break
        except (TypeError, ValueError):
            continue
    if starts > caps["max_starts"]:
        hits.append({"condition": "S5", "detail": "starts %d > max %d" % (starts, caps["max_starts"])})
    if internal_total > caps["max_internal_cases"]:
        hits.append({"condition": "S5", "detail": "internal %d > max %d"
                                                  % (internal_total, caps["max_internal_cases"])})
    return hits


def dry_run(run_dir: Path) -> Dict[str, Any]:
    """Pre/post-approval dry-run: binds executor+plan bytes, writes an auditable record."""
    plan, plan_sha, plan_bytes = load_plan(run_dir)
    executor = verify_executor_binding(plan)
    cases = plan.get("case_matrix") or []
    report: Dict[str, Any] = {
        "schema": "dreal001.dry_run.v1", "status": "DRY_RUN",
        "run_id": plan.get("run_id"), "batch_id": plan.get("batch_id"),
        "plan_sha256": plan_sha, "plan_bytes": plan_bytes,
        "executor": executor, "executor_sha256": executor["blob_sha256"],
        "executor_blobs": {EXECUTOR_RELPATH: executor["blob_sha256"]},
        "per_case": [{"case_id": case["case_id"], "design_hash": case.get("design_hash"),
                      "target_family": case.get("target_family"), "repeat": case.get("repeat"),
                      "starts": 1, "expected_internal_cases": 7,
                      "max_mesh_attempts": case.get("max_mesh_attempts")} for case in cases],
        "case_count": len(cases),
        "case_order": [case["case_id"] for case in cases],
        "cases_planned": sum(int(case.get("starts") or 1) for case in cases),
        "planned_starts": sum(int(case.get("starts") or 1) for case in cases),
        "planned_internal_cases": sum(int(case.get("expected_internal_cases") or 0) for case in cases),
        "approval_sha256": None,
        "physical_solver_starts": 0, "physical_call_count": 0,
        "created_utc": ledger.iso_utc(),
        "created_by": "p2a_cal.dry_run",
        "note": "no case directory, no ledger line, no solver start",
    }
    approval_path = run_dir / "approval.json"
    if approval_path.is_file():
        raw = approval_path.read_bytes()
        approval = json.loads(raw.decode("utf-8"))
        report["approval_sha256"] = sha256_bytes(raw)
        try:
            verified = {"state": "VALID",
                        **verify_approval(plan, plan_sha, approval, sha256_bytes(raw))}
            report["approval"] = verified
            approved_at = str(approval.get("approved_at_utc") or "")
            created = str(report["created_utc"])
            if approved_at and created < approved_at:
                report["created_utc_check"] = "FAILED: dry_run.created_utc < approval.approved_at_utc"
            else:
                report["created_utc_check"] = "PASS"
        except CalRefusal as exc:
            report["approval"] = {"state": "REFUSED", "reason": str(exc)}
    else:
        report["approval"] = "ABSENT_OR_NOT_CHECKED_IN_DRY_RUN"
    _write_json(run_dir / "dry_run.json", report)
    return report


def _code_sha() -> str:
    try:
        import subprocess
        completed = subprocess.run(["git", "-C", str(repo_root()), "rev-parse", "HEAD"],
                                   capture_output=True, text=True, timeout=15)
        return completed.stdout.strip() or "UNKNOWN"
    except Exception:  # pragma: no cover
        return "UNKNOWN"


def _default_spawner(pre: Dict[str, Any], attempt_id: str, timeout_s: float) -> Dict[str, Any]:
    return solver_runner.spawn_case(pre, attempt_id, timeout_s=timeout_s)


def _flatten_condition_rows(case: Dict[str, Any], case_plan: Dict[str, Any],
                            spawned: Dict[str, Any], attempt_id: str) -> List[Dict[str, Any]]:
    from .p1_batch import flatten_conditions
    rows = flatten_conditions({"case_id": case["case_id"], "config_id": case.get("config_id"),
                               "design": case.get("design"), "design_hash": case.get("design_hash")},
                              case_plan, spawned, attempt_id)
    for row in rows:
        row["cal_target_family"] = case.get("target_family")
        row["cal_repeat"] = case.get("repeat")
    return rows


def _stop_report(run_dir: Path, plan_sha: str, hits: Sequence[Dict[str, str]],
                 starts: int, internal_total: int, completed: int, extra: Optional[Dict[str, Any]] = None) -> None:
    payload = {"schema": "dreal001.stop_report.v1", "status": "STOPPED_FAIL_CLOSED",
               "plan_sha256": plan_sha, "conditions": list(hits),
               "completed_cases": completed, "physical_solver_starts": starts,
               "internal_solver_cases": internal_total,
               "created_utc": ledger.iso_utc(),
               "next_action": "human review; remaining cases must not start"}
    if extra:
        payload.update(extra)
    _write_json(run_dir / "stop_report.json", payload)


def _write_summary(run_dir: Path, plan: Dict[str, Any], plan_sha: str,
                   approval_sha: Optional[str], starts: int, internal_total: int,
                   completed: int, unreachable: Sequence[str],
                   stop_hits: Sequence[Dict[str, str]],
                   accounting_flags: Sequence[str],
                   status: Optional[str] = None) -> Dict[str, Any]:
    summary = {
        "schema": CAL_SUMMARY_SCHEMA, "run_id": RUN_ID, "batch_id": plan.get("batch_id"),
        "plan_sha256": plan_sha, "approval_sha256": approval_sha,
        "status": status or ("COMPLETED" if not stop_hits else "STOPPED_FAIL_CLOSED"),
        "physical_solver_starts": int(starts), "internal_solver_cases": int(internal_total),
        "completed_cases": int(completed), "unreachable_cases": list(unreachable),
        "stop_hits": list(stop_hits), "accounting_flags": list(accounting_flags),
        "caps": {"max_starts": MAX_STARTS, "max_internal_cases": MAX_INTERNAL_CASES},
        "executor_blob_sha256": (plan.get("executor") or {}).get("blob_sha256"),
        "physical_validation_status": "NOT_VALIDATED", "fuel_burn_kg": None,
        "evidence_tier": "SOLVER_LOOP_VERIFIED", "created_utc": ledger.iso_utc(),
    }
    _write_json(run_dir / "batch_summary.json", summary)
    return summary


def run_batch(run_dir: Path, *, spawner: Optional[Callable[..., Dict[str, Any]]] = None,
              max_cases: Optional[int] = None,
              clock: Optional[Callable[[], float]] = None,
              disk_free: Optional[Callable[[], int]] = None) -> Dict[str, Any]:
    """Execute the CAL matrix with fail-closed accounting, S1/S5/S6/S7/S8 handling."""
    plan, plan_sha, _plan_bytes = load_plan(run_dir)
    approval_path = run_dir / "approval.json"
    if not approval_path.is_file():
        raise CalRefusal("approval.json missing: P2A-CAL must not start without Lead approval")
    raw = approval_path.read_bytes()
    approval = json.loads(raw.decode("utf-8"))
    approval_sha = sha256_bytes(raw)
    approved = verify_approval(plan, plan_sha, approval, approval_sha)
    verify_executor_binding(plan)
    caps = {"max_starts": approved["max_starts"],
            "max_internal_cases": approved["max_internal_cases"]}
    spawner = spawner or _default_spawner
    clock = clock or time.monotonic
    disk_free = disk_free or (lambda: shutil.disk_usage(run_dir).free)
    solver_ledger = ledger.SolverLedger(run_dir, RUN_ID, TASK_SPEC.task_id)
    if solver_ledger.count_starts():
        raise CalRefusal("run directory already has start lines; reruns are refused")
    evaluations_path = run_dir / "evaluations.jsonl"
    cases = plan.get("case_matrix") or []
    starts = 0
    internal_total = 0
    completed = 0
    unreachable: List[str] = []
    stop_hits: List[Dict[str, str]] = []
    accounting_flags: List[str] = []
    batch_start = clock()

    def finish(status: Optional[str] = None) -> Dict[str, Any]:
        summary = _write_summary(run_dir, plan, plan_sha, approval_sha, starts, internal_total,
                                 completed, unreachable, stop_hits, accounting_flags, status)
        if stop_hits:
            _stop_report(run_dir, plan_sha, stop_hits, starts, internal_total, completed)
        return summary

    for case in (cases[:max_cases] if max_cases else cases):
        case_id = str(case["case_id"])
        window = ledger.window_status(approval)
        if not window["open"]:
            stop_hits.append({"condition": "S7",
                              "detail": "window closed before %s: %s" % (case_id, window["reason"])})
            break
        if clock() - batch_start > MAX_BATCH_WALL_SECONDS:
            stop_hits.append({"condition": "S6", "detail": "batch wall exceeded 2 h before %s" % case_id})
            break
        try:
            free = int(disk_free())
        except Exception:
            free = 0
        if free < MIN_FREE_DISK_BYTES:
            stop_hits.append({"condition": "S6", "detail": "free disk %d < 50 GB before %s"
                                                        % (free, case_id)})
            break
        expected_start_index = starts + 1
        expected_starts_total = int((plan.get("budget") or {}).get("expected_starts") or MAX_STARTS)
        expected_internal = int(case.get("expected_internal_cases") or 7)
        max_internal = int(caps["max_internal_cases"])
        if (expected_start_index > expected_starts_total
                or internal_total + expected_internal > max_internal
                or expected_start_index > caps["max_starts"]):
            accounting_flags.append("ACCOUNTING_MISMATCH_PRE_START")
            stop_hits.append({"condition": "ACCOUNTING_MISMATCH",
                              "detail": "pre-start budget check refused %s: starts %d+1/%d, "
                                        "internal %d+%d/%d"
                                        % (case_id, starts, expected_starts_total,
                                           internal_total, expected_internal, max_internal)})
            break
        case_dir = run_dir / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        try:
            inputs = build_case_inputs(case, case_dir)
        except Exception as exc:  # geometry rebuild failure: no start, record and stop
            stop_hits.append({"condition": "S8", "detail": "case input build failed for %s: %r"
                                                        % (case_id, exc)})
            _write_json(case_dir / "case_result.json", {
                "schema": CAL_RESULT_SCHEMA, "status": "INFRA_EXCEPTION", "case_id": case_id,
                "error": repr(exc), "physical_solver_starts": 0, "physical_call_count": 0,
                "created_utc": ledger.iso_utc()})
            break
        if inputs["status"] == "CAL_FAMILY_UNREACHABLE":
            unreachable.append(case_id)
            _write_json(case_dir / "case_result.json", {
                "schema": CAL_RESULT_SCHEMA, "status": "CAL_FAMILY_UNREACHABLE", "case_id": case_id,
                "target_family": case.get("target_family"),
                "observed_final": inputs.get("observed_final"),
                "rebuild_attempts": inputs.get("rebuild_attempts"),
                "attempts": inputs.get("attempts"),
                "physical_solver_starts": 0, "physical_call_count": 0,
                "note": "target family not reached within %d zero-physical rebuilds; no start, "
                        "no budget consumed, batch continues" % MAX_MESH_ATTEMPTS,
                "created_utc": ledger.iso_utc()})
            continue
        case_plan = build_case_plan(case, plan, case_dir, plan_sha, inputs)
        case_plan_sha = sha256_bytes(_write_json(case_dir / "plan.json", case_plan))
        case_approval = build_case_approval(case, approval, plan_sha, case_plan_sha)
        _write_json(case_dir / "approval.json", case_approval)
        attempt_id = case_id + "-a01"
        started = False
        try:
            pre = solver_runner.prepare_case(case_dir / "plan.json", case_dir / "approval.json",
                                             attempt_id)
            solver_ledger.begin_attempt(
                attempt_id, case_id,
                [str(item) for item in pre["argv"]], str(pre["cwd"]), approval, plan_sha,
                approval_sha, pre.get("geometry_files") or {}, pre.get("exe_sha256") or "",
                caps["max_starts"], batch_id=plan.get("batch_id"),
                design_hash=case.get("design_hash"), x12=case.get("x12"),
                geometry_source="REBUILT_FROM_X12_DIRECT_UNTIL_TARGET_FAMILY",
                solver_version=(plan.get("solver") or {}).get("version"),
                stdout_path=str(pre["cwd"] / "logs" / (attempt_id + ".stdout.log")),
                stderr_path=str(pre["cwd"] / "logs" / (attempt_id + ".stderr.log")))
            started = True
            starts += 1
            spawned = spawner(pre, attempt_id, TIMEOUT_SECONDS)
            internal = int((spawned.get("internal") or {}).get("count") or 0)
            internal_total += internal
            flags = [str(flag) for flag in (spawned.get("accounting_flags") or [])]
            if flags:
                accounting_flags.extend(flags)
                solver_ledger.end_attempt(
                    attempt_id, exit_code=(spawned.get("process") or {}).get("exit_code"),
                    status=str(spawned.get("status")),
                    wall_s=(spawned.get("process") or {}).get("wall_s"),
                    outputs=spawned.get("outputs"), case_id=case_id,
                    internal_solver_cases=internal,
                    internal_case_breakdown=(spawned.get("internal") or {}).get("breakdown"),
                    unique_flow_conditions=(spawned.get("internal") or {}).get("unique_flow_conditions"),
                    note="accounting_flags: %s" % ",".join(flags))
                started = False
                stop_hits.append({"condition": "ACCOUNTING_MISMATCH",
                                  "detail": "solver accounting flags %s in %s" % (flags, case_id)})
                break
            solver_ledger.end_attempt(
                attempt_id, exit_code=(spawned.get("process") or {}).get("exit_code"),
                status=str(spawned.get("status")),
                wall_s=(spawned.get("process") or {}).get("wall_s"),
                outputs=spawned.get("outputs"), case_id=case_id,
                internal_solver_cases=internal,
                internal_case_breakdown=(spawned.get("internal") or {}).get("breakdown"),
                unique_flow_conditions=(spawned.get("internal") or {}).get("unique_flow_conditions"))
            started = False
            _append_jsonl(evaluations_path, _flatten_condition_rows(case, case_plan, spawned, attempt_id))
            _write_json(case_dir / "case_result.json", {
                "schema": CAL_RESULT_SCHEMA, "case_id": case_id, "attempt_id": attempt_id,
                "status": spawned.get("status"), "target_family": case.get("target_family"),
                "actual_family": (case_plan.get("geometry") or {}).get("mesh_family_actual"),
                "rebuild_attempts": inputs.get("rebuild_attempts"),
                "mesh": case_plan.get("geometry", {}).get("mesh"),
                "process": spawned.get("process"), "internal_solver_cases": internal,
                "accounting_flags": flags,
                "lift_match": (spawned.get("evaluation") or {}).get("lift_match"),
                "objective": (spawned.get("evaluation") or {}).get("objective"),
                "physical_solver_starts": 1, "created_utc": ledger.iso_utc()})
            completed += 1
            hits = evaluate_stop_conditions(case_id, spawned, starts, caps, internal_total)
            if hits:
                stop_hits = hits
                break
        except Exception as exc:  # S8: never leave an unpaired start line
            if started:
                try:
                    solver_ledger.end_attempt(attempt_id, exit_code=None,
                                              status="EXECUTOR_EXCEPTION", wall_s=0.0,
                                              case_id=case_id,
                                              note=("EXECUTOR_EXCEPTION: %r" % exc)[:500])
                except Exception:
                    pass
                started = False
            stop_hits.append({"condition": "S8",
                              "detail": "EXECUTOR_EXCEPTION in %s: %r" % (case_id, exc)})
            _write_json(case_dir / "case_result.json", {
                "schema": CAL_RESULT_SCHEMA, "status": "FAILED_EXECUTOR_EXCEPTION",
                "case_id": case_id, "error": repr(exc),
                "physical_solver_starts": 1 if starts else 0,
                "created_utc": ledger.iso_utc()})
            break
        finally:
            if started:  # defensive: any unexpected path must close its start line
                try:
                    solver_ledger.end_attempt(attempt_id, exit_code=None,
                                              status="FAILED_EXECUTOR_EXCEPTION", wall_s=0.0,
                                              case_id=case_id,
                                              note="EXECUTOR_EXCEPTION: unpaired start closed in finally")
                except Exception:
                    pass
                started = False
    return finish()


def analyze(run_dir: Path) -> Dict[str, Any]:
    """Per-design cross-family CDi relative difference; gated by batch completeness."""
    plan, plan_sha, _plan_bytes = load_plan(run_dir)
    results: List[Dict[str, Any]] = []
    for case in plan["case_matrix"]:
        case_id = case["case_id"]
        result_path = run_dir / "cases" / case_id / "case_result.json"
        if not result_path.is_file():
            continue
        result = _read_json(result_path)
        if result.get("status") != "SOLVED":
            continue
        case_plan = _read_json(run_dir / "cases" / case_id / "plan.json")
        sref = float((case_plan.get("geometry") or {}).get("sref_m2") or 0.0)
        cl_target = TASK_SPEC.l_ref_n / (TASK_SPEC.q_pa * sref)
        polar_path = Path((case_plan.get("solver") or {}).get("cwd", "")) / (BASENAME + ".polar")
        cdi = _matched_cdi_from_polar(polar_path, cl_target)
        results.append({"case_id": case_id, "design_tag": case.get("design_tag"),
                        "design_hash": case.get("design_hash"), "family": case.get("target_family"),
                        "repeat": case.get("repeat"), "sref_m2": sref, "cl_target": cl_target,
                        "cdi_matched": cdi, "rebuild_attempts": result.get("rebuild_attempts")})
    by_design: Dict[str, Dict[str, Any]] = {}
    for design in (plan.get("designs") or []):
        tag = design["design_tag"]
        entries = [item for item in results if item["design_tag"] == tag]
        fam_a = [item for item in entries if item["family"] == FAMILY_LABELS[0]]
        fam_b = [item for item in entries if item["family"] == FAMILY_LABELS[1]]
        diffs: List[float] = []
        for a, b in zip(sorted(fam_a, key=lambda item: item["repeat"] or 0),
                        sorted(fam_b, key=lambda item: item["repeat"] or 0)):
            if a["cdi_matched"] and b["cdi_matched"]:
                diffs.append((b["cdi_matched"] - a["cdi_matched"]) / a["cdi_matched"])
        mean = sum(diffs) / len(diffs) if diffs else None
        spread = (max(diffs) - min(diffs)) if diffs else None
        cell_complete = len(fam_a) == 3 and len(fam_b) == 3 and len(diffs) == 3
        by_design[tag] = {
            "design_hash": design.get("design_hash"), "family_A": FAMILY_LABELS[0],
            "family_B": FAMILY_LABELS[1],
            "cdi_A": [item["cdi_matched"] for item in sorted(fam_a, key=lambda item: item["repeat"] or 0)],
            "cdi_B": [item["cdi_matched"] for item in sorted(fam_b, key=lambda item: item["repeat"] or 0)],
            "relative_difference": diffs, "mean": mean, "range": spread,
            "n_pairs": len(diffs), "cell_complete": cell_complete,
        }
    all_complete = (len(by_design) == len(plan.get("designs") or [])
                    and all(block["cell_complete"] for block in by_design.values()))
    verdict = "CAL_COMPLETE" if all_complete and len(by_design) == 2 else "CAL_INCOMPLETE"
    for block in by_design.values():
        if verdict != "CAL_COMPLETE":
            block["decision"] = "NOT_VALIDATED"
            block["decision_reason"] = "batch verdict %s: poolable/root-cause decisions are blocked" % verdict
        else:
            mean, spread = block.get("mean"), block.get("range")
            if mean is None or spread is None:
                block["decision"] = "NOT_VALIDATED"
            elif abs(mean) <= SAME_FAMILY_TOLERANCE and spread <= SAME_FAMILY_TOLERANCE:
                block["decision"] = "POOLABLE_CANDIDATE"
            else:
                block["decision"] = "ROOT_CAUSE_REQUIRED"
    return {"schema": CAL_SUMMARY_SCHEMA, "run_id": RUN_ID, "plan_sha256": plan_sha,
            "criteria": {"threshold": SAME_FAMILY_TOLERANCE,
                         "definition": "(CDi_B - CDi_A) / CDi_A at matched lift",
                         "poolable_candidate_if": "abs(mean(r)) <= 0.005 AND range(r) <= 0.005",
                         "incomplete_if": "any missing cell -> CAL_INCOMPLETE"},
            "verdict": verdict, "batch_verdict": verdict,
            "per_design": by_design, "case_results": results,
            "physical_validation_status": "NOT_VALIDATED",
            "prohibited_conclusions": ["optimizer ranking", "fuel burn", "physical drag validation"],
            "created_utc": ledger.iso_utc()}


def _matched_cdi_from_polar(polar_path: Path, cl_target: float) -> Optional[float]:
    if not polar_path.is_file():
        return None
    from . import polar_parser
    try:
        parsed = polar_parser.parse_polar_file(polar_path)
    except Exception:
        return None
    pairs: List[Tuple[float, float]] = []
    for row in parsed.get("rows") or []:
        cl = polar_parser.cltot(row)
        cdi = polar_parser.field(row, "CDi")
        if cl is None or cdi is None:
            continue
        pairs.append((float(cl), float(cdi)))
    pairs.sort()
    for (cl0, cdi0), (cl1, cdi1) in zip(pairs, pairs[1:]):
        if cl0 <= cl_target <= cl1 and cl1 != cl0:
            return cdi0 + (cl_target - cl0) * (cdi1 - cdi0) / (cl1 - cl0)
    return None


def write_artifacts(run_dir: Path) -> Dict[str, Any]:
    """Write CAL metrics/manifest/SHA list; physical count comes from the actual ledger/summary."""
    summary = analyze(run_dir)
    _write_json(run_dir / "calibration_results.json", summary)
    metrics = run_dir / "metrics.csv"
    lines = ["design_tag,design_hash,family_A,family_B,mean_relative_difference,range,n_pairs,decision"]
    for tag, block in summary["per_design"].items():
        lines.append("%s,%s,%s,%s,%s,%s,%s,%s" % (
            tag, block.get("design_hash"), block["family_A"], block["family_B"],
            "" if block["mean"] is None else "%.9e" % block["mean"],
            "" if block["range"] is None else "%.9e" % block["range"],
            block["n_pairs"], block.get("decision") or "NOT_VALIDATED"))
    lines.append("# fuel_burn_physical,NOT_RUN,requires validated external physics")
    lines.append("# 12D_ACTIVE,NOT_VALIDATED,mesh non-determinism unresolved")
    metrics.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    batch_summary = _read_json(run_dir / "batch_summary.json") if (run_dir / "batch_summary.json").is_file() else {}
    ledger_starts = ledger.SolverLedger(run_dir, RUN_ID, TASK_SPEC.task_id).count_starts()
    physical_starts = int(batch_summary.get("physical_solver_starts")
                          if batch_summary.get("physical_solver_starts") is not None else ledger_starts)
    files = {}
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name not in ("SHA256SUMS.txt", "data_manifest.json"):
            files[str(path.relative_to(run_dir)).replace("\\", "/")] = {
                "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    manifest = {"schema": "dreal001.data_manifest.v1", "run_id": RUN_ID,
                "created_utc": ledger.iso_utc(), "files": files, "file_count": len(files),
                "physical_solver_starts": physical_starts,
                "ledger_start_lines": int(ledger_starts),
                "batch_summary_status": batch_summary.get("status"),
                "source": "ledger/batch_summary actual counts (never hard-coded)"}
    _write_json(run_dir / "data_manifest.json", manifest)
    sums = ["%s  %s" % (entry["sha256"], name) for name, entry in sorted(files.items())]
    sums.append("%s  data_manifest.json" % sha256_file(run_dir / "data_manifest.json"))
    (run_dir / "SHA256SUMS.txt").write_bytes(("\n".join(sums) + "\n").encode("utf-8"))
    return {"calibration": summary, "manifest_files": len(files),
            "physical_solver_starts": physical_starts, "ledger_start_lines": ledger_starts}


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="P2A-CAL driver (zero physical until approved)")
    parser.add_argument("command", choices=("build", "dry-run", "run", "analyze"))
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--design-space", default=None)
    parser.add_argument("--p1c-plan", default=None)
    parser.add_argument("--prereg", default=None)
    parser.add_argument("--execution-code-sha", default=None)
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = repo_root() / run_dir
    if args.command == "build":
        build_plan(run_dir, Path(args.design_space), Path(args.p1c_plan), Path(args.prereg),
                   execution_code_sha=args.execution_code_sha)
    elif args.command == "dry-run":
        report = dry_run(run_dir)
        print(json.dumps({"status": report["status"], "approval": report["approval"],
                          "approval_sha256": report["approval_sha256"],
                          "executor": report["executor"],
                          "cases_planned": report["cases_planned"],
                          "physical_solver_starts": report["physical_solver_starts"]},
                         ensure_ascii=False))
    elif args.command == "run":
        summary = run_batch(run_dir)
        print(json.dumps({"status": summary["status"],
                          "physical_solver_starts": summary["physical_solver_starts"],
                          "internal_solver_cases": summary["internal_solver_cases"],
                          "stop_hits": summary["stop_hits"]}, ensure_ascii=False))
    else:
        print(json.dumps(write_artifacts(run_dir), ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
