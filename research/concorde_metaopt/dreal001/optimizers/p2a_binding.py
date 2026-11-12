"""A1 v1.1 binding for the P2a pre-registration (TaskSpec / freeze / code).

Lead m00591 P2A-07 blocker: P2a must run a THIN 12x25 7-alpha task, not the
legacy thick/20x20/wake32/refine DRealTaskSpec default.  This module builds the
byte-level binding to A1's frozen contract without copying it:

* A1 geometry/task_spec.py raw SHA256 + canonical TASK_SPEC.to_dict() SHA256;
* A1 design_space_freeze.json raw + canonical hash and the frozen bounds hash;
* A1 evaluator.py / p2a_contract.py / EVALUATOR_API.md byte hashes;
* fail-closed probes: A1's make_evaluate_fn must refuse the unsigned P2a
  approval BEFORE constructing the evaluator; A2's build_real_adapter must
  refuse it before any spawn.

Everything here is read-only and zero-physical (physical_call_count=0).
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .records import canonical_json, sha256_file

A1_TASK_SPEC_SCHEMA = "dreal001.task_spec.v1"
A1_EVALUATOR_MODULE = "research.concorde_metaopt.dreal001.geometry.evaluator"
A1_TASK_SPEC_MODULE = "research.concorde_metaopt.dreal001.geometry.task_spec"
A1_CONTRACT_MODULE = "research.concorde_metaopt.dreal001.geometry.p2a_contract"

#: Frozen P2a thin task values (Lead m00591; A1 EVALUATOR_API v1.1 D2/D3).
P2A_TASK_EXPECTATIONS: Dict[str, Any] = {
    "geometry_set": "thin",
    "tess_u": 12.0,
    "tess_w": 25.0,
    "alpha_fixed_list_deg": (-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0),
    "lift_tolerance_rel": 1.0e-3,
    "q_Pa": 20483.940233430174,
    "l_ref_N": 1333704.4,
    "sref_baseline_m2": 358.25,
    "reference_frame": "WING_AC",
    "solver_includes_fuselage": False,
}

#: Config keys that must NOT survive into the P2a plan/approval (legacy thick).
FORBIDDEN_LEGACY_KEYS = ("num_wake_nodes", "wake_iters", "alpha_refine_deg", "max_refine_sweeps")


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def a1_geometry_dir(a1_root: Any) -> Path:
    return Path(a1_root) / "research" / "concorde_metaopt" / "dreal001" / "geometry"


def ensure_a1_importable(a1_root: Any) -> Path:
    """Make A1's `dreal001.geometry` importable read-only inside the A2 process."""
    root = Path(a1_root)
    geometry = a1_geometry_dir(root)
    if not geometry.is_dir():
        raise FileNotFoundError("A1 geometry package not found under %s" % (root,))
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    package = importlib.import_module("research.concorde_metaopt.dreal001")
    a1_package_dir = str(root / "research" / "concorde_metaopt" / "dreal001")
    if a1_package_dir not in list(getattr(package, "__path__", [])):
        package.__path__.append(a1_package_dir)  # type: ignore[attr-defined]
    importlib.invalidate_caches()
    return root


def _canonical_sha(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _approx(value: Any, expected: float, rel: float = 1.0e-9) -> bool:
    try:
        actual = float(value)
    except Exception:
        return False
    return abs(actual - float(expected)) <= rel * max(1.0, abs(float(expected)))


def a1_code_binding(a1_root: Any) -> Dict[str, Any]:
    """Byte hashes of the A1 files the P2a plan is bound to."""
    root = Path(a1_root)
    geometry = a1_geometry_dir(root)
    paths = {
        "task_spec.py": geometry / "task_spec.py",
        "p2a_contract.py": geometry / "p2a_contract.py",
        "evaluator.py": geometry / "evaluator.py",
        "EVALUATOR_API.md": geometry / "EVALUATOR_API.md",
        "design_space_freeze.json": geometry / "design_space_freeze.json",
    }
    files: Dict[str, Any] = {}
    for name, target in paths.items():
        if target.is_file():
            files[name] = {
                "path": _rel(target, root),
                "sha256": sha256_file(target),
                "bytes": int(target.stat().st_size),
            }
    return {"a1_root": str(root), "files": files, "physical_call_count": 0}


def frozen_design_space_binding(a1_root: Any) -> Dict[str, Any]:
    """Double hash of A1's frozen 12D design space (raw + canonical)."""
    root = Path(a1_root)
    geometry = a1_geometry_dir(root)
    freeze_path = geometry / "design_space_freeze.json"
    if not freeze_path.is_file():
        return {"status": "A1_FROZEN_DESIGN_SPACE_UNAVAILABLE", "path": _rel(freeze_path, root) if freeze_path.exists() else str(freeze_path)}
    raw = freeze_path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "A1_FROZEN_DESIGN_SPACE_INVALID", "reason": "%s: %s" % (type(exc).__name__, exc)}
    source = payload.get("source_config", {}) or {}
    variables = payload.get("variables") or []
    bounds = []
    for item in variables:
        if isinstance(item, Mapping) and "bounds" in item:
            bounds.append({"name": item.get("name") or item.get("id"), "bounds": list(item.get("bounds") or [])})
    config_rel = str(source.get("path") or "")
    config_path = root / config_rel if config_rel else None
    config_sha = ""
    if config_path is not None and config_path.is_file():
        config_sha = sha256_file(config_path)
    checks = {
        "schema_ok": payload.get("schema") == "dreal001.design_space_freeze.v1",
        "bounds_frozen_for_p0": bool((payload.get("design_space_status") or {}).get("bounds_frozen_for_p0")),
        "twelve_variables": len(variables) == 12,
        "config_sha_matches_freeze": bool(source.get("sha256")) and config_sha == str(source.get("sha256")),
    }
    return {
        "status": "BOUND" if all(checks.values()) else "FROZEN_DESIGN_SPACE_CHECK_FAILED",
        "path": _rel(freeze_path, root),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "canonical_sha256": _canonical_sha(payload),
        "bytes": len(raw),
        "source_config": {"path": config_rel, "sha256": config_sha, "declared_sha256": str(source.get("sha256") or "")},
        "bounds_sha256": _canonical_sha(bounds),
        "n_variables": len(variables),
        "checks": checks,
        "physical_call_count": 0,
    }


@contextlib.contextmanager
def _no_bytecode_writes():
    """Import A1 modules without writing __pycache__ into the A1 worktree.

    A2 may only write its own worktree; importing A1's geometry package for a
    read-only binding/probe must not leave bytecode behind in A1's tree.
    """
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous


def a1_task_spec_binding(a1_root: Any) -> Dict[str, Any]:
    """Bind A1 v1.1 TaskSpec by raw file bytes + canonical TASK_SPEC.to_dict()."""
    root = Path(a1_root)
    geometry = a1_geometry_dir(root)
    task_spec_path = geometry / "task_spec.py"
    binding: Dict[str, Any] = {
        "status": "A1_TASK_SPEC_UNAVAILABLE",
        "module": A1_TASK_SPEC_MODULE,
        "raw_path": _rel(task_spec_path, root) if task_spec_path.exists() else str(task_spec_path),
        "raw_sha256": sha256_file(task_spec_path) if task_spec_path.is_file() else "",
        "canonical_sha256": "",
        "schema": "",
        "expected": dict(P2A_TASK_EXPECTATIONS),
        "checks": {},
        "physical_call_count": 0,
    }
    try:
        ensure_a1_importable(root)
        with _no_bytecode_writes():
            module = importlib.import_module(A1_TASK_SPEC_MODULE)
        module_file = Path(getattr(module, "__file__", ""))
        if root.resolve() not in module_file.resolve().parents and module_file.resolve() != task_spec_path.resolve():
            raise ImportError("imported %s from %s, not from the A1 worktree %s" % (A1_TASK_SPEC_MODULE, module_file, root))
        spec = getattr(module, "TASK_SPEC")
        contract = module.validate_contract()
        payload = spec.to_dict()
        checks = {
            "schema_ok": payload.get("schema") == A1_TASK_SPEC_SCHEMA,
            "status_frozen": str(getattr(spec, "status", "")) == "FROZEN_FOR_P0_P1",
            "q_pa": _approx(getattr(spec, "q_pa"), P2A_TASK_EXPECTATIONS["q_Pa"], 1.0e-12),
            "l_ref_n": _approx(getattr(spec, "l_ref_n"), P2A_TASK_EXPECTATIONS["l_ref_N"], 1.0e-12),
            "sref_baseline_m2": _approx(getattr(spec, "sref_baseline_m2"), P2A_TASK_EXPECTATIONS["sref_baseline_m2"]),
            "alpha_fixed_list_deg": tuple(float(v) for v in getattr(spec, "alpha_fixed_list_deg")) == tuple(P2A_TASK_EXPECTATIONS["alpha_fixed_list_deg"]),
            "lift_tolerance_rel": _approx(getattr(spec, "lift_tolerance_rel"), P2A_TASK_EXPECTATIONS["lift_tolerance_rel"], 1.0e-12),
            "geometry_set_thin": str(getattr(spec, "default_geometry_set", "")) == "thin",
            "solver_excludes_fuselage": getattr(spec, "solver_includes_fuselage") is False,
            "reference_frame": str(getattr(spec, "reference_frame", "")) == "WING_AC",
            "contract_validation": bool(contract),
        }
        binding.update(
            {
                "status": "BOUND" if all(checks.values()) else "TASK_SPEC_CHECK_FAILED",
                "module_file": _rel(module_file, root),
                "raw_sha256": sha256_file(task_spec_path),
                "canonical_sha256": _canonical_sha(payload),
                "schema": str(payload.get("schema")),
                "task_id": str(getattr(spec, "task_id", "")),
                "status_field": str(getattr(spec, "status", "")),
                "contract_validation": {key: float(value) for key, value in contract.items()},
                "frozen_values": {
                    "q_pa": float(getattr(spec, "q_pa")),
                    "l_ref_n": float(getattr(spec, "l_ref_n")),
                    "cref_m": float(getattr(spec, "cref_m")),
                    "bref_m": float(getattr(spec, "bref_m")),
                    "recref": float(getattr(spec, "recref")),
                    "sref_baseline_m2": float(getattr(spec, "sref_baseline_m2")),
                    "xcg_m": float(getattr(spec, "xcg_m")),
                    "geometry_cg_x_m": float(getattr(spec, "geometry_cg_x_m")),
                    "lift_tolerance_rel": float(getattr(spec, "lift_tolerance_rel")),
                    "reference_frame": str(getattr(spec, "reference_frame")),
                    "alpha_fixed_list_deg": [float(v) for v in getattr(spec, "alpha_fixed_list_deg")],
                    "default_geometry_set": str(getattr(spec, "default_geometry_set")),
                    "solver_includes_fuselage": bool(getattr(spec, "solver_includes_fuselage")),
                    "mass_cruise_entry_kg": float(getattr(spec, "mass_cruise_entry_kg")),
                    "mass_geometry_model_kg": float(getattr(spec, "mass_geometry_model_kg")),
                    "mass_contract_status": str(getattr(spec, "mass_contract_status")),
                },
                "checks": checks,
            }
        )
    except Exception as exc:  # noqa: BLE001 - binding must fail closed, not crash the build
        binding["error"] = "%s: %s" % (type(exc).__name__, exc)
    return binding


def probe_a1_fail_closed(a1_root: Any, approval: Mapping[str, Any]) -> Dict[str, Any]:
    """Call A1's make_evaluate_fn with the DRAFT approval; it must refuse pre-solver."""
    root = Path(a1_root)
    result: Dict[str, Any] = {
        "status": "A1_PROBE_UNAVAILABLE",
        "physical_call_count": 0,
        "solver_started": False,
    }
    try:
        ensure_a1_importable(root)
        with _no_bytecode_writes():
            contract_module = importlib.import_module(A1_CONTRACT_MODULE)
        try:
            contract_module.make_evaluate_fn(
                None,
                None,
                run_dir=None,
                approval=dict(approval),
                spawn=None,
                allow_physical_starts=False,
                batch_id=str(approval.get("batch_id") or ""),
            )
            result.update({"status": "UNEXPECTED_ALLOWED", "reason": "A1 accepted an unsigned approval"})
        except Exception as exc:  # noqa: BLE001 - refusal IS the expected result
            code = str(getattr(contract_module, "ERROR_APPROVAL", "APPROVAL_MISSING_OR_NOT_APPROVED"))
            result.update(
                {
                    "status": "REFUSED_BEFORE_SOLVER",
                    "exception": type(exc).__name__,
                    "message": str(exc),
                    "expected_error_code": code,
                    "expected_code_present": code in str(exc),
                    "physical_call_count": 0,
                }
            )
        result["refusal_code"] = str(getattr(contract_module, "ERROR_APPROVAL", ""))
        result["aero_eval_schema"] = str(getattr(contract_module, "AERO_EVAL_SCHEMA", ""))
    except Exception as exc:  # noqa: BLE001
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
    return result


def probe_a2_adapter_fail_closed(approval: Mapping[str, Any]) -> Dict[str, Any]:
    """A2 build_real_adapter must refuse the unsigned approval before any spawn."""
    result: Dict[str, Any] = {"status": "A2_PROBE_UNAVAILABLE", "physical_call_count": 0, "solver_started": False}
    try:
        from .real_backend import build_real_adapter

        try:
            build_real_adapter(
                design_space=None,
                task=None,
                ledger=None,
                run_dir=None,
                approval=dict(approval),
                spawn=None,
                allow_physical_starts=False,
            )
            result.update({"status": "UNEXPECTED_ALLOWED", "reason": "A2 adapter accepted an unsigned approval"})
        except Exception as exc:  # noqa: BLE001
            result.update(
                {
                    "status": "REFUSED_BEFORE_SPAWN",
                    "exception": type(exc).__name__,
                    "message": str(exc),
                    "physical_call_count": 0,
                }
            )
    except Exception as exc:  # noqa: BLE001
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
    return result


def legacy_solver_config_keys(config: Mapping[str, Any]) -> List[str]:
    """Keys that would prove the plan still carries the legacy thick task."""
    present: List[str] = []
    for key in FORBIDDEN_LEGACY_KEYS:
        if key in config:
            present.append(key)
    if str(config.get("geom_set") or config.get("geometry_set") or "").lower() == "thick":
        present.append("geom_set=thick")
    if int(config.get("tess_u", 0) or 0) == 20 or int(config.get("tess_w", 0) or 0) == 20:
        present.append("tess_20x20")
    if "wake" in canonical_json(config).lower():
        present.append("wake_field")
    return present


__all__ = [
    "A1_CONTRACT_MODULE",
    "A1_EVALUATOR_MODULE",
    "A1_TASK_SPEC_MODULE",
    "FORBIDDEN_LEGACY_KEYS",
    "P2A_TASK_EXPECTATIONS",
    "a1_code_binding",
    "a1_geometry_dir",
    "a1_task_spec_binding",
    "ensure_a1_importable",
    "frozen_design_space_binding",
    "legacy_solver_config_keys",
    "probe_a1_fail_closed",
    "probe_a2_adapter_fail_closed",
]
