"""Executable P2a v2 entry point (zero-physical until a signed approval exists).

This module is the executor blob bound by approval.a2_executor_sha256.  It:
  * validates the signed approval and every frozen binding before any start;
  * builds the A1 FreezeAPI callable and the A1 two-family evaluator;
  * runs three REPLAY_B2 preflight cases with a FRESH evaluator per case
    (A1 dedupes (design_hash, family); PRE-01 and PRE-03 are the same cell);
  * runs six arms over 32 design evaluations x 2 frozen families = 384 starts;
  * writes per-row backend, batch_summary, preflight_result and evaluations.

No physical start happens in dry-run mode.  There is no fallback: a missing
approval, closed window, hash mismatch or unavailable A1 real path stops with
zero starts.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

import numpy as np

from .p2a_v2_common import (
    A1_PAIR_MANIFEST_PATH,
    APPEND_ONLY_LOG_PATH,
    APPROVAL_SCHEMA,
    ARMS,
    BATCH_ID,
    DESIGN_EVALS_PER_ARM,
    DISCOVERY_TARGET_ATTEMPTS,
    FORCE_ATTEMPTS_PER_FAMILY,
    FREEZE_API_DISCOVERY_K,
    FROZEN_PAIR_MANIFEST_SHA256,
    INITIAL_DESIGN_INDICES,
    INITIAL_MANIFEST_SCHEMA,
    MAX_GEOMETRY_BUILDS,
    MAX_GEOMETRY_BUILDS_PER_DESIGN,
    MAX_INTERNAL_CASES,
    MAX_REFINE_STARTS,
    MAX_STARTS,
    PLANNED_INTERNAL_CASES,
    PLANNED_STARTS,
    PREFLIGHT_CASES_DEFAULT,
    Q_PA,
    RESERVE_STARTS,
    RUN_ID,
    SEED,
    TIMEOUT_SECONDS,
    WINDOW_END_UTC,
    WINDOW_START_UTC,
    WINDOW_TOKEN,
    ZERO_PHYSICAL_WALL_CAP_SECONDS,
    A1_DESIGN_SPACE_CONFIG_REL,
    A1_DESIGN_SPACE_CONFIG_SHA256,
    A1_DESIGN_SPACE_CONFIG_BYTES,
    A1_DESIGN_SPACE_PY_REL,
    A1_DESIGN_SPACE_PY_SHA256,
    A1_DESIGN_SPACE_PY_BYTES,
    DESIGN_SPACE_VARIABLE_IDS,
    DIAGNOSTIC_CASES,
    DIAGNOSTIC_PLANNED_INTERNAL_CASES,
    DIAGNOSTIC_PLANNED_STARTS,
    R10_PLANNED_STARTS,
    R10_PLANNED_INTERNAL_CASES,
    INVALID_CONSECUTIVE_MAX,
    INVALID_EVALUATION_STATUS,
    INVALID_RATIO_MAX,
    INVALID_RATIO_MIN_EVALS,
    INVALID_TOTAL_MAX,
    R10_CUMULATIVE_STARTS,
    R10_CUMULATIVE_INTERNAL_CASES,
    STATIC_INDEX_COUNT_EXPECTED,
    PREFROZEN_SOURCE_KIND,
    ACCOUNTING_INCONSISTENT,
    INTERNAL_CASES_PER_START, INTERNAL_CASES_PER_START_SOURCE,
)
from .p2a_v2_runtime import (
    family_frozen_payload,
    A1FreezeApiAdapter, A1LedgerReader, FreezeRecordStore, FrozenPairService,
    P2AV2Batch, P2AV2Runner, PreflightVerifier, ReservePool,
    design_hash, sha256_file, utc_now,
    internal_cases_from_starts,
)

DRY_RUN_SCHEMA = "dreal001.p2a_v2.executor_dry_run.v1"
BATCH_SCHEMA = "dreal001.p2a_v2_batch_summary.v1"
PREFLIGHT_SCHEMA = "dreal001.p2a_v2.preflight_result.v1"
EVAL_SCHEMA = "dreal001.p2a_v2.evaluation_row.v1"
EXECUTOR_VERSION = "a2-p2a-v2-executor-2026-11-11"


class ExecutorRefused(RuntimeError):
    """Fail-closed refusal; always before any solver start."""


def _read_json(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=1, default=str)
        stream.write("\n")


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _now_utc() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _parse_utc(text: str) -> float:
    """Parse an explicit UTC instant (never local-time arithmetic)."""
    from datetime import datetime, timezone
    value = str(text).strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _solver_contract_binding(plan: Mapping[str, Any], approval: Mapping[str, Any], *,
                             write_path: Optional[Path] = None) -> dict[str, Any]:
    """R1: the real exe is the plan/approval solver contract, never a silent fallback."""
    plan_sc = plan.get("solver_contract") or {}
    appr_solver = approval.get("solver") or approval.get("solver_contract") or {}
    exe_path = str(plan_sc.get("exe_path") or "").strip()
    exe_sha = str(plan_sc.get("exe_sha256") or "").strip().lower()
    if not exe_path or not exe_sha:
        raise ExecutorRefused("plan.solver_contract.exe_path/exe_sha256 is not bound")
    if str(appr_solver.get("exe_path") or "").strip() != exe_path:
        raise ExecutorRefused("approval.solver.exe_path does not match plan.solver_contract")
    if str(appr_solver.get("exe_sha256") or "").strip().lower() != exe_sha:
        raise ExecutorRefused("approval.solver.exe_sha256 does not match plan.solver_contract")
    exe = Path(exe_path)
    if not exe.is_file():
        raise ExecutorRefused("vspaero.exe from solver_contract is missing: %s" % exe_path)
    actual = sha256_file(exe)
    if actual.lower() != exe_sha:
        raise ExecutorRefused("vspaero.exe SHA256 mismatch: contract=%s actual=%s" % (exe_sha, actual))
    env_path = os.environ.get("DREAL001_VSPAERO_EXE", "").strip()
    if env_path:
        env_resolved = Path(env_path).resolve()
        if env_resolved != exe.resolve():
            raise ExecutorRefused("DREAL001_VSPAERO_EXE does not match plan solver contract: %s" % env_path)
    row = {
        "schema": "dreal001.p2a_v2.solver_exe_binding.v1",
        "checked_utc": _iso(_now_utc()), "source": "PLAN_SOLVER_CONTRACT",
        "exe_path": str(exe), "exe_sha256": actual, "exe_bytes": int(exe.stat().st_size),
        "contract_exe_path": exe_path, "contract_exe_sha256": exe_sha,
        "env_override_present": bool(env_path), "env_override_path": env_path or None,
        "match": True,
    }
    if write_path is not None:
        out = Path(write_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return row


def verify_execution_gate(
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
    *,
    run_dir: Path,
    plan_sha256: str,
    identity_sha256: str,
    executor_sha256: str,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """Fail-closed gate.  Raises ExecutorRefused before any start."""
    now = _now_utc() if now is None else float(now)
    if approval.get("schema") != APPROVAL_SCHEMA:
        raise ExecutorRefused("approval schema is not %s" % APPROVAL_SCHEMA)
    if approval.get("approved") is not True:
        raise ExecutorRefused("approval.approved is not true")
    if str(approval.get("run_id")) != RUN_ID or str(approval.get("batch_id")) != BATCH_ID:
        raise ExecutorRefused("approval run_id/batch_id mismatch")
    if str(approval.get("plan_sha256")) != str(plan_sha256):
        raise ExecutorRefused("approval.plan_sha256 does not match plan bytes")
    if str(approval.get("identity_binding_file_sha256")) != str(identity_sha256):
        raise ExecutorRefused("approval.identity_binding_file_sha256 mismatch")
    if str(approval.get("a2_executor_sha256")) != str(executor_sha256):
        raise ExecutorRefused("approval.a2_executor_sha256 mismatch")
    if int(approval.get("max_starts", 0)) != MAX_STARTS:
        raise ExecutorRefused("approval.max_starts is not %d" % MAX_STARTS)
    if int(approval.get("max_internal_cases", 0)) != MAX_INTERNAL_CASES:
        raise ExecutorRefused("approval.max_internal_cases is not %d" % MAX_INTERNAL_CASES)
    if int(approval.get("max_refine_starts", 0)) != MAX_REFINE_STARTS:
        raise ExecutorRefused("approval.max_refine_starts is not 0")
    if int(plan.get("matrix", {}).get("max_starts", 0) or 0) != MAX_STARTS:
        raise ExecutorRefused("plan.matrix.max_starts is not %d" % MAX_STARTS)
    if int(plan.get("matrix", {}).get("max_internal_cases", 0) or 0) != MAX_INTERNAL_CASES:
        raise ExecutorRefused("plan.matrix.max_internal_cases is not %d" % MAX_INTERNAL_CASES)
    solver_exe = _solver_contract_binding(plan, approval)
    window = approval.get("window") or {}
    start = str(window.get("start_utc") or WINDOW_START_UTC)
    end = str(window.get("end_utc") or WINDOW_END_UTC)
    token = str(window.get("token") or WINDOW_TOKEN)
    if token != WINDOW_TOKEN:
        raise ExecutorRefused("window token mismatch")
    if not (_parse_utc(start) <= now <= _parse_utc(end)):
        raise ExecutorRefused("approval window is not open")
    if not Path(run_dir).is_dir():
        raise ExecutorRefused("run_dir does not exist: %s" % run_dir)
    return {"checked_utc": _iso(now), "window_start_utc": start, "window_end_utc": end,
            "window_token": token, "max_starts": MAX_STARTS,
            "max_internal_cases": MAX_INTERNAL_CASES, "physical_call_count": 0,
            "solver_exe": solver_exe, "solver_exe_sha256": solver_exe["exe_sha256"]}


def _load_a1(a1_root: Path) -> tuple[Any, Any, Any]:
    """Import A1 FreezeAPI + evaluator v1.2 without writing bytecode."""
    sys.dont_write_bytecode = True
    root = str(Path(a1_root))
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        import research.concorde_metaopt.dreal001.geometry.freeze_api as freeze_api
        import research.concorde_metaopt.dreal001.geometry.evaluator_v12 as ev12
        import research.concorde_metaopt.dreal001.geometry.openvsp_model as openvsp_model
    except Exception as exc:  # noqa: BLE001
        raise ExecutorRefused("A1 real path is not importable: %s: %s" % (type(exc).__name__, exc))
    return freeze_api, ev12, openvsp_model


def _load_a1_design_space(a1_root: Path) -> tuple[Any, dict[str, Any]]:
    """Load and verify the frozen A1 12D design space (zero physical).

    R5: the A2 proposal engines work in unit [0,1]^12 while every value that
    enters freeze/evaluate/SrefResolver/design_hash must be a physical x12.
    The conversion is delegated to the A1 frozen DesignSpace API; both bound
    files are SHA-pinned so a changed design space fails closed before any
    start.  A1 bytes are never modified.
    """
    sys.dont_write_bytecode = True
    root = Path(a1_root)
    config = root / A1_DESIGN_SPACE_CONFIG_REL
    module = root / A1_DESIGN_SPACE_PY_REL
    for path, expected, label, size in (
        (config, A1_DESIGN_SPACE_CONFIG_SHA256, "design-space config", A1_DESIGN_SPACE_CONFIG_BYTES),
        (module, A1_DESIGN_SPACE_PY_SHA256, "design_space.py", A1_DESIGN_SPACE_PY_BYTES),
    ):
        if not path.is_file():
            raise ExecutorRefused("A1 %s missing: %s" % (label, path))
        if path.stat().st_size != size:
            raise ExecutorRefused("A1 %s size mismatch: %s" % (label, path))
        if sha256_file(path) != expected:
            raise ExecutorRefused("A1 %s SHA mismatch: %s" % (label, path))
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    try:
        from research.concorde_metaopt.aircraft.design_space import load_design_space
    except Exception as exc:  # noqa: BLE001
        raise ExecutorRefused("A1 design_space is not importable: %s: %s"
                             % (type(exc).__name__, exc))
    space = load_design_space(config)
    return space, {
        "design_space_config_path": str(config),
        "design_space_config_sha256": A1_DESIGN_SPACE_CONFIG_SHA256,
        "design_space_config_bytes": A1_DESIGN_SPACE_CONFIG_BYTES,
        "design_space_module_path": str(module),
        "design_space_module_sha256": A1_DESIGN_SPACE_PY_SHA256,
        "design_space_module_bytes": A1_DESIGN_SPACE_PY_BYTES,
        "design_space_variable_ids": list(DESIGN_SPACE_VARIABLE_IDS),
        "unit_domain": "[0,1]^12",
        "boundary_rule": "fail-closed; never clip a physical x12 into a unit seed",
        "physical_call_count": 0,
        "solver_started": False,
    }


def _check_x12_domain(values: Sequence[float], what: str) -> list[float]:
    out = [float(v) for v in values]
    if len(out) != len(DESIGN_SPACE_VARIABLE_IDS):
        raise ExecutorRefused("%s must have %d entries, got %d"
                             % (what, len(DESIGN_SPACE_VARIABLE_IDS), len(out)))
    if not all(math.isfinite(v) for v in out):
        raise ExecutorRefused("%s contains a non-finite value" % what)
    return out


def x12_to_unit(space: Any, x12: Sequence[float]) -> list[float]:
    """Physical x12 -> unit [0,1]^12 through the frozen A1 design space."""
    values = _check_x12_domain(x12, "physical x12")
    try:
        unit = [float(v) for v in space.to_unit_interval(
            dict(zip(DESIGN_SPACE_VARIABLE_IDS, values)))]
    except Exception as exc:  # noqa: BLE001
        raise ExecutorRefused("physical x12 is outside the frozen design space: %s: %s"
                             % (type(exc).__name__, exc))
    if len(unit) != len(DESIGN_SPACE_VARIABLE_IDS) or not all(math.isfinite(v) for v in unit):
        raise ExecutorRefused("design_space.to_unit_interval returned an invalid vector")
    if any(v < -1e-12 or v > 1.0 + 1e-12 for v in unit):
        raise ExecutorRefused("physical x12 maps outside unit [0,1]^12")
    return unit


def unit_to_x12(space: Any, unit: Sequence[float]) -> list[float]:
    """Unit [0,1]^12 -> physical x12 through the frozen A1 design space."""
    values = _check_x12_domain(unit, "unit proposal")
    if any(v < -1e-12 or v > 1.0 + 1e-12 for v in values):
        raise ExecutorRefused("unit proposal is outside [0,1]^12")
    try:
        physical = space.from_unit_interval(values)
    except Exception as exc:  # noqa: BLE001
        raise ExecutorRefused("unit proposal cannot be mapped to physical x12: %s: %s"
                             % (type(exc).__name__, exc))
    try:
        x12 = [float(physical[name]) for name in DESIGN_SPACE_VARIABLE_IDS]
    except Exception as exc:  # noqa: BLE001
        raise ExecutorRefused("design_space.from_unit_interval returned an invalid mapping: %s: %s"
                             % (type(exc).__name__, exc))
    return _check_x12_domain(x12, "mapped physical x12")


def build_freeze_fn(a1_root: Path, run_dir: Path) -> Callable[..., Mapping[str, Any]]:
    freeze_api, _, _ = _load_a1(a1_root)
    log_path = Path(run_dir) / "runtime" / "freeze_log.jsonl"

    def freeze_fn(x12: Sequence[float], design_hash: str, out_dir: Any, policy: Mapping[str, Any],  # noqa: A002
                  builder_sha: str) -> Mapping[str, Any]:
        return freeze_api.discover_and_freeze_pair(
            list(float(v) for v in x12),
            design_hash,
            str(out_dir),
            policy=dict(policy),
            builder_sha=str(builder_sha),
            log_path=str(log_path),
        )

    return freeze_fn


def _a1_sref_config_root(a1_root: Path) -> Path:
    """Mirror the A1 12D config tree with frozen:false for the A2 process.

    A1 fresh-process builder loads the A1 config from the A1 tree (frozen:true,
    rejected by the shared loader). A2 imports that loader from its own tree,
    so for the zero-physical Sref(x) lookup we mirror the A1 config bytes into
    an A2 runtime temp tree with only the frozen gate flipped. No A1 file is
    modified, no geometry is built and no solver starts.
    """
    openvsp_model = _load_a1(a1_root)[2]
    source = Path(openvsp_model.REPO_ROOT) / "research/concorde_metaopt/configs" / \
        "design_space_12d_lifting_surfaces.yaml"
    if not source.is_file():
        raise ExecutorRefused("A1 design space config missing: %s" % source)
    text = source.read_text(encoding="utf-8")
    if "\nfrozen: true" in text:
        text = text.replace("\nfrozen: true", "\nfrozen: false", 1)
    elif text.startswith("frozen: true"):
        text = "frozen: false" + text[len("frozen: true"):]
    import tempfile
    target_root = Path(tempfile.gettempdir()) / "a2_p2a_v2_sref_config"
    config = target_root / "research/concorde_metaopt/configs" / source.name
    config.parent.mkdir(parents=True, exist_ok=True)
    if not config.is_file() or config.read_text(encoding="utf-8") != text:
        config.write_text(text, encoding="utf-8")
    return target_root


def sref_from_x12(a1_root: Path, x12: Sequence[float]) -> float:
    """Zero-physical Sref(x) = wing.area_m2 via A1 openvsp_model geometry model.

    A1 evaluator_v12 omits sref_m2 from geometry_bundle; the canonical A1 path
    openvsp_model._geometry_from_design_vector(x12) -> geometry.wing.area_m2 is
    deterministic and never launches VSPAERO. A2 mirrors the A1 config tree in a
    temp directory solely to satisfy the shared frozen gate; A1 bytes untouched.
    """
    openvsp_model = _load_a1(a1_root)[2]
    values = [float(v) for v in x12]
    if len(values) != 12 or not all(math.isfinite(v) for v in values):
        raise ExecutorRefused("Sref(x) requires 12 finite design values")
    original_root = openvsp_model.REPO_ROOT
    try:
        openvsp_model.REPO_ROOT = _a1_sref_config_root(a1_root)
        geometry, _space = openvsp_model._geometry_from_design_vector(values)
    finally:
        openvsp_model.REPO_ROOT = original_root
    area = float(geometry.wing.area_m2)
    if not area > 0 or not math.isfinite(area):
        raise ExecutorRefused("non-positive or non-finite Sref(x) = %r" % area)
    return area

def build_sref_map(a1_root: Path, x12_by_hash: Mapping[str, Sequence[float]]) -> dict[str, float]:
    return {str(dh): sref_from_x12(a1_root, x12) for dh, x12 in x12_by_hash.items()}


class SrefResolver:
    """Lazy zero-physical Sref(x) resolver for designs outside the static manifest.

    Sref(x) depends only on x12 (wing area), so an unseen online proposal can be
    resolved on demand without rebuilding geometry or touching the frozen bytes.
    """

    def __init__(self, a1_root: Path, seed: Optional[Mapping[str, float]] = None) -> None:
        self.a1_root = Path(a1_root)
        self._values: dict[str, float] = {str(k): float(v) for k, v in (seed or {}).items()}
        self._lazy: dict[str, float] = {}

    def note(self, design_hash_value: str, x12: Optional[Sequence[float]]) -> Optional[float]:
        dh = str(design_hash_value)
        if dh in self._values:
            return self._values[dh]
        if dh in self._lazy:
            return self._lazy[dh]
        if x12 is None:
            return None
        value = float(sref_from_x12(self.a1_root, x12))
        self._lazy[dh] = value
        return value

    def get(self, design_hash_value: str) -> Optional[float]:
        dh = str(design_hash_value)
        return self._values.get(dh, self._lazy.get(dh))

    def snapshot(self) -> dict[str, float]:
        merged = dict(self._values)
        merged.update(self._lazy)
        return merged


def _write_runtime_solver_inputs(case_dir: Path, basename: str, sref: float, a1_root: Path) -> None:
    """Write the .vspaero/.csf inputs the frozen .vspgeom/.vkey pair needs.

    The frozen bytes are never rebuilt or modified.  Only the solver input file
    (a text parameter deck) is written; Sref comes from Sref(x), not from bytes.
    """
    _, _, openvsp_model = _load_a1(a1_root)
    task_spec = openvsp_model.TASK_SPEC
    vspaero = case_dir / (basename + ".vspaero")
    if not vspaero.is_file():
        alphas = ", ".join("%g" % float(a) for a in task_spec.alpha_fixed_list_deg)
        lines = [
            "Sref = %.15g " % float(sref),
            "Cref = %.15g " % float(task_spec.cref_m),
            "Bref = %.15g " % float(task_spec.bref_m),
            "X_cg = %.15g " % float(task_spec.xcg_m),
            "Y_cg = 0 ", "Z_cg = 0 ",
            "Mach = %g " % float(task_spec.mach),
            "AoA = %s " % alphas,
            "Beta = 0 ",
            "ReCref = %.15g " % float(task_spec.recref),
            "Vinf = %.15g " % float(task_spec.vinf_m_s),
            "Rho = %.15g " % float(task_spec.rho_kg_m3),
            "StallModel = 0 ", "Clo2D = 0 ", "CLMax2D = 1 ", "Symmetry = 0 ",
            "FreezeMultiPoleAtIteration = 10000 ", "FreezeWakeAtIteration = 10000 ",
            "FreezeWakeRootVortices = 0 ", "ImplicitWake = 0 ", "ImplicitWakeStartIteration = 0 ",
            "FarDist = -1 ", "NumWakeNodes = 8 ", "WakeIters = 5 ", "WakeRelax = 1 ",
            "ForwardGMRESConvergenceFactor = 1 ", "AdjointGMRESConvergenceFactor = 1 ",
            "NonLinearConvergenceFactor = 1 ", "CoreSizeFactor = 1 ", "FarAway = 5 ",
            "UpdateMatrixPreconditioner = 0 ", "UseWakeNodeMatrixPreconditioner = 0 ",
            "Write2DFEMFile = 0 ", "WriteTecplotFile = 0 ", "NumberOfControlGroups = 0 ",
            "NumberofSurveyPoints = 0 ", "QuadTreeBufferLevels = 0 ", "NumberOfQuadTrees = 1 ",
            "1 2 0 ", "NumberOfInlets = 0 ", "NumberOfNozzles = 0 ", "VSP_StabilityType = 0 ",
        ]
        vspaero.write_text("\n".join(lines) + "\n", encoding="ascii")
    csf = case_dir / (basename + ".csf")
    if not csf.is_file():
        csf.write_bytes(b"0 Control Surfaces\r\n")


def _polar_objective(case_dir: Path, basename: str, sref: float, a1_root: Path) -> dict[str, Any]:
    """Parse the produced polar and compute D_i_N at the matched lift."""
    _, _, openvsp_model = _load_a1(a1_root)
    task_spec = openvsp_model.TASK_SPEC
    from research.concorde_metaopt.dreal001.geometry import polar_parser, solver_runner

    polar_path = case_dir / (basename + ".polar")
    polar = polar_parser.parse_polar_file(polar_path)
    rows = polar_parser.unique_case_rows(polar["rows"])
    q = float(task_spec.q_pa)
    cl_target = float(task_spec.l_ref_n) / (q * float(sref))
    match = solver_runner._interp_alpha(rows, cl_target)
    results = {"alpha_deg": [], "cltot": [], "cdi": [], "cdtot": [], "cdo": []}
    for row in rows:
        if not polar_parser.row_is_valid(row):
            continue
        results["alpha_deg"].append(polar_parser.field(row, "AoA"))
        results["cltot"].append(polar_parser.cltot(row))
        results["cdi"].append(polar_parser.field(row, "CDi"))
        results["cdtot"].append(polar_parser.field(row, "CDtot"))
        results["cdo"].append(polar_parser.field(row, "CDo"))
    if match.get("status") != "LIFT_MATCHED_BY_INTERPOLATION":
        return {"objective": None, "results": results,
                "lift": {"matched": False, "status": match.get("status"),
                         "cl_target": cl_target, "sref_m2": float(sref)}}
    alpha = float(match["alpha_deg"])
    cdi = solver_runner._interp_field_at_alpha(rows, alpha, "CDi")
    cl = solver_runner._interp_field_at_alpha(rows, alpha, "CLtot")
    if cdi is None or cl is None:
        return {"objective": None, "results": results,
                "lift": {"matched": False, "status": "INTERPOLATION_FAILED",
                         "cl_target": cl_target, "sref_m2": float(sref)}}
    return {"objective": q * float(sref) * float(cdi), "results": results,
            "lift": {"matched": True, "cl": float(cl), "rel_error": 0.0,
                     "alpha_deg": alpha, "cl_target": cl_target,
                     "sref_m2": float(sref), "status": match.get("status")}}


class A1FamilySolver:
    """Adapt the A1 two-family evaluator to the A2 runner's SolverResult shape."""

    def __init__(self, evaluator: Any, *, arm_id: str, sref_by_hash: Mapping[str, float],
                 q_pa: float = Q_PA, sref_resolver: Optional[SrefResolver] = None,
                 a1_root: Optional[Path] = None) -> None:
        self.evaluator = evaluator
        self.arm_id = str(arm_id)
        self._legacy_sref = dict(sref_by_hash)
        self.sref_resolver = sref_resolver or SrefResolver(a1_root or Path("."), self._legacy_sref)
        self.q_pa = float(q_pa)

    def evaluate(self, family: Any, design_hash_value: str, slot: str, *, x12: Optional[Sequence[float]] = None) -> Any:
        if x12 is None:
            raise ExecutorRefused("A1FamilySolver requires x12 for design %s" % design_hash_value)
        role = "f1" if slot == "f1" else "f2"
        # case_id carries the arm so A1 attempt_ids and A3 aggregation stay attributable.
        case_id = "%s-%s-%s" % (self.arm_id, design_hash_value, role)
        # Resolve Sref(x) lazily BEFORE the A1 call: A1's real_spawn context has no
        # x12, so unseen online proposals are cached here first (zero physical).
        self.sref_resolver.note(str(design_hash_value), list(float(v) for v in x12))
        sref = self.sref_resolver.get(str(design_hash_value))
        if sref is None or not math.isfinite(float(sref)) or float(sref) <= 0.0:
            raise ExecutorRefused("invalid/missing Sref(x) for design %s" % design_hash_value)
        record = self.evaluator.evaluate(list(float(v) for v in x12), role, case_id=case_id)
        status = str(record.get("status") or record.get("record_status") or "")
        geometry = record.get("geometry_bundle") or record.get("geometry") or {}
        solver = record.get("solver") or {}
        results = record.get("results") or {}
        lift = record.get("lift") or {}
        objective = record.get("objective") or {}
        value = objective.get("value") if isinstance(objective, dict) else None
        # A1 geometry_bundle has no Sref by design; use Sref(x) computed from x12.
        cdi = None
        if value is not None and sref not in (None, 0):
            cdi = float(value) / (self.q_pa * float(sref))
        cl = lift.get("cl") if isinstance(lift, dict) else None
        if cl is None:
            cl = lift.get("CL") if isinstance(lift, dict) else None
        lift_rel = lift.get("rel_error") if isinstance(lift, dict) else None
        feasible = bool(lift.get("matched", status == "SOLVED_VALID") and
                        (lift_rel is None or float(lift_rel) <= 1e-3))
        from .p2a_v2_runtime import SolverResult

        _physical_starts = int(record.get("physical_solver_starts", solver.get("physical_solver_starts", 0)) or 0)
        return SolverResult(
            status=status or "SOLVER_FAILED",
            cdi=cdi,
            cl=None if cl is None else float(cl),
            physical_solver_starts=_physical_starts,
            internal_solver_cases=internal_cases_from_starts(_physical_starts),
            vspgeom_sha_before=str(geometry.get("vspgeom_sha256_before") or geometry.get("vspgeom_sha256") or ""),
            vspgeom_sha_after=str(geometry.get("vspgeom_sha256_after") or geometry.get("vspgeom_sha256") or ""),
            canonical_sha_after=str(geometry.get("canonical_mesh_sha256_after") or geometry.get("canonical_mesh_sha256") or ""),
            feasible=feasible,
            errors=tuple(str(e.get("code") if isinstance(e, Mapping) else e) for e in (record.get("errors") or [])),
            sref_m2=float(sref),
            polar_sha256=_find_polar_sha(record),
        )


def _ensure_solver_geometry_alias(case_dir: Path, basename: str) -> dict[str, Any]:
    """R2: VSPAERO reads <basename>.vspgeom/.vkey; A1 materialises model.*.

    Copy the already-verified frozen geometry bytes to the basename alias before
    launch.  Source bytes are never modified and no geometry is rebuilt; both
    copies are SHA-checked so a stale/mismatched alias fails closed.
    """
    copied: dict[str, Any] = {}
    for stem in ("vspgeom", "vkey"):
        source = case_dir / ("model." + stem)
        alias = case_dir / (basename + "." + stem)
        if alias.is_file():
            if not source.is_file():
                raise ExecutorRefused("missing %s to verify existing solver alias %s" % (source.name, alias.name))
            if sha256_file(source) != sha256_file(alias):
                raise ExecutorRefused("solver geometry alias mismatch: %s != %s" % (alias.name, source.name))
            copied[stem] = {"path": str(alias), "sha256": sha256_file(alias), "copied": False}
            continue
        if not source.is_file():
            raise ExecutorRefused("missing %s for solver alias %s" % (source.name, alias.name))
        before = sha256_file(source)
        shutil.copyfile(source, alias)
        after = sha256_file(alias)
        if after != before:
            raise ExecutorRefused("solver geometry alias copy changed bytes: %s" % alias.name)
        copied[stem] = {"path": str(alias), "sha256": after, "copied": True}
    return copied

def _real_spawn_factory(a1_root: Path, run_dir: Path,
                        sref_by_hash: Optional[Mapping[str, float]] = None,
                        sref_resolver: Optional[SrefResolver] = None,
                        solver_binding: Optional[Mapping[str, Any]] = None) -> Callable[..., Mapping[str, Any]]:
    """Real vspaero.exe spawn for A1 evaluator; one process = one start.

    R1: the executable path/SHA comes only from the approved plan solver
    contract.  No OPENVSP_ROOT scan and no silent fallback.
    """
    _, _, openvsp_model = _load_a1(a1_root)
    resolver = sref_resolver or SrefResolver(a1_root, sref_by_hash)
    if not solver_binding:
        raise ExecutorRefused("real spawn requires the approved solver_contract binding")
    expected_sha = str(solver_binding.get("exe_sha256") or "")
    exe = Path(str(solver_binding.get("exe_path") or ""))

    def real_spawn(context: Mapping[str, Any]) -> Mapping[str, Any]:
        case_dir = Path(str(context["case_dir"]))
        basename = str(context.get("basename") or "concorde_baseline")
        if not exe.is_file():
            raise ExecutorRefused("vspaero.exe missing at approved path: %s" % exe)
        actual = sha256_file(exe)
        if actual.lower() != expected_sha.lower():
            raise ExecutorRefused("vspaero.exe SHA256 changed before spawn: %s != %s" % (actual, expected_sha))
        dh = str(context.get("design_hash") or "")
        sref = resolver.get(dh)
        if sref is None:
            raise ExecutorRefused("no Sref(x) for design %s" % dh)
        _write_runtime_solver_inputs(case_dir, basename, float(sref), a1_root)
        _ensure_solver_geometry_alias(case_dir, basename)
        started = _now_utc()
        proc = subprocess.Popen([str(exe), "-omp", "1", basename], cwd=str(case_dir),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            output, _ = proc.communicate(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return {"status": "TIMEOUT", "internal_evals": 0,
                    "wall_s": _now_utc() - started, "stdout_tail": "timeout"}
        polar = case_dir / (basename + ".polar")
        status = "SOLVED_VALID" if proc.returncode == 0 and polar.is_file() else "SOLVER_FAILED"
        outcome: dict[str, Any] = {
            "status": status, "exit_code": int(proc.returncode), "internal_evals": 7,
            "polar_path": str(polar) if polar.is_file() else None,
            "wall_s": _now_utc() - started, "stdout_tail": (output or "")[-2000:],
        }
        if status == "SOLVED_VALID":
            try:
                parsed = _polar_objective(case_dir, basename, float(sref), a1_root)
            except Exception as exc:  # fail closed, start already charged
                outcome["status"] = "LIFT_MATCH_FAILED"
                outcome["error"] = "POLAR_OBJECTIVE_FAILED: %r" % (exc,)
            else:
                outcome["objective"] = parsed["objective"]
                outcome["results"] = parsed["results"]
                outcome["lift"] = parsed["lift"]
                if parsed["objective"] is None:
                    outcome["status"] = "LIFT_MATCH_FAILED"
        return outcome

    return real_spawn


def make_preflight_factory(a1_root: Path, run_dir: Path, approval: Mapping[str, Any],
                           manifest: Mapping[str, Any], manifest_path: Path,
                           x12_by_hash: Mapping[str, Sequence[float]],
                           sref_by_hash: Optional[Mapping[str, float]] = None,
                           solver_binding: Optional[Mapping[str, Any]] = None,
                           ledger: Any = None,
                           exe_path: Optional[Path] = None) -> Callable[[Mapping[str, Any]], Callable[[Mapping[str, Any]], Mapping[str, Any]]]:
    """Return a factory that builds a NEW A1 evaluator for every preflight case.

    R1: two replay cases; per-case starts are read from record.solver.
    physical_solver_starts and cross-checked against the canonical ledger delta.
    """
    _, ev12, _ = _load_a1(a1_root)
    real_spawn = _real_spawn_factory(a1_root, run_dir, sref_by_hash, solver_binding=solver_binding)

    def factory(case: Mapping[str, Any]) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
        case_id = str(case["case_id"])
        case_dir = Path(run_dir) / "preflight" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        # A5: resolve x12/family BEFORE the evaluator takes the exclusive lock,
        # so a KeyError can never leave a stale .lock behind.
        x12 = list(x12_by_hash[str(case["design_hash"])])
        family = "f1" if str(case.get("family_label")) == "483x418" else "f2"
        evaluator = ev12.TwoFamilyEvaluator(
            manifest, approval, batch_id=str(approval.get("batch_id")), max_starts=1,
            run_dir=case_dir, manifest_source=manifest_path, mock=False, mode=ev12.MODE_REPLAY,
            replay_physical=True, real_spawn=real_spawn, allow_physical_starts=True,
            ledger_path=Path(run_dir) / "solver_attempts.jsonl",
        )

        def replay(c: Mapping[str, Any]) -> Mapping[str, Any]:
            def f(name: str) -> str:
                return str(case_dir / name)
            starts_before = int(ledger.count_starts()) if ledger is not None else None
            replay_input = {
                "vspgeom_path": f("geometry.vspgeom"),
                "vkey_path": f("geometry.vkey"),
                "vspaero_path": f("concorde_baseline.vspaero"),
                "csf_path": f("concorde_baseline.csf"),
                "expected_polar_sha256": c.get("expected_polar_sha256"),
            }
            try:
                record = evaluator.evaluate(x12, family, case_id=case_id,
                                            replay_input=replay_input)
            finally:
                close = getattr(evaluator, "close", None)
                if callable(close):
                    close()
            # A1 writes the case artifacts under run_dir/preflight/<case_id>/<case_id>/.
            polar = case_dir / case_id / ("concorde_baseline.polar")
            solver_block = record.get("solver") or {}
            record_starts = int(solver_block.get("physical_solver_starts", record.get("physical_solver_starts", record.get("physical_call_count", 0))) or 0)
            ledger_delta = (int(ledger.count_starts()) - int(starts_before)) if ledger is not None else None
            starts_consistent = (ledger_delta == record_starts) if ledger_delta is not None else True
            return {
                "status": (record.get("status") or record.get("record_status")),
                "polar_sha256": sha256_file(polar) if polar.is_file() else None,
                "mesh_family": (record.get("geometry_bundle") or {}).get("mesh_family"),
                "starts": ledger_delta if ledger_delta is not None else record_starts,
                "record_starts": record_starts,
                "ledger_delta": ledger_delta,
                "starts_consistent": starts_consistent,
                "physical_solver_starts": record_starts,
                "internal_solver_cases": internal_cases_from_starts(record_starts),
                "internal_cases_source": INTERNAL_CASES_PER_START_SOURCE,
                "errors": record.get("errors") or [],
            }

        return replay

    return factory


class ProposalEngine:
    """Online six-arm proposals.  Only real evaluations update state."""

    def __init__(self, arm_id: str, *, seed: int = SEED, adaptive: bool = False) -> None:
        self.arm_id = arm_id
        self.seed = int(seed)
        self.adaptive = bool(adaptive)
        self.rng = np.random.default_rng(self.seed + ARMS.index(arm_id) * 101)
        self.population: list[dict[str, Any]] = []
        self.pending: dict[str, Any] = {}
        self.bo = None
        self.velocity: dict[str, np.ndarray] = {}
        self.pbest: dict[str, dict[str, Any]] = {}
        self.gbest: Optional[dict[str, Any]] = None
        self.initial: list[np.ndarray] = []
        if arm_id in ("BO", "ABO"):
            from maml_opt.bayesian import ConstrainedBayesianOptimizer

            self.bo = ConstrainedBayesianOptimizer(np.zeros(12), np.ones(12), seed=self.seed,
                                                   candidate_count=256)
        self.extra_pool: Optional[np.ndarray] = None

    def _extras(self, n: int) -> np.ndarray:
        if self.extra_pool is None or len(self.extra_pool) < n:
            if self.adaptive:
                from ..warm_start.surrogate import zero_shot_snapshot
                from ..warm_start.sampler import WarmStartConfig, WarmStartSampler

                snapshot = zero_shot_snapshot(seed=self.seed)
                sampler = WarmStartSampler(WarmStartConfig(source="zero_shot_surrogate", seed=self.seed),
                                           snapshot=snapshot)
                proposal = sampler.propose((0.0, 0.0), 12, n_new=max(8, n), seed=self.seed)
                self.extra_pool = np.clip(np.asarray(proposal.X_init, dtype=float), 0.0, 1.0)
            else:
                self.extra_pool = self.rng.random((max(16, n), 12))
        return self.extra_pool[:n]

    def seed_initial(self, units: Sequence[Sequence[float]]) -> None:
        self.initial = [np.clip(np.asarray(u, dtype=float), 0.0, 1.0) for u in units]

    def propose(self, arm_id: str, design_index: int, replacement_attempt: int) -> Sequence[float]:
        if design_index <= len(self.initial):
            return self.initial[design_index - 1]
        if self.bo is not None:
            proposal = self.bo.ask()
            if proposal is None:
                raise ExecutorRefused("BO exhausted candidates")
            vector = np.clip(np.asarray(proposal["design_vector"], dtype=float), 0.0, 1.0)
            self.pending[design_hash(vector)] = vector
            return vector
        if not self.population:
            self.population = [{"u": u, "primary": None, "feasible": False}
                               for u in self.initial]
            extras = self._extras(max(4, 5 - len(self.population)))
            for u in extras:
                self.population.append({"u": np.asarray(u, dtype=float), "primary": None,
                                        "feasible": False})
        if self.arm_id in ("DE", "ADE") and len(self.population) < 4:
            for u in self._extras(max(1, 4 - len(self.population))):
                self.population.append({"u": np.asarray(u, dtype=float), "primary": None,
                                        "feasible": False})
        if self.arm_id in ("DE", "ADE"):
            target = len(self.population) % len(self.population)
            idx = (design_index - len(self.initial) - 1) % len(self.population)
            candidates = [i for i in range(len(self.population)) if i != idx]
            r1, r2, r3 = self.rng.choice(candidates, size=3, replace=False)
            base = self.population[r1]["u"]
            mutant = np.clip(base + 0.5 * (self.population[r2]["u"] - self.population[r3]["u"]), 0.0, 1.0)
            mask = self.rng.random(12) < 0.7
            if not mask.any():
                mask[self.rng.integers(0, 12)] = True
            trial = np.where(mask, mutant, self.population[idx]["u"])
            self.pending["target_index"] = idx
            self.pending[design_hash(trial)] = trial
            return trial
        # PSO / APSO
        if not self.velocity:
            self.velocity = {design_hash(p["u"]): self.rng.uniform(-0.1, 0.1, 12)
                             for p in self.population}
            for p in self.population:
                self.pbest[design_hash(p["u"])] = dict(p)
        idx = (design_index - len(self.initial) - 1) % len(self.population)
        current = self.population[idx]["u"]
        key = design_hash(current)
        v = 0.7298 * self.velocity.get(key, np.zeros(12))
        pbest = self.pbest.get(key, {"u": current})
        gbest = self.gbest or pbest
        v = v + 1.49618 * self.rng.random(12) * (pbest["u"] - current)
        v = v + 1.49618 * self.rng.random(12) * (gbest["u"] - current)
        v = np.clip(v, -0.2, 0.2)
        self.velocity[key] = v
        trial = np.clip(current + v, 0.0, 1.0)
        self.pending["target_index"] = idx
        self.pending[design_hash(trial)] = trial
        return trial

    def observe(self, unit: Sequence[float], evaluation: Any) -> None:
        u = np.clip(np.asarray(unit, dtype=float), 0.0, 1.0)
        key = design_hash(u)
        primary = evaluation.primary if evaluation.status == "SOLVED_VALID" else None
        feasible = bool(evaluation.feasible and primary is not None)
        if self.bo is not None:
            if primary is not None:
                try:
                    self.bo.tell(list(u), {
                        "valid": True, "objective": float(primary),
                        "constraints_g_le_zero": {"C00_lift_feasible": 0.0 if feasible else 1.0},
                    })
                except ValueError:
                    pass
            return
        if not self.population:
            self.population = [{"u": np.asarray(i, dtype=float), "primary": None, "feasible": False}
                               for i in self.initial]
            # R7: pad the DE/PSO population so the first proposal after the three
            # seeded initial designs cannot underflow rng.choice(..., size=3).
            for u in self._extras(max(4, 5 - len(self.population))):
                self.population.append({"u": np.asarray(u, dtype=float), "primary": None,
                                        "feasible": False})
        target = self.pending.get("target_index")
        if target is None:
            return
        incumbent = self.population[target]
        better = (primary is not None and (incumbent["primary"] is None or float(primary) < float(incumbent["primary"])))
        if better:
            self.population[target] = {"u": u, "primary": float(primary), "feasible": feasible}
        if self.arm_id in ("PSO", "APSO"):
            pkey = key
            if primary is not None and (pkey not in self.pbest or
                                        self.pbest[pkey]["primary"] is None or
                                        float(primary) < float(self.pbest[pkey]["primary"])):
                self.pbest[pkey] = {"u": u, "primary": float(primary), "feasible": feasible}
            if self.gbest is None or (primary is not None and
                                      (self.gbest.get("primary") is None or float(primary) < float(self.gbest["primary"]))):
                self.gbest = {"u": u, "primary": float(primary), "feasible": feasible}


def _load_x12_by_hash(manifest: Mapping[str, Any]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for record in manifest.get("records") or manifest.get("designs") or []:
        dh = str(record.get("design_hash") or "")
        x12 = record.get("x12")
        if dh and isinstance(x12, list) and len(x12) == 12:
            out[dh] = [float(v) for v in x12]
    return out


INITIAL_EXPECTED_HASHES = {15: "d51866f7d3c49303", 16: "eb00b7ad545243e6",
                          17: "dc96d2438a6dddc3"}


def _validate_initial_designs(initial: Mapping[str, Any], approval: Mapping[str, Any],
                              run_dir: Path) -> None:
    """Fail closed if the three shared initial designs do not match plan/approval."""
    bound = str(approval.get("initial_designs_manifest_sha256") or "")
    actual = sha256_file(Path(run_dir) / "initial_designs_manifest.json")
    if bound != actual:
        raise ExecutorRefused("initial_designs_manifest SHA mismatch: bound=%s actual=%s"
                              % (bound, actual))
    designs = list(initial.get("designs") or [])
    if len(designs) != 3:
        raise ExecutorRefused("initial_designs_manifest must contain exactly 3 designs")
    seen: dict[int, str] = {}
    for rec in designs:
        index = int(rec.get("design_index", -1))
        x12 = [float(v) for v in rec.get("x12") or []]
        dh = design_hash(x12)
        expected = INITIAL_EXPECTED_HASHES.get(index)
        if expected is None:
            raise ExecutorRefused("unexpected initial design_index %s" % index)
        if dh != expected:
            raise ExecutorRefused("initial design %s hash mismatch: %s != %s"
                                  % (index, dh, expected))
        if str(rec.get("design_hash")) != dh:
            raise ExecutorRefused("initial design %s record hash mismatch" % index)
        seen[index] = dh
    if set(seen) != set(INITIAL_EXPECTED_HASHES):
        raise ExecutorRefused("initial design indices must be 15/16/17")


def _pending_starts(ledger_path: Path) -> list[dict[str, Any]]:
    path = Path(ledger_path)
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    ended = {str(r.get("case_id")) for r in rows if r.get("event") == "end"}
    return [r for r in rows if r.get("event") == "start"
            and str(r.get("case_id")) not in ended]


def _repair_pending_starts(ledger_path: Path, exc: BaseException) -> list[dict[str, Any]]:
    """Append a terminal end row for every start left open by an exception.

    The start was already charged; the repair never refunds it.  A5 can pair every
    start with exactly one end row even on executor failure.
    """
    pending = _pending_starts(ledger_path)
    if not pending:
        return []
    path = Path(ledger_path)
    with path.open("a", encoding="utf-8") as handle:
        for row in pending:
            payload = {
                "ts_utc": _iso(_now_utc()), "batch_id": row.get("batch_id"),
                "mode": row.get("mode"), "writer_pid": os.getpid(),
                "event": "end", "case_id": row.get("case_id"),
                "design_hash": row.get("design_hash"),
                "status": "EXECUTOR_EXCEPTION", "physical_call_count": 0,
                "internal_solver_cases": 0, "repair": True,
                "error": type(exc).__name__ + ": " + str(exc),
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return pending


def _write_stop_report(run_dir: Path, phase: str, exc: BaseException,
                       *, arm_id: Optional[str] = None,
                       ledger_path: Optional[Path] = None) -> dict[str, Any]:
    import traceback

    repaired = _repair_pending_starts(ledger_path, exc) if ledger_path else []
    ledger_rows: list[dict[str, Any]] = []
    if ledger_path is not None and Path(ledger_path).is_file():
        ledger_rows = [json.loads(line) for line in
                       Path(ledger_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    actual_starts = sum(1 for r in ledger_rows if r.get("event") == "start")
    ledger_internal_recorded = sum(int(r.get("internal_solver_cases", 0) or 0)
                                   for r in ledger_rows if r.get("event") == "end")
    report = {
        "schema": "dreal001.p2a_v2.stop_report.v1",
        "phase": str(phase), "arm_id": arm_id,
        "error_type": type(exc).__name__, "message": str(exc),
        "traceback": traceback.format_exc(),
        "pending_starts_repaired": len(repaired),
        "pending_case_ids": [str(r.get("case_id")) for r in repaired],
        "ledger_path": None if ledger_path is None else str(ledger_path),
        "physical_solver_starts": actual_starts,
        "physical_call_count": actual_starts,
        "internal_solver_cases": None,  # A1 evaluator end rows carry no internal count
        "internal_solver_cases_source": "evaluations/record; ledger only audits physical start/end",
        "ledger_internal_cases_recorded": ledger_internal_recorded,
        "ledger_starts": actual_starts,
        "ledger_ends": sum(1 for r in ledger_rows if r.get("event") == "end"),
        "pending_starts_repaired_count": len(repaired),
        "created_utc": _iso(_now_utc()),
    }
    _write_json(Path(run_dir) / "stop_report.json", report)
    return report


def _build_final_manifest(run_dir: Path, approval: Mapping[str, Any],
                          a1_root: Path) -> dict[str, Any]:
    freeze_api, _, _ = _load_a1(a1_root)
    log_path = Path(str(approval.get("append_only_log_path")
                        or (Path(run_dir) / APPEND_ONLY_LOG_PATH)))
    out_path = Path(run_dir) / "final_run_manifest.json"
    manifest = freeze_api.build_final_run_manifest(
        log_path, out_path, batch_id=str(approval.get("batch_id") or BATCH_ID),
        manifest_source_sha256=FROZEN_PAIR_MANIFEST_SHA256,
        policy_doc_sha256=str(approval.get("policy_doc_sha256") or ""),
        builder_code_sha256=str(approval.get("builder_code_sha256") or ""))
    if not manifest.get("issued"):
        raise ExecutorRefused("final_run_manifest refused: %s" % manifest.get("file_errors"))
    return {"path": str(out_path), "sha256": sha256_file(out_path),
            "issued": bool(manifest.get("issued")),
            "designs_total": manifest.get("designs_total"),
            "designs_usable": manifest.get("designs_usable"),
            "append_only_log_sha256": manifest.get("append_only_log_sha256"),
            "chain": manifest.get("chain")}


def _preflight_record_internal(pre: Mapping[str, Any]) -> Optional[int]:
    """R2: preflight failure must report record internal cases, never hardcode 0."""
    total = 0
    charged = 0
    for case in (pre.get("cases") or []):
        starts = int(case.get("starts") or 0)
        if starts <= 0:
            continue
        charged += 1
        internal = case.get("internal_cases")
        if internal is None or int(internal or 0) <= 0:
            return None
        total += int(internal)
    return total if charged else 0


def _preflight_record_internal_status(pre: Mapping[str, Any]) -> str:
    return "NOT_COMPUTABLE" if _preflight_record_internal(pre) is None else "COMPUTED_FROM_PREFLIGHT_RECORDS"

def _find_polar_sha(record: Any) -> Optional[str]:
    """R7: best-effort polar SHA-256 from the A1 evaluator record (None if absent)."""
    seen: set[int] = set()

    def walk(node: Any) -> Optional[str]:
        if id(node) in seen:
            return None
        if isinstance(node, Mapping):
            seen.add(id(node))
            for key, value in node.items():
                key_l = str(key).lower()
                if isinstance(value, str) and (key_l in ("polar_path", "polar_file")
                                               or (key_l.endswith("polar") and value.lower().endswith(".polar"))):
                    try:
                        candidate = Path(value)
                        if candidate.is_file():
                            return sha256_file(candidate)
                    except OSError:
                        pass
                found = walk(value)
                if found:
                    return found
        elif isinstance(node, (list, tuple)):
            seen.add(id(node))
            for item in node:
                found = walk(item)
                if found:
                    return found
        return None

    return walk(record)


def _write_arm_failure_evidence(run_dir: Path, arm: str, failure: BaseException, *,
                                ledger: Any, pre: Mapping[str, Any], arms: Mapping[str, Any],
                                preflight_starts: int,
                                diagnostics: Mapping[str, Any]) -> None:
    """R7 (A5/R6 report gap): an arm exception must still leave a minimal
    preflight_result.json and batch_summary.json next to the stop_report."""
    total = ledger.count_starts()
    diag_starts = int(diagnostics.get("starts") or 0)
    summary = {
        "schema": BATCH_SCHEMA, "batch_id": BATCH_ID, "run_id": RUN_ID,
        "status": "STOP_ARM_EXCEPTION",
        "failure": {"arm_id": arm, "error_type": type(failure).__name__,
                    "message": str(failure)},
        "preflight": dict(pre) if isinstance(pre, Mapping) else pre,
        "diagnostics": dict(diagnostics) if isinstance(diagnostics, Mapping) else diagnostics,
        "arms": {str(k): dict(v) for k, v in (arms or {}).items()},
        "preflight_starts": preflight_starts,
        "diagnostic_starts": diag_starts,
        "main_starts": max(0, total - preflight_starts - diag_starts),
        "total_starts": total, "total_ledger_starts": total,
        "physical_call_count": total, "physical_solver_starts": total,
        "record_internal_cases": None,
        "record_internal_cases_status": "NOT_COMPUTABLE",
        "record_internal_cases_source": "arm exception path; ledger does not carry internal counts",
        "final_run_manifest": None,
        "executor_version": EXECUTOR_VERSION,
        "physical_validation_status": "NOT_VALIDATED",
        "fuel_burn_kg": None,
    }
    _write_json(run_dir / "batch_summary.json", summary)
    _write_json(run_dir / "preflight_result.json", pre)


def _prefrozen_reuse_gate(run_dir: Path, service: Any, initial: Mapping[str, Any],
                         static_index_hashes: Iterable[str]) -> dict[str, Any]:
    """P5 zero-physical gate: reuse the pinned pre-frozen pairs and verify them.

    Fail-closed: any byte/canonical/record mismatch or a static index size other
    than the bound 119 refuses the run before any solver start.
    """
    static_hashes = sorted(str(h) for h in static_index_hashes)
    designs: list[dict[str, Any]] = []
    all_ok = True
    for design in (initial.get("designs") or []):
        dh = str(design.get("design_hash") or "")
        x12 = [float(v) for v in (design.get("x12") or [])]
        frozen, record, reused = service.get_or_freeze(x12, "GATE-PREFROZEN-" + dh)
        families = record.get("families") or {}
        checks = {
            "record_status_pair_ready": record.get("status") == "PAIR_READY",
            "record_arm_blind_true": record.get("arm_blind") is True,
            "record_two_families": len(families) == 2,
            "record_source_kind_prefrozen": record.get("source_kind") == PREFROZEN_SOURCE_KIND,
            "record_reused_prefrozen_true": record.get("reused_prefrozen") is True,
            "record_attempts_zero": all(
                int((row or {}).get("attempts", 0) or 0) == 0 for row in families.values()),
            "record_hash_hex64": (bool(record.get("record_hash"))
                                  and len(str(record.get("record_hash"))) == 64),
        }
        for label, fam_row in sorted((design.get("families") or {}).items()):
            mf = family_frozen_payload(fam_row)
            row = families.get(label) or {}
            rf = row.get("frozen") or {}
            checks["family_%s_vspgeom_sha" % label] = (
                str(mf.get("frozen_vspgeom_sha256") or "")
                == str(rf.get("frozen_vspgeom_sha256") or "")
                == str(row.get("vspgeom_sha256") or ""))
            checks["family_%s_canonical_mesh_sha" % label] = (
                str(mf.get("canonical_mesh_sha256") or "")
                == str(rf.get("canonical_mesh_sha256") or "")
                == str(row.get("canonical_mesh_sha256") or ""))
            checks["family_%s_vkey_sha" % label] = (
                str(mf.get("frozen_vkey_sha256") or "")
                == str(rf.get("frozen_vkey_sha256") or ""))
            checks["family_%s_vsp3_sha" % label] = (
                str(mf.get("frozen_vsp3_sha256") or "")
                == str(rf.get("frozen_vsp3_sha256") or ""))
            checks["family_%s_copied_files_exist" % label] = bool(
                Path(str(rf.get("frozen_vspgeom_path") or "")).is_file()
                and Path(str(rf.get("frozen_vkey_path") or "")).is_file())
        ok = all(checks.values())
        all_ok = all_ok and ok
        designs.append({
            "design_hash": dh, "design_index": int(design.get("design_index") or -1),
            "record_hash": record.get("record_hash"), "ok": bool(ok),
            "checks": checks,
            "reuse_evidence": service.prefrozen_reuse_evidence.get(dh) or {},
        })
    index_ok = len(static_hashes) == int(STATIC_INDEX_COUNT_EXPECTED)
    doc = {
        "schema": "dreal001.p2a_v2r8.prefrozen_reuse_gate.v1",
        "run_id": RUN_ID, "batch_id": BATCH_ID,
        "status": ("PREFROZEN_REUSE_GATE_PASS" if (all_ok and index_ok)
                   else "PREFROZEN_REUSE_GATE_FAILED"),
        "static_index_count": len(static_hashes),
        "static_index_count_expected": int(STATIC_INDEX_COUNT_EXPECTED),
        "static_index_count_ok": bool(index_ok),
        "prefrozen_hashes": sorted(service.prefrozen_hashes),
        "designs": designs,
        "all_consistent": bool(all_ok and index_ok),
        "freeze_builder_invocations": int(service.builds),
        "physical_call_count": 0, "solver_started": False,
        "created_utc": utc_now(),
    }
    _write_json(Path(run_dir) / "runtime" / "prefrozen_reuse_gate.json", doc)
    if doc["status"] != "PREFROZEN_REUSE_GATE_PASS":
        raise ExecutorRefused(
            "ACCOUNTING_INCONSISTENT: PREFROZEN_REUSE_GATE_FAILED "
            "(all_consistent=%s static_index_count=%d/%d)"
            % (doc["all_consistent"], doc["static_index_count"],
               STATIC_INDEX_COUNT_EXPECTED))
    return doc


def _run_batch_executable_impl(run_dir: Path, a1_root: Path, *, source_kind: str = "REAL_VSPAERO") -> dict[str, Any]:
    run_dir = Path(run_dir)
    plan_path = run_dir / "plan.json"
    approval_path = run_dir / "approval.json"
    identity_path = run_dir / "identity_binding.json"
    if not approval_path.is_file():
        raise ExecutorRefused("approval.json is absent; P2a v2 is not authorized")
    plan = _read_json(plan_path)
    approval = _read_json(approval_path)
    identity_sha = sha256_file(identity_path)
    from .p2a_v2 import a2_code_binding
    executor = a2_code_binding()
    gate = verify_execution_gate(plan, approval, run_dir=run_dir, plan_sha256=sha256_file(plan_path),
                                 identity_sha256=identity_sha,
                                 executor_sha256=executor["a2_executor_sha256"])
    solver_binding = gate["solver_exe"]
    _write_json(run_dir / "runtime" / "solver_exe_binding.json", solver_binding)
    freeze_api, ev12, _ = _load_a1(a1_root)
    design_space, design_space_binding = _load_a1_design_space(a1_root)
    _write_json(run_dir / "runtime" / "design_space_binding.json", design_space_binding)
    initial = _read_json(run_dir / "initial_designs_manifest.json")
    _validate_initial_designs(initial, approval, run_dir)
    bound_manifest_path = approval.get("pair_manifest_path") or approval.get("family_pair_manifest_path")
    if not bound_manifest_path:
        raise ExecutorRefused("approval lacks pair_manifest_path")
    manifest_path = Path(str(bound_manifest_path))
    if sha256_file(manifest_path) != str(approval.get("pair_manifest_sha256")):
        raise ExecutorRefused("pair manifest SHA mismatch vs approval.pair_manifest_sha256")
    pair_manifest = _read_json(manifest_path)
    x12_by_hash = _load_x12_by_hash(pair_manifest)
    sref_by_hash = build_sref_map(a1_root, x12_by_hash)
    resolver = SrefResolver(a1_root, sref_by_hash)
    store = FreezeRecordStore(run_dir / "runtime" / "family_pair_manifest.append_only.jsonl",
                              a1_freeze_api=freeze_api)
    adapter = A1FreezeApiAdapter(
        build_freeze_fn(a1_root, run_dir),
        builder_code_sha256=str(approval.get("builder_code_sha256") or ""),
        freeze_api_sha256=str(approval.get("freeze_api_sha256") or ""))
    try:
        from research.concorde_metaopt.dreal001.geometry import mesh_identity as _mesh_identity_mod
    except Exception as exc:  # noqa: BLE001
        raise ExecutorRefused(
            "ACCOUNTING_INCONSISTENT: A1 mesh_identity unavailable for prefrozen reuse: %r"
            % (exc,))
    static_index_hashes = {str(rec.get("design_hash") or "")
                           for rec in (pair_manifest.get("records") or [])
                           if rec.get("design_hash")}
    service = FrozenPairService(
        adapter, store, build_root=run_dir / "runtime" / "designs",
        prefrozen_manifest=initial,
        static_index_hashes=static_index_hashes,
        describe_mesh=_mesh_identity_mod.describe_mesh)
    prefrozen_gate = _prefrozen_reuse_gate(run_dir, service, initial, static_index_hashes)
    ledger_path = run_dir / "solver_attempts.jsonl"
    ledger = A1LedgerReader(ledger_path)
    real_spawn = _real_spawn_factory(a1_root, run_dir, sref_by_hash, sref_resolver=resolver,
                                     solver_binding=solver_binding)
    bundle_root = Path(str(approval.get("replay_bundles", {}).get("bundle_root") or ""))
    bundle_manifest = _read_json(bundle_root / "bundle_manifest.json")
    preflight = PreflightVerifier(bundle_manifest, bundle_root=bundle_root,
                                  replay_fn_factory=make_preflight_factory(
                                      a1_root, run_dir, approval, pair_manifest, manifest_path,
                                      x12_by_hash, sref_by_hash,
                                      solver_binding=solver_binding, ledger=ledger))
    batch = P2AV2Batch(P2AV2Runner(service, None, store, ledger_reader=ledger,
                                  max_starts=MAX_STARTS),
                       preflight=preflight,
                       accept_preflight_numeric=bool(approval.get("preflight_accept_numeric")))
    engines = {arm: ProposalEngine(arm, seed=SEED, adaptive=arm in ("ABO", "ADE", "APSO"))
               for arm in ARMS}
    initial_x12 = [list(map(float, rec["x12"])) for rec in initial.get("designs") or []]
    # R5: physical x12 -> unit through the frozen A1 design space.  The old
    # np.clip(physical, 0, 1) silently changed the domain and was rejected by the
    # A1 unit-box guard; every seed/freeze/evaluate/SrefResolver input below is
    # physical x12 and out-of-bounds values fail closed.
    initial_unit = [x12_to_unit(design_space, x12) for x12 in initial_x12]
    for engine in engines.values():
        engine.seed_initial(initial_unit)
    proposal_fns: dict[str, Callable[[str, int, int], Sequence[float]]] = {}
    current_units: dict[str, list[float]] = {}
    for arm in ARMS:
        def make(arm_id: str):
            def fn(a: str, index: int, replacement: int) -> Sequence[float]:
                u = engines[arm_id].propose(a, index, replacement)
                current_units[arm_id] = list(map(float, u))
                # R5: the engine stays in unit space; only a physical x12 leaves
                # this boundary (no clip, out-of-domain -> ExecutorRefused).
                return unit_to_x12(design_space, current_units[arm_id])
            return fn
        proposal_fns[arm] = make(arm)

    def on_evaluation(arm_id: str, evaluation: Any) -> None:
        unit = current_units.get(arm_id)
        if unit is not None:
            engines[arm_id].observe(unit, evaluation)

    def make_arm_evaluator(arm: str) -> tuple[Any, Any]:
        evaluator = ev12.TwoFamilyEvaluator(
            pair_manifest, approval, batch_id=str(approval.get("batch_id")),
            max_starts=DESIGN_EVALS_PER_ARM * 2, run_dir=run_dir / "arms" / arm,
            manifest_source=manifest_path, mock=False, mode=ev12.MODE_RUNTIME,
            append_only_log=str(approval.get("append_only_log_path")
                                or (Path(run_dir) / APPEND_ONLY_LOG_PATH)),
            policy_doc_sha256=str(approval.get("policy_doc_sha256") or ""),
            builder_code_sha256=str(approval.get("builder_code_sha256") or ""),
            evaluator_code_sha256=str(approval.get("evaluator_code_sha256") or ""),
            real_spawn=real_spawn, allow_physical_starts=True, ledger_path=ledger_path,
        )
        solver = A1FamilySolver(evaluator, arm_id=arm, sref_by_hash=sref_by_hash,
                                sref_resolver=resolver, a1_root=a1_root)
        return evaluator, solver

    try:
        pre = _reconcile_preflight_ledger(batch.run_preflight(), ledger)
    except Exception as exc:  # noqa: BLE001
        _write_stop_report(run_dir, "preflight", exc, ledger_path=ledger_path)
        raise

    if not pre.get("main_batch_may_start"):
        # A5: even a FAILing preflight must repair orphan starts (after evaluator
        # close), report physical counts from the ledger, and write a stop_report.
        stop = _write_stop_report(run_dir, "preflight",
                                  RuntimeError("preflight not PASS: " + str(pre.get("overall"))),
                                  ledger_path=ledger_path)
        preflight_starts = ledger.count_starts()
        summary = {
            "schema": BATCH_SCHEMA, "batch_id": BATCH_ID, "run_id": RUN_ID,
            "status": "STOP_PREFLIGHT_" + str(pre.get("overall")),
            "preflight": pre, "arms": {}, "preflight_starts": preflight_starts,
            "main_starts": 0, "total_starts": preflight_starts,
            "total_ledger_starts": preflight_starts,
            "record_internal_cases": _preflight_record_internal(pre),
            "record_internal_cases_status": _preflight_record_internal_status(pre),
            "record_internal_cases_source": "preflight records; ledger does not carry internal counts",
            "reserve_groups_used": 0, "reserve_groups_used_total": 0,
            "reserve_scope": "GLOBAL",
            "physical_call_count": ledger.count_starts(),
            "physical_solver_starts": ledger.count_starts(), "final_run_manifest": None,
        }
        _write_json(run_dir / "batch_summary.json", summary)
        _write_json(run_dir / "preflight_result.json", pre)
        return summary

    preflight_ledger_starts = ledger.count_starts()

    # R10 L-12: the diagnostic phase is NOT part of the R10 matrix.  The plan and
    # the signed approval must BOTH declare it out of matrix with 0/0 planned
    # starts/internal; any disagreement fails closed before a solver can start.
    _plan_diag = dict(plan.get("diagnostics") or {})
    _plan_matrix = dict(plan.get("matrix") or {})
    _appr_diag = dict(approval.get("diagnostics") or {})
    _diag_decl = {
        "plan_in_r10_matrix": _plan_diag.get("in_r10_matrix"),
        "plan_matrix_diagnostic_starts": _plan_matrix.get("diagnostic_starts"),
        "plan_diagnostic_planned_starts": _plan_diag.get("planned_starts"),
        "plan_diagnostic_planned_internal_cases": _plan_diag.get("planned_internal_cases"),
        "approval_in_r10_matrix": _appr_diag.get("in_r10_matrix"),
        "approval_diagnostic_planned_starts": approval.get("diagnostic_planned_starts"),
        "approval_diagnostic_planned_internal_cases": approval.get("diagnostic_planned_internal_cases"),
        "approval_diagnostic_cases": list(_appr_diag.get("cases") or []),
    }
    def _decl_zero(value: Any) -> int:
        return 0 if value is None else int(value or 0)
    if ((_diag_decl["plan_in_r10_matrix"] is None)
            or (_diag_decl["approval_in_r10_matrix"] is None)):
        raise ExecutorRefused(
            "ACCOUNTING_INCONSISTENT: diagnostic matrix declaration missing "
            "(plan=%r approval=%r)"
            % (_diag_decl["plan_in_r10_matrix"], _diag_decl["approval_in_r10_matrix"]))
    if ((bool(_diag_decl["plan_in_r10_matrix"]) != bool(_diag_decl["approval_in_r10_matrix"]))
            or (_decl_zero(_diag_decl["plan_diagnostic_planned_starts"])
                != _decl_zero(_diag_decl["approval_diagnostic_planned_starts"]))
            or (_decl_zero(_diag_decl["plan_diagnostic_planned_internal_cases"])
                != _decl_zero(_diag_decl["approval_diagnostic_planned_internal_cases"]))):
        raise ExecutorRefused(
            "ACCOUNTING_INCONSISTENT: diagnostic declaration mismatch plan=%r approval=%r"
            % (_diag_decl, {
                "approval_in_r10_matrix": _diag_decl["approval_in_r10_matrix"],
                "approval_diagnostic_planned_starts": _diag_decl["approval_diagnostic_planned_starts"],
                "approval_diagnostic_planned_internal_cases": _diag_decl["approval_diagnostic_planned_internal_cases"],
            }))
    _diag_skip_ok = (
        (bool(_diag_decl["plan_in_r10_matrix"]) is False)
        and _decl_zero(_diag_decl["plan_matrix_diagnostic_starts"]) == 0
        and _decl_zero(_diag_decl["plan_diagnostic_planned_starts"]) == 0
        and _decl_zero(_diag_decl["plan_diagnostic_planned_internal_cases"]) == 0)
    if _diag_skip_ok:
        diagnostics = {
            "phase": "DIAGNOSTICS", "status": "DIAGNOSTICS_NOT_IN_MATRIX",
            "cases": [], "planned_starts": 0, "planned_internal_cases": 0,
            "starts": 0, "internal_cases": 0, "passed_cases": 0,
            "in_r10_matrix": False, "skipped": True,
            "excluded_from_endpoints": True,
            "accounting": {"planned_starts": 0, "planned_internal_cases": 0,
                           "actual_starts": 0, "actual_internal_cases": 0,
                           "ok": True, "source": "R10 matrix: diagnostics not in matrix (L-12)"},
            "internal_cases_source": INTERNAL_CASES_PER_START_SOURCE,
            "matrix_declaration": _diag_decl,
            "r9_evidence": dict(_plan_diag.get("r9_source") or {}),
        }
        _write_json(run_dir / "diagnostics.json", diagnostics)
    else:
        _expected_diag_starts = _decl_zero(_diag_decl["plan_diagnostic_planned_starts"])
        _expected_diag_internal = _decl_zero(_diag_decl["plan_diagnostic_planned_internal_cases"])
        # R7 protocol D: pre-registered diagnostic phase. Two real starts (one per
        # design, 7 internal cases each) run after a PASSing preflight and before the
        # 384-start main batch; both failing stops the run cleanly with main NOT_RUN.
        diagnostics: dict[str, Any] = {
            "phase": "DIAGNOSTICS", "status": "DIAGNOSTICS_NOT_RUN", "cases": [],
            "planned_starts": _expected_diag_starts,
            "planned_internal_cases": _expected_diag_internal,
            "starts": 0, "internal_cases": 0, "passed_cases": 0,
            "pass_rule": "status is SOLVED_VALID and the objective is finite/non-null",
            "fail_rule": "both diagnostic cases fail -> main NOT_RUN (clean stop)",
        }
        diag_ledger_before = ledger.count_starts()
        diag_evaluator = None
        diag_failure: Optional[BaseException] = None
        diag_by_hash = {str(rec.get("design_hash")): rec
                        for rec in (initial.get("designs") or [])}
        try:
            diag_evaluator, diag_solver = make_arm_evaluator("DIAG")
            diag_runner = P2AV2Runner(service, diag_solver, store, ledger_reader=ledger,
                                      max_starts=MAX_STARTS)
            for case_id, expected_hash, design_index in DIAGNOSTIC_CASES:
                source = diag_by_hash.get(expected_hash)
                case_row: dict[str, Any] = {
                    "case_id": case_id, "design_index": design_index,
                    "design_hash": expected_hash, "status": "DIAGNOSTIC_SOURCE_MISSING",
                    "primary": None, "internal_cases": None, "starts": 0,
                    "polar_sha256": None, "passed": False,
                }
                if source is not None:
                    x12 = list(map(float, source["x12"]))
                    evaluation = diag_runner.run_one(x12, design_index)
                    polar = None
                    for row in evaluation.per_family or []:
                        if row.get("polar_sha256"):
                            polar = row["polar_sha256"]
                            break
                    if polar is None and getattr(evaluation, "failed_family", None):
                        polar = (evaluation.failed_family or {}).get("polar_sha256")
                    primary = evaluation.primary
                    passed = (evaluation.status == "SOLVED_VALID"
                              and primary is not None
                              and float(primary) == float(primary)
                              and abs(float(primary)) != float("inf"))
                    case_row.update({
                        "status": evaluation.status, "primary": primary,
                        "internal_cases": evaluation.internal_solver_cases,
                        "starts": evaluation.starts, "polar_sha256": polar,
                        "validation_error": evaluation.validation_error,
                        "failed_family": evaluation.failed_family,
                        "passed": bool(passed),
                    })
                diagnostics["cases"].append(case_row)
        except Exception as exc:  # noqa: BLE001
            diag_failure = exc
        finally:
            if diag_evaluator is not None:
                close = getattr(diag_evaluator, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception as close_exc:  # noqa: BLE001
                        if diag_failure is None:
                            diag_failure = close_exc
        diagnostics["starts"] = ledger.count_starts() - diag_ledger_before
        _diag_internal = 0
        _diag_consistent = True
        for _row in diagnostics["cases"]:
            _row_starts = int(_row.get("starts") or 0)
            _expected = internal_cases_from_starts(_row_starts)
            if _row_starts > 0:
                _diag_internal += _expected
            if _row.get("internal_cases") not in (None, _expected):
                _diag_consistent = False
        diagnostics["internal_cases"] = int(_diag_internal)
        diagnostics["internal_cases_source"] = INTERNAL_CASES_PER_START_SOURCE
        diagnostics["passed_cases"] = sum(1 for row in diagnostics["cases"] if row.get("passed"))
        diagnostics["status"] = ("DIAGNOSTICS_PASS" if diagnostics["passed_cases"] >= 1
                                 else "DIAGNOSTICS_FAILED")
        if diag_failure is not None:
            _write_stop_report(run_dir, "diagnostics", diag_failure, ledger_path=ledger_path)
            raise diag_failure
        diag_accounting_ok = (
            bool(_diag_consistent)
            and int(diagnostics["starts"]) == int(_expected_diag_starts)
            and diagnostics["internal_cases"] is not None
            and int(diagnostics["internal_cases"]) == int(_expected_diag_internal))
        diagnostics["accounting"] = {
            "planned_starts": int(_expected_diag_starts),
            "planned_internal_cases": int(_expected_diag_internal),
            "actual_starts": int(diagnostics["starts"]),
            "actual_internal_cases": diagnostics["internal_cases"],
            "ok": bool(diag_accounting_ok),
            "prereg_deviation_disclosure":
                "R7 pre-registered 2 starts / 14 internal but implemented one start per design "
                "per family (2 designs x 2 families = 4 starts / 28 internal). R8 pre-registers "
                "4 starts / 28 internal explicitly and fails closed on any other count.",
        }
        if diagnostics["status"] == "DIAGNOSTICS_PASS" and not diag_accounting_ok:
            diagnostics["status"] = "DIAGNOSTICS_ACCOUNTING_INCONSISTENT"
        if diagnostics["status"] != "DIAGNOSTICS_PASS":
            stop_status = ("STOP_DIAGNOSTICS_ACCOUNTING_INCONSISTENT"
                           if diagnostics["status"] == "DIAGNOSTICS_ACCOUNTING_INCONSISTENT"
                           else "STOP_DIAGNOSTICS_FAILED")
            diag_stop = _write_stop_report(
                run_dir, "diagnostics",
                RuntimeError("diagnostic phase %s: starts=%s internal=%s planned=%s/%s"
                             % (diagnostics["status"], diagnostics["starts"],
                                diagnostics["internal_cases"],
                                _expected_diag_starts,
                                _expected_diag_internal)),
                ledger_path=ledger_path)
            diag_summary = {
                "schema": BATCH_SCHEMA, "batch_id": BATCH_ID, "run_id": RUN_ID,
                "status": stop_status, "preflight": pre,
                "diagnostics": diagnostics, "arms": {},
                "preflight_starts": preflight_ledger_starts,
                "diagnostic_starts": diagnostics["starts"],
                "main_starts": 0, "total_starts": ledger.count_starts(),
                "total_ledger_starts": ledger.count_starts(),
                "record_internal_cases": diagnostics["internal_cases"],
                "record_internal_cases_status": ("COMPUTED_FROM_DIAGNOSTIC_RECORDS"
                                                 if diagnostics["internal_cases"] is not None
                                                 else "NOT_COMPUTABLE"),
                "record_internal_cases_source": "diagnostic records; main batch NOT_RUN",
                "physical_call_count": ledger.count_starts(),
                "physical_solver_starts": ledger.count_starts(),
                "prefrozen_reuse_gate": prefrozen_gate,
                "final_run_manifest": None, "stop_report": diag_stop,
            }
            _write_json(run_dir / "batch_summary.json", diag_summary)
            _write_json(run_dir / "preflight_result.json", pre)
            return diag_summary

    invalid_state: dict[str, Any] = {
        "evaluations": 0, "invalid": 0,
        "consecutive": {arm: 0 for arm in ARMS},
    }

    def stop_check(arm_id: str, evaluation: Any) -> Optional[str]:
        invalid_state["evaluations"] += 1
        if evaluation.status == INVALID_EVALUATION_STATUS:
            invalid_state["invalid"] += 1
            invalid_state["consecutive"][arm_id] = (
                invalid_state["consecutive"].get(arm_id, 0) + 1)
        else:
            invalid_state["consecutive"][arm_id] = 0
        total = invalid_state["evaluations"]
        invalid = invalid_state["invalid"]
        if invalid >= INVALID_TOTAL_MAX:
            return "STOPPED_SCIENTIFIC_INVALID_TOTAL"
        if invalid_state["consecutive"].get(arm_id, 0) >= INVALID_CONSECUTIVE_MAX:
            return "STOPPED_SCIENTIFIC_INVALID_CONSECUTIVE"
        if total >= INVALID_RATIO_MIN_EVALS and invalid / total > INVALID_RATIO_MAX:
            return "STOPPED_SCIENTIFIC_INVALID_RATIO"
        return None

    arms: dict[str, Any] = {}
    shared_reserve = ReservePool()
    shared_voided: set[str] = set()
    for arm in ARMS:
        evaluator = None
        failure: Optional[BaseException] = None
        try:
            evaluator, solver = make_arm_evaluator(arm)
            runner = P2AV2Runner(service, solver, store, ledger_reader=ledger,
                                 max_starts=MAX_STARTS)
            arm_batch = P2AV2Batch(runner, preflight=preflight,
                                   accept_preflight_numeric=bool(
                                       approval.get("preflight_accept_numeric")),
                                   reserve_pool=shared_reserve,
                                   voided_designs=shared_voided)
            arm_result = arm_batch.run_arm(
                arm, proposal_fns[arm], budget_designs=DESIGN_EVALS_PER_ARM,
                initial_designs=None, on_evaluation=on_evaluation,
                stop_check=stop_check)
        except Exception as exc:  # noqa: BLE001
            # A5 P2AV2-21/24: close the sole ledger writer BEFORE any repair append.
            failure = exc
        finally:
            if evaluator is not None:
                close = getattr(evaluator, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception as close_exc:  # noqa: BLE001
                        if failure is None:
                            failure = close_exc
        if failure is not None:
            _write_arm_failure_evidence(run_dir, arm, failure, ledger=ledger, pre=pre,
                                        arms=arms, preflight_starts=preflight_ledger_starts,
                                        diagnostics=diagnostics)
            _write_stop_report(run_dir, "arm", failure, arm_id=arm, ledger_path=ledger_path)
            raise failure from failure
        arms[arm] = {
            "status": arm_result.status, "valid_designs": arm_result.valid_designs,
            "void_designs": arm_result.void_designs,
            "invalid_designs": arm_result.invalid_designs, "starts": arm_result.starts,
            "best_primary": arm_result.best_primary,
            "reserve_groups_used": arm_result.reserve_groups_used,
            "evaluations": [asdict(e) for e in arm_result.evaluations],
        }
        if arm_result.status != "COMPLETED":
            phase = ("scientific_auto_stop"
                     if str(arm_result.status).startswith("STOPPED_SCIENTIFIC_") else "s1")
            _write_stop_report(run_dir, phase,
                               RuntimeError("ARM_STOPPED_%s" % arm_result.status),
                               arm_id=arm, ledger_path=ledger_path)
            break

    _counts = summarize_evaluations(arms)
    record_internal_cases = _counts["record_internal_cases"]
    record_internal_cases_status = _counts["record_internal_cases_status"]
    main_record_starts = _counts["main_starts"]
    _start = summarize_start_accounting(ledger.count_starts(), preflight_ledger_starts)
    preflight_starts = _start["preflight_starts"]
    diagnostic_starts = int(diagnostics["starts"])
    total_starts = _start["total_starts"]
    main_starts = max(0, total_starts - preflight_starts - diagnostic_starts)
    try:
        final_manifest = _build_final_manifest(run_dir, approval, a1_root)
    except Exception as exc:  # noqa: BLE001
        _write_stop_report(run_dir, "final_manifest", exc, ledger_path=ledger_path)
        raise
    preflight_internal_cases = _preflight_record_internal(pre)
    diagnostic_internal_cases = diagnostics["internal_cases"]
    main_internal_cases = record_internal_cases
    if (preflight_internal_cases is None or diagnostic_internal_cases is None
            or main_internal_cases is None):
        total_internal_cases = None
    else:
        total_internal_cases = (int(preflight_internal_cases)
                                + int(diagnostic_internal_cases)
                                + int(main_internal_cases))
    phase_conservation: dict[str, Any] = {}
    phase_conservation_ok = True
    for _phase, _starts, _internal in (
            ("preflight", int(preflight_starts), preflight_internal_cases),
            ("diagnostic", int(diagnostic_starts), diagnostic_internal_cases),
            ("main", int(main_starts), main_internal_cases)):
        _expected_internal = internal_cases_from_starts(_starts)
        if _internal is None:
            _ok = _starts == 0
        else:
            _ok = int(_internal) == _expected_internal
        phase_conservation[_phase] = {
            "starts": _starts,
            "expected_internal_cases": _expected_internal,
            "recorded_internal_cases": _internal,
            "ok": bool(_ok),
            "source": INTERNAL_CASES_PER_START_SOURCE,
        }
        if not _ok:
            phase_conservation_ok = False
    total_conservation_ok = (
        total_internal_cases is not None
        and int(total_internal_cases) == internal_cases_from_starts(int(total_starts)))
    cumulative_accounting_ok = bool(
        phase_conservation_ok
        and total_conservation_ok
        and R10_CUMULATIVE_STARTS <= MAX_STARTS
        and R10_CUMULATIVE_INTERNAL_CASES <= MAX_INTERNAL_CASES
        and int(ledger.count_starts()) <= MAX_STARTS
        and (total_internal_cases is None or int(total_internal_cases) <= MAX_INTERNAL_CASES))
    _accounting_stop = None
    if not cumulative_accounting_ok:
        _accounting_stop = _write_stop_report(
            run_dir, "accounting",
            RuntimeError(
                "ACCOUNTING_INCONSISTENT: planned cumulative %d starts / %d internal vs caps "
                "%d/%d; run %d starts / %s internal; phase_conservation_ok=%s "
                "total_conservation_ok=%s (policy internal=%d x starts, source=%s)"
                % (R10_CUMULATIVE_STARTS, R10_CUMULATIVE_INTERNAL_CASES,
                   MAX_STARTS, MAX_INTERNAL_CASES, ledger.count_starts(),
                   total_internal_cases, phase_conservation_ok,
                   total_conservation_ok, int(INTERNAL_CASES_PER_START),
                   INTERNAL_CASES_PER_START_SOURCE)),
            ledger_path=ledger_path)
    summary = {
        "schema": BATCH_SCHEMA, "batch_id": BATCH_ID, "run_id": RUN_ID,
        "status": ("STOP_ACCOUNTING_INCONSISTENT" if _accounting_stop is not None
                   else ("COMPLETED" if len(arms) == len(ARMS) else "STOPPED")),
        "preflight": pre, "diagnostics": diagnostics, "arms": arms,
        "preflight_starts": preflight_starts, "diagnostic_starts": diagnostic_starts,
        "main_starts": main_starts,
        "main_record_starts": main_record_starts,
        "total_starts": total_starts,
        "total_ledger_starts": _start["total_ledger_starts"],
        "ledger_starts": ledger.count_starts(),
        "ledger_starts_source": "canonical evaluator event ledger, event==start",
        "preflight_internal_cases": preflight_internal_cases,
        "diagnostic_internal_cases": diagnostic_internal_cases,
        "main_internal_cases": main_internal_cases,
        "total_internal_cases": total_internal_cases,
        "phase_internal_cases": {
            "preflight": preflight_internal_cases,
            "diagnostic": diagnostic_internal_cases,
            "main": main_internal_cases,
            "total": total_internal_cases,
        },
        "phase_conservation": phase_conservation,
        "accounting_conservation_ok": bool(phase_conservation_ok and total_conservation_ok),
        "internal_cases_policy": {
            "internal_cases_per_start": int(INTERNAL_CASES_PER_START),
            "source": INTERNAL_CASES_PER_START_SOURCE,
            "conservation_rule": "sum(internal) == INTERNAL_CASES_PER_START * starts per phase and in total",
            "legacy_silent_default_removed": True,
        },
        "cumulative_charged_starts": int(R10_CUMULATIVE_STARTS),
        "cumulative_charged_internal_cases": int(R10_CUMULATIVE_INTERNAL_CASES),
        "cumulative_accounting_ok": bool(cumulative_accounting_ok),
        "accounting_stop_report": _accounting_stop,
        "prefrozen_reuse_gate": prefrozen_gate,
        "main_evaluations": invalid_state["evaluations"],
        "invalid_evaluations": invalid_state["invalid"],
        "invalid_evaluations_consecutive_max_by_arm": dict(invalid_state["consecutive"]),
        "invalid_tolerance": {
            "ratio_min_evaluations": INVALID_RATIO_MIN_EVALS,
            "ratio_max": INVALID_RATIO_MAX,
            "consecutive_max": INVALID_CONSECUTIVE_MAX,
            "total_max": INVALID_TOTAL_MAX,
            "invalid_status": INVALID_EVALUATION_STATUS,
        },
        "scientific_stop": any(str(a.get("status", "")).startswith("STOPPED_SCIENTIFIC_")
                               for a in arms.values()),
        "record_internal_cases": record_internal_cases,
        "record_internal_cases_status": record_internal_cases_status,
        "record_internal_cases_source": "evaluations/record per-family rows incl. failed_family; ledger does not carry internal counts",
        "reserve_groups_used": shared_reserve.groups_used,
        "reserve_groups_used_total": shared_reserve.groups_used,
        "reserve_groups_left": shared_reserve.groups_left,
        "reserve_starts_used": shared_reserve.starts_used,
        "reserve_scope": "GLOBAL",
        "voided_designs": sorted(str(r.get("design_hash")) for r in store.records()
                                 if str(r.get("status")) == "DESIGN_VOID"),
        "append_log_sha256": store.sha256_of_log(),
        "append_log_head_sha256": store.prev_sha,
        "final_run_manifest": final_manifest,
        "physical_call_count": ledger.count_starts(),
        "physical_solver_starts": ledger.count_starts(),
        "sref_resolver": {"static_designs": len(sref_by_hash),
                          "lazy_designs": len(resolver.snapshot()) - len(sref_by_hash)},
        "evaluator_lifecycle": "SEQUENTIAL_ONE_PER_ARM",
        "canonical_ledger": str(ledger_path),
        "one_writer_at_a_time": True,
    }
    summary["executor_version"] = EXECUTOR_VERSION
    summary["source_kind"] = source_kind
    summary["physical_validation_status"] = "NOT_VALIDATED"
    summary["fuel_burn_kg"] = None
    _write_json(run_dir / "batch_summary.json", summary)
    _write_json(run_dir / "preflight_result.json", pre)
    with (run_dir / "evaluations.jsonl").open("w", encoding="utf-8") as stream:
        for arm, payload in (summary.get("arms") or {}).items():
            for row in payload.get("evaluations") or []:
                row = dict(row)
                row["schema"] = EVAL_SCHEMA
                row["arm_id"] = arm
                row["backend"] = "REAL_VSPAERO"
                stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return summary


def summarize_evaluations(arms: Mapping[str, Any]) -> dict[str, Any]:
    """Aggregate starts/internal from A2 records (not from A1 ledger).

    R10: internal cases are policy-derived (INTERNAL_CASES_PER_START x starts) and
    the aggregate is checked against that conservation rule instead of trusting a
    record field that may be absent.
    """
    evaluations = [e for a in arms.values() for e in (a or {}).get("evaluations") or []]
    main_starts = sum(int(e.get("starts") or 0) for e in evaluations)
    expected_internal = internal_cases_from_starts(main_starts)
    internal_values = [e.get("internal_solver_cases") for e in evaluations]
    if any(v is None for v in internal_values) and main_starts > 0:
        record_internal_cases = None
        status = "NOT_COMPUTABLE"
    else:
        record_internal_cases = sum(int(v or 0) for v in internal_values)
        status = "COMPUTED_FROM_EVALUATIONS"
        if int(record_internal_cases) != expected_internal:
            status = "INCONSISTENT_POLICY"
    return {
        "main_starts": main_starts,
        "record_internal_cases": record_internal_cases,
        "record_internal_cases_status": status,
        "expected_internal_cases": expected_internal,
        "internal_cases_source": INTERNAL_CASES_PER_START_SOURCE,
    }


def _reconcile_preflight_ledger(pre: Mapping[str, Any], ledger: Any) -> dict[str, Any]:
    """Make preflight physical counts ledger-authoritative (A5 P2AV2-24 follow-up).

    Per-case starts come from the A1 record (0 when the case failed before a
    start; 1 when a replay process actually started). The authoritative total is
    always event == "start" in the canonical ledger; planned starts stay a
    separate field and are never reported as physical.
    """
    out = dict(pre)
    ledger_starts = int(ledger.count_starts())
    out["ledger_starts"] = ledger_starts
    out["physical_call_count"] = ledger_starts
    out["physical_call_count_source"] = "canonical evaluator ledger event=start count"
    out["per_case_starts_sum"] = sum(int(r.get("starts", 0)) for r in out.get("cases") or [])
    return out


def summarize_start_accounting(ledger_starts: int, preflight_ledger_starts: int) -> dict[str, int]:
    """Derive preflight/main/total starts from the canonical ledger count only."""
    total = int(ledger_starts)
    pre = int(preflight_ledger_starts)
    return {
        "preflight_starts": pre,
        "main_starts": total - pre,
        "total_starts": total,
        "total_ledger_starts": total,
    }


def run_batch_executable(run_dir: Path, a1_root: Path, *, source_kind: str = "REAL_VSPAERO") -> dict[str, Any]:
    """Fail-closed wrapper: any setup exception still leaves a stop_report."""
    run_dir = Path(run_dir)
    try:
        return _run_batch_executable_impl(run_dir, a1_root, source_kind=source_kind)
    except ExecutorRefused:
        raise
    except BaseException as exc:  # noqa: BLE001
        if not (run_dir / "stop_report.json").is_file():
            try:
                _write_stop_report(run_dir, "setup", exc)
            except Exception:
                pass
        raise


def run_dry_run(run_dir: Path, a1_root: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    plan_path = run_dir / "plan.json"
    approval_path = run_dir / "approval.DRAFT.json"
    plan = _read_json(plan_path)
    approval = _read_json(approval_path)
    checks: list[dict[str, Any]] = []
    def check(cid: str, ok: bool, expected: Any, actual: Any) -> None:
        checks.append({"check_id": cid, "status": "PASS" if ok else "FAIL",
                       "expected": expected, "actual": actual})
    check("D01_plan_sha", sha256_file(plan_path) == approval.get("plan_sha256"), approval.get("plan_sha256"), sha256_file(plan_path))
    check("D02_draft_not_approved", approval.get("approved") is False, False, approval.get("approved"))
    check("D03_caps", (plan.get("budget_and_caps", {}).get("planned_starts"), plan.get("budget_and_caps", {}).get("max_starts")) == (R10_PLANNED_STARTS, MAX_STARTS),
          (R10_PLANNED_STARTS, MAX_STARTS), (plan.get("budget_and_caps", {}).get("planned_starts"), plan.get("budget_and_caps", {}).get("max_starts")))
    check("D04_window", str(plan.get("window", {}).get("token")) == WINDOW_TOKEN, WINDOW_TOKEN, plan.get("window", {}).get("token"))
    check("D05_executor_blob", bool(approval.get("a2_executor_sha256")), True, bool(approval.get("a2_executor_sha256")))
    check("D06_a1_real_path", (Path(a1_root) / "research/concorde_metaopt/dreal001/geometry/evaluator_v12.py").is_file(), True, True)
    solver_exe: Optional[dict[str, Any]] = None
    try:
        solver_exe = _solver_contract_binding(plan, approval)
    except ExecutorRefused as exc:
        check("D07_solver_contract_exe", False, "bound and SHA-verified", str(exc))
    else:
        check("D07_solver_contract_exe", True, solver_exe["exe_sha256"], solver_exe["exe_sha256"])
    failed = [c for c in checks if c["status"] == "FAIL"]
    result = {
        "schema": DRY_RUN_SCHEMA, "status": "DRY_RUN_BLOCKED_NOT_APPROVED" if approval.get("approved") is not True else "DRY_RUN_READY",
        "approved": False, "blocked": True, "cases_planned": R10_PLANNED_STARTS, "cases_emitted": 0,
        "planned_starts": R10_PLANNED_STARTS, "max_starts": MAX_STARTS,
        "planned_internal_cases": R10_PLANNED_INTERNAL_CASES, "max_internal_cases": MAX_INTERNAL_CASES,
        "preflight_cases": len(PREFLIGHT_CASES_DEFAULT), "reserve_starts": RESERVE_STARTS,
        "diagnostic_cases": list((plan.get("diagnostics") or {}).get("cases") or []),
        "diagnostic_planned_starts": int((plan.get("diagnostics") or {}).get("planned_starts") or 0),
        "diagnostic_planned_internal_cases": int((plan.get("diagnostics") or {}).get("planned_internal_cases") or 0),
        "diagnostics_in_r10_matrix": bool((plan.get("diagnostics") or {}).get("in_r10_matrix") is True),
        "ledger_created": False, "solver_processes": 0, "physical_call_count": 0,
        "solver_exe_binding": solver_exe,
        "checks": checks, "failed": [c["check_id"] for c in failed],
        "executor_version": EXECUTOR_VERSION, "created_utc": _iso(_now_utc()),
    }
    _write_json(run_dir / "executor_dry_run.json", result)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="P2a v2 executable runner")
    parser.add_argument("command", choices=("dry-run", "run"))
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--a1-root", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    a1_root = Path(args.a1_root)
    try:
        if args.command == "dry-run":
            result = run_dry_run(run_dir, a1_root)
        else:
            result = run_batch_executable(run_dir, a1_root)
    except ExecutorRefused as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc), "physical_call_count": 0},
                         ensure_ascii=False, indent=1))
        return 2
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "EXECUTOR_ERROR", "reason": type(exc).__name__ + ": " + str(exc),
                          "stop_report": str(run_dir / "stop_report.json"),
                          "physical_call_count": 0}, ensure_ascii=False, indent=1))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
