"""REAL backend wiring for the A2 lift-match evaluator (A1 contract v1.0).

A2 never launches vspaero.exe itself. This module builds a RealVspaeroAdapter
around an A1 dreal001.geometry.evaluator.AeroEvaluator instance obtained either
by import (merged tree) or by an injected factory (tests / A1 driver). The A1
evaluate callable owns the process, the alpha sweep and the attempt ledger.

Fail-closed rules (Lead m00963, A1 m00946/m00973):
* an A1 evaluate callable is mandatory;
* a signed approval (approved=true, max_starts>0, matching batch_id) is
  mandatory - RealVspaeroAdapter re-checks it;
* allow_physical_starts=True additionally needs A1's ledgered spawn callable;
  P2a is NOT approved, so the default path is zero-physical (A1 evaluate
  returns NOT_RUN records with physical_solver_starts=0);
* A1 owns solver_attempts.jsonl; A2 verifies the rows for every real start and
  fails closed on a mismatch.

A1 accounting recap: one vspaero.exe launch = 1 physical_solver_starts and
7 internal_solver_cases (fixed alpha grid, no per-alpha billing). A real record
must carry geometry.mesh_family + normalized_geometry_hash (canonical mesh sha)
or the adapter raises AccountingViolation.

P2a entry point (A1 EVALUATOR_API v1.1):
research.concorde_metaopt.dreal001.geometry.p2a_contract.make_evaluate_fn is the
unique factory. It returns a guarded callable that (a) refuses unit-box vectors,
(b) enforces approval / batch_id / max_starts before any launch, (c) bills one
physical start per 7-alpha launch, and (d) stamps record["p2a_evaluator"] with
starts_before/starts_after/approval_max_starts. build_p2a_adapter wraps that
callable in RealVspaeroAdapter; the adapter reconciles the stamp against its own
ledger row (fail-closed on any mismatch). Zero physical starts unless a signed
approval is supplied AND allow_physical_starts=True with A1's ledgered spawn.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from .constants import (
    INTERNAL_SOLVER_CASES_PER_START,
    P2A_EVALUATE_ID,
    P2A_EVALUATE_SCHEMA,
    SCHEMA_VERSION,
)
from .evaluators import RealSolverNotAuthorized, RealVspaeroAdapter

#: Module that ships with A1 (branch research/dreal001-a1-geometry-solver).
A1_EVALUATOR_MODULE = "research.concorde_metaopt.dreal001.geometry.evaluator"
A1_EVALUATOR_CLASS = "AeroEvaluator"

#: P2a contract module / factory (A1 EVALUATOR_API v1.1, commit e0838b5).
A1_P2A_MODULE = "research.concorde_metaopt.dreal001.geometry.p2a_contract"
A1_P2A_FACTORY = "make_evaluate_fn"
P2A_TARGET_MESH_FAMILY = (543, 472)
P2A_MAX_MESH_ATTEMPTS = 12
#: A1 P2a disables its own cache; A2 design-hash reuse would mix mesh families.
P2A_CACHE_ENABLED = False


class RealBackendUnavailable(RealSolverNotAuthorized):
    """A1 evaluator is not importable / not constructible in this tree."""


def load_a1_evaluator_class(
    module_name: str = A1_EVALUATOR_MODULE,
    class_name: str = A1_EVALUATOR_CLASS,
) -> Any:
    """Import A1's AeroEvaluator class read-only (no A1 file is modified)."""
    try:
        module = importlib.import_module(str(module_name))
    except Exception as exc:  # noqa: BLE001 - explain the missing dependency
        raise RealBackendUnavailable(
            "A1 geometry evaluator module %r is not importable in this tree (%s: %s); "
            "merge A1 branch research/dreal001-a1-geometry-solver or inject a1_evaluator_factory"
            % (module_name, type(exc).__name__, exc)
        ) from exc
    evaluator_class = getattr(module, str(class_name), None)
    if evaluator_class is None:
        raise RealBackendUnavailable(
            "module %r has no %r (A1 EVALUATOR_API expected)" % (module_name, class_name)
        )
    return evaluator_class


def load_a1_p2a_factory(
    module_name: str = A1_P2A_MODULE,
    factory_name: str = A1_P2A_FACTORY,
) -> Callable[..., Any]:
    """Import A1's P2a make_evaluate_fn factory read-only (no A1 file touched)."""
    try:
        module = importlib.import_module(str(module_name))
    except Exception as exc:  # noqa: BLE001 - explain the missing dependency
        raise RealBackendUnavailable(
            "A1 P2a contract module %r is not importable in this tree (%s: %s); "
            "merge A1 branch research/dreal001-a1-geometry-solver or inject a1_p2a_factory"
            % (module_name, type(exc).__name__, exc)
        ) from exc
    factory = getattr(module, str(factory_name), None)
    if not callable(factory):
        raise RealBackendUnavailable(
            "module %r has no callable %r (A1 EVALUATOR_API v1.1 expected)"
            % (module_name, factory_name)
        )
    return factory


def _p2a_factory_kwargs(
    *,
    run_dir: Any,
    approval: Optional[Mapping[str, Any]],
    spawn: Optional[Callable[..., Mapping[str, Any]]],
    allow_physical_starts: bool,
    max_starts: int,
    batch_id: Optional[str],
    timeout_s: float,
    target_mesh_family: Any,
    max_mesh_attempts: int,
    extra: Optional[Mapping[str, Any]] = None,
) -> dict:
    base = {
        "run_dir": str(run_dir),
        "approval": dict(approval or {}),
        "spawn": spawn,
        "allow_physical_starts": bool(allow_physical_starts),
        "max_starts": int(max_starts),
        "batch_id": batch_id,
        "timeout_s": float(timeout_s),
        "target_mesh_family": tuple(target_mesh_family),
        "max_mesh_attempts": int(max_mesh_attempts),
        "cache_enabled": P2A_CACHE_ENABLED,
    }
    reserved = set(base)
    for key in (extra or {}):
        if key in reserved:
            raise ValueError("p2a_kwargs may not override reserved key %r" % (key,))
    base.update(dict(extra or {}))
    return base


def build_p2a_adapter(
    *,
    design_space: Any,
    task: Any,
    ledger: Any,
    run_dir: Any,
    approval: Optional[Mapping[str, Any]],
    spawn: Optional[Callable[..., Mapping[str, Any]]] = None,
    a1_p2a_factory: Optional[Callable[..., Any]] = None,
    allow_physical_starts: bool = False,
    external_attempts_path: Optional[Any] = None,
    a1_module_name: str = A1_P2A_MODULE,
    a1_design_space: Any = None,
    timeout_s: float = 60.0,
    target_mesh_family: Any = P2A_TARGET_MESH_FAMILY,
    max_mesh_attempts: int = P2A_MAX_MESH_ATTEMPTS,
    p2a_kwargs: Optional[Mapping[str, Any]] = None,
    **adapter_kwargs: Any,
) -> RealVspaeroAdapter:
    """Build the REAL adapter around A1's P2a guarded evaluate callable.

    Fail-closed before touching A1: an approved approval.json with max_starts>0
    is mandatory; physical starts additionally require A1's ledgered spawn.
    The returned adapter verifies record["p2a_evaluator"] against its own ledger
    row and fails closed on any mismatch.
    """
    if not approval or not bool(approval.get("approved")):
        raise RealSolverNotAuthorized(
            "REAL backend needs a signed approval.json (approved=true); P2a remains unapproved"
        )
    declared_starts = int(approval.get("max_starts", 0) or 0)
    if declared_starts <= 0:
        raise RealSolverNotAuthorized("approval.json max_starts must be positive")
    starts_allowed = bool(allow_physical_starts)
    if starts_allowed and not callable(spawn):
        raise RealSolverNotAuthorized(
            "allow_physical_starts=True requires A1's ledgered spawn callable; "
            "A2 must never construct an unguarded physical-start evaluator"
        )
    factory = a1_p2a_factory
    if factory is None:
        factory = load_a1_p2a_factory(a1_module_name)
    batch_id = adapter_kwargs.get("batch_id")
    calls = _p2a_factory_kwargs(
        run_dir=run_dir,
        approval=approval,
        spawn=spawn,
        allow_physical_starts=starts_allowed,
        max_starts=declared_starts,
        batch_id=None if batch_id is None else str(batch_id),
        timeout_s=timeout_s,
        target_mesh_family=target_mesh_family,
        max_mesh_attempts=max_mesh_attempts,
        extra=p2a_kwargs,
    )
    try:
        evaluate_fn = factory(
            a1_design_space if a1_design_space is not None else design_space,
            task,
            **calls,
        )
    except TypeError as exc:
        raise RealBackendUnavailable(
            "could not construct A1 P2a make_evaluate_fn result with the v1.1 signature "
            "(design_space, task, run_dir, approval, spawn, allow_physical_starts, "
            "max_starts, batch_id, timeout_s, target_mesh_family, max_mesh_attempts, "
            "cache_enabled, **kwargs): %s" % (exc,)
        ) from exc
    if not callable(evaluate_fn):
        raise RealBackendUnavailable(
            "A1 P2a factory returned %r; a callable evaluate_fn is required"
            % (type(evaluate_fn),)
        )
    attempts_path = (
        Path(external_attempts_path)
        if external_attempts_path is not None
        else (Path(run_dir) / "solver_attempts.jsonl")
    )
    adapter = RealVspaeroAdapter(
        design_space,
        task,
        ledger,
        evaluate_fn=evaluate_fn,
        approval=approval,
        external_attempts_path=attempts_path,
        **adapter_kwargs,
    )
    # Provenance for run_config/summary: A2 still never launches vspaero.exe.
    adapter.a1_p2a_evaluate_fn = evaluate_fn
    adapter.evaluate_fn_kind = "A1_P2A_V1_1"
    adapter.a1_p2a_module_name = str(a1_module_name)
    adapter.a1_evaluator_contract = "P2A_V1_1"
    adapter.p2a_contract_schema = P2A_EVALUATE_SCHEMA
    adapter.p2a_evaluate_id = str(getattr(evaluate_fn, "evaluate_id", P2A_EVALUATE_ID))
    adapter.p2a_max_starts_approved = declared_starts
    adapter.allow_physical_starts = starts_allowed
    adapter.internal_cases_per_start = int(INTERNAL_SOLVER_CASES_PER_START)
    adapter.record_schema_version = SCHEMA_VERSION
    return adapter


def p2a_adapter_factory(
    *,
    spawn: Optional[Callable[..., Mapping[str, Any]]] = None,
    allow_physical_starts: bool = False,
    a1_p2a_factory: Optional[Callable[..., Any]] = None,
    external_attempts_path: Optional[Any] = None,
    a1_module_name: str = A1_P2A_MODULE,
    a1_design_space: Any = None,
    timeout_s: float = 60.0,
    target_mesh_family: Any = P2A_TARGET_MESH_FAMILY,
    max_mesh_attempts: int = P2A_MAX_MESH_ATTEMPTS,
    p2a_kwargs: Optional[Mapping[str, Any]] = None,
    adapter_kwargs: Optional[Mapping[str, Any]] = None,
) -> Callable[..., RealVspaeroAdapter]:
    """Return a run_pilot(real_adapter_factory=...) closure for the P2a route."""
    fixed_adapter_kwargs = dict(adapter_kwargs or {})
    fixed_p2a_kwargs = dict(p2a_kwargs or {})

    def factory(*, kwargs: Mapping[str, Any], plan: Mapping[str, Any], approval: Optional[Mapping[str, Any]]) -> RealVspaeroAdapter:
        _ = plan
        run_dir = Path(kwargs["run_dir"])
        attempts = (
            Path(external_attempts_path)
            if external_attempts_path is not None
            else (run_dir / "solver_attempts.jsonl")
        )
        forwarded = {
            key: value
            for key, value in dict(kwargs).items()
            if key not in ("design_space", "task", "ledger", "run_dir")
        }
        forwarded.update(fixed_adapter_kwargs)
        return build_p2a_adapter(
            design_space=kwargs["design_space"],
            task=kwargs["task"],
            ledger=kwargs["ledger"],
            run_dir=run_dir,
            approval=approval,
            spawn=spawn,
            a1_p2a_factory=a1_p2a_factory,
            allow_physical_starts=allow_physical_starts,
            external_attempts_path=attempts,
            a1_module_name=a1_module_name,
            a1_design_space=a1_design_space,
            timeout_s=timeout_s,
            target_mesh_family=target_mesh_family,
            max_mesh_attempts=max_mesh_attempts,
            p2a_kwargs=fixed_p2a_kwargs,
            **forwarded,
        )

    return factory


def build_real_adapter(
    *,
    design_space: Any,
    task: Any,
    ledger: Any,
    run_dir: Any,
    approval: Optional[Mapping[str, Any]],
    spawn: Optional[Callable[..., Mapping[str, Any]]] = None,
    a1_evaluator_factory: Optional[Callable[..., Any]] = None,
    allow_physical_starts: bool = False,
    external_attempts_path: Optional[Any] = None,
    a1_module_name: str = A1_EVALUATOR_MODULE,
    a1_evaluator_kwargs: Optional[Mapping[str, Any]] = None,
    **adapter_kwargs: Any,
) -> RealVspaeroAdapter:
    """Build the REAL adapter around A1's evaluator (fail-closed).

    adapter_kwargs are forwarded to the A2 evaluator base (batch_id, run_id,
    arm_id, seed, cache, label_store, recorder, ...). The A1 evaluator receives
    design_space, run_dir, approval, spawn, allow_physical_starts plus
    a1_evaluator_kwargs (e.g. task, timeout_s, tess_u).
    """
    if not approval or not bool(approval.get("approved")):
        raise RealSolverNotAuthorized(
            "REAL backend needs a signed approval.json (approved=true); P2a remains unapproved"
        )
    starts_allowed = bool(allow_physical_starts)
    if starts_allowed and not callable(spawn):
        raise RealSolverNotAuthorized(
            "allow_physical_starts=True requires A1's ledgered spawn callable; "
            "A2 must never construct an unguarded physical-start evaluator"
        )
    if starts_allowed and int(approval.get("max_starts", 0) or 0) <= 0:
        raise RealSolverNotAuthorized("approval.json max_starts must be positive for physical starts")
    factory = a1_evaluator_factory
    if factory is None:
        factory = load_a1_evaluator_class(a1_module_name)
    a1_kwargs = dict(a1_evaluator_kwargs or {})
    try:
        a1_evaluator = factory(
            design_space,
            run_dir=str(run_dir),
            approval=dict(approval),
            spawn=spawn,
            allow_physical_starts=starts_allowed,
            **a1_kwargs,
        )
    except TypeError as exc:
        raise RealBackendUnavailable(
            "could not construct A1 AeroEvaluator with the EVALUATOR_API v1.0 signature "
            "(design_space, run_dir, approval, spawn, allow_physical_starts, **kwargs): %s" % (exc,)
        ) from exc
    evaluate_fn = getattr(a1_evaluator, "evaluate", None)
    if not callable(evaluate_fn):
        raise RealBackendUnavailable("A1 AeroEvaluator instance has no callable evaluate()")
    attempts_path = (
        Path(external_attempts_path)
        if external_attempts_path is not None
        else (Path(run_dir) / "solver_attempts.jsonl")
    )
    adapter = RealVspaeroAdapter(
        design_space,
        task,
        ledger,
        evaluate_fn=evaluate_fn,
        approval=approval,
        external_attempts_path=attempts_path,
        **adapter_kwargs,
    )
    # Provenance for run_config/summary: A2 does not launch the solver itself.
    adapter.a1_evaluator = a1_evaluator
    adapter.a1_module_name = str(a1_module_name)
    adapter.allow_physical_starts = starts_allowed
    adapter.internal_cases_per_start = int(INTERNAL_SOLVER_CASES_PER_START)
    adapter.record_schema_version = SCHEMA_VERSION
    return adapter


def pilot_real_adapter_factory(
    *,
    spawn: Optional[Callable[..., Mapping[str, Any]]] = None,
    allow_physical_starts: bool = False,
    a1_evaluator_factory: Optional[Callable[..., Any]] = None,
    external_attempts_path: Optional[Any] = None,
    a1_module_name: str = A1_EVALUATOR_MODULE,
    a1_evaluator_kwargs: Optional[Mapping[str, Any]] = None,
    adapter_kwargs: Optional[Mapping[str, Any]] = None,
) -> Callable[..., RealVspaeroAdapter]:
    """Return a run_pilot(real_adapter_factory=...) closure.

    The closure reuses the per-run kwargs that pilot.run_pilot already builds
    (design_space, task, ledger, run_dir, batch_id, run_id, arm_id, seed, cache,
    label_store, recorder) and validates the run approval against the plan.
    """
    fixed_adapter_kwargs = dict(adapter_kwargs or {})

    def factory(*, kwargs: Mapping[str, Any], plan: Mapping[str, Any], approval: Optional[Mapping[str, Any]]) -> RealVspaeroAdapter:
        _ = plan
        run_dir = Path(kwargs["run_dir"])
        attempts = (
            Path(external_attempts_path)
            if external_attempts_path is not None
            else (run_dir / "solver_attempts.jsonl")
        )
        forwarded = {
            key: value
            for key, value in dict(kwargs).items()
            if key not in ("design_space", "task", "ledger", "run_dir")
        }
        forwarded.update(fixed_adapter_kwargs)
        return build_real_adapter(
            design_space=kwargs["design_space"],
            task=kwargs["task"],
            ledger=kwargs["ledger"],
            run_dir=run_dir,
            approval=approval,
            spawn=spawn,
            a1_evaluator_factory=a1_evaluator_factory,
            allow_physical_starts=allow_physical_starts,
            external_attempts_path=attempts,
            a1_module_name=a1_module_name,
            a1_evaluator_kwargs=a1_evaluator_kwargs,
            **forwarded,
        )

    return factory


__all__ = [
    "A1_EVALUATOR_MODULE",
    "A1_EVALUATOR_CLASS",
    "A1_P2A_MODULE",
    "A1_P2A_FACTORY",
    "P2A_EVALUATE_SCHEMA",
    "P2A_EVALUATE_ID",
    "P2A_TARGET_MESH_FAMILY",
    "P2A_MAX_MESH_ATTEMPTS",
    "P2A_CACHE_ENABLED",
    "RealBackendUnavailable",
    "build_p2a_adapter",
    "build_real_adapter",
    "load_a1_evaluator_class",
    "load_a1_p2a_factory",
    "p2a_adapter_factory",
    "pilot_real_adapter_factory",
]
