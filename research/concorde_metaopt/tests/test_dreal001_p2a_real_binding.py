"""D-REAL-001 A2: bind A1 P2a make_evaluate_fn (EVALUATOR_API v1.1) into the REAL adapter.

Zero-physical tests: a fake P2a factory returns synthetic dreal001.aero_eval.v1
records and synthetic solver_attempts.jsonl rows. No vspaero.exe is launched and
none of these numbers are aerodynamic evidence. What is tested here is the
fail-closed wiring: approval gating, physical-x12 hand-off, budget-refusal
accounting (never billed, never scored), and reconciliation of A1's
record["p2a_evaluator"] stamp against A2's own ledger.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from research.concorde_metaopt.dreal001.optimizers import (
    BACKEND_REAL,
    P2A_EVALUATE_ID,
    P2A_EVALUATE_SCHEMA,
    SCHEMA_VERSION,
    AccountingViolation,
    RealBackendUnavailable,
    RealSolverNotAuthorized,
    SolverStartLedger,
    build_p2a_adapter,
    build_task,
    design_hash,
    load_a1_p2a_factory,
    p2a_adapter_factory,
)

X12 = np.full(12, 0.5)
ALPHA_GRID = (-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0)
APPROVAL_MAX_STARTS = 4
BATCH_ID = "pytest-p2a-binding"


def _read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _a1_physical_x12(design_space, unit_vector):
    physical = design_space.from_unit_interval([float(value) for value in unit_vector])
    names = list(design_space.names)
    return [float(physical[name]) for name in names]


def _a1_v1_record(*, task, x12_physical, starts=1):
    """Synthetic A1 record: 7 alpha rows that bracket the target lift."""
    cl = [0.05, 0.09, 0.13, 0.17, 0.21, 0.25, 0.29]
    cdi = [0.0060, 0.0064, 0.0068, 0.0072, 0.0076, 0.0080, 0.0084]
    cdo = [0.0040] * 7
    cdtot = [i + j for i, j in zip(cdi, cdo)]
    attempt_id = "a1-p2a-attempt-01"
    return {
        "schema_version": SCHEMA_VERSION,
        "evaluator_id": P2A_EVALUATE_ID,
        "backend": BACKEND_REAL,
        "source_kind": "REAL_VSPAERO",
        "physical_validation_status": "NOT_VALIDATED",
        "status": "SOLVED_VALID",
        "design": {
            "x12": [float(value) for value in x12_physical],
            "design_hash": design_hash([float(value) for value in x12_physical]),
        },
        "geometry": {
            "geometry_sha256": "e" * 64,
            "vspgeom_sha256": "f" * 64,
            "nodes": 543,
            "elements": 472,
            "mesh_family": "543/472",
            "mesh_attempts": 1,
            "mesh_strategy": "roundtrip",
            "canonical_mesh_sha256": "c" * 64,
        },
        "solver": {
            "physical_solver_starts": int(starts),
            "internal_solver_cases": 7 * int(starts),
            "internal_solver_cases_expected": 7,
            "solver_config_sha256": task.solver_config_sha256,
            "command": ["vspaero", "-omp", "1"],
            "attempt_ids": [attempt_id] if starts else [],
        },
        "physical_solver_starts": int(starts),
        "results": {
            "alpha_deg": list(ALPHA_GRID),
            "cltot": cl,
            "cdi": cdi,
            "cdo": cdo,
            "cdtot": cdtot,
            "cmy": [0.0] * 7,
        },
        "lift": {},
        "attempt_ids": [attempt_id] if starts else [],
        "raw_artifacts": [],
        "errors": [],
        "fuel_burn_kg": None,
        "objective": {"name": "D_i_N", "value": None, "unit": "N"},
    }


def _refusal_record(case_id, code, detail):
    """Synthetic A1 P2a refusal record (same shape as A1 p2a_contract)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "evaluator_id": P2A_EVALUATE_ID,
        "backend": BACKEND_REAL,
        "source_kind": "REAL_VSPAERO",
        "physical_validation_status": "NOT_VALIDATED",
        "status": "NOT_RUN",
        "record_status": "NOT_RUN",
        "case_id": str(case_id),
        "design": {"x12": [], "design_hash": ""},
        "geometry": {},
        "solver": {"physical_solver_starts": 0, "attempt_ids": [], "argv": [], "command": []},
        "results": {"alpha_deg": [], "cltot": [], "cdi": [], "cdo": [], "cdtot": [], "cmy": []},
        "lift": {},
        "attempt_ids": [],
        "raw_artifacts": [],
        "errors": [{"code": str(code), "detail": str(detail), "no_solver_start": True}],
        "cache_hit": False,
        "physical_solver_starts": 0,
        "physical_call_count": 0,
        "objective": {"name": "D_i_N", "value": None, "unit": "N"},
        "fuel_burn_kg": None,
    }


class _FakeP2AFactory:
    """Stand-in for A1 make_evaluate_fn; records the construction kwargs."""

    MODES = (
        "solved",
        "stamped_budget",
        "budget_refusal",
        "mesh_refusal",
        "delta_mismatch",
        "over_cap",
        "cap_mismatch",
        "bad_schema",
    )

    def __init__(self, mode="solved"):
        assert mode in self.MODES, mode
        self.mode = mode
        self.calls = []
        self.design_space = None
        self.task = None
        self.evaluate_fn = None

    def __call__(self, design_space, task, **kwargs):
        self.design_space = design_space
        self.task = task
        self.calls.append({"design_space": design_space, "task": task, "kwargs": dict(kwargs)})
        self.evaluate_fn = _FakeP2AEvaluateFn(self)
        return self.evaluate_fn


class _FakeP2AEvaluateFn:
    """Stand-in for A1's guarded P2AEvaluateFn: writes attempts, stamps records."""

    evaluate_id = P2A_EVALUATE_ID
    schema_version = P2A_EVALUATE_SCHEMA

    def __init__(self, factory):
        self.factory = factory
        self.calls = []
        self.starts_used = 0

    def _kwargs(self):
        return self.factory.calls[-1]["kwargs"] if self.factory.calls else {}

    def __call__(self, x12, case_id=None, meta=None):
        x12_physical = [float(value) for value in x12]
        self.calls.append({"x12": x12_physical, "case_id": case_id, "meta": dict(meta or {})})
        mode = self.factory.mode
        if mode == "budget_refusal":
            return _refusal_record(case_id, "SOLVER_BUDGET_EXHAUSTED", "refused before any solver start")
        if mode == "mesh_refusal":
            return _refusal_record(case_id, "MESH_FAMILY_UNAVAILABLE", "target mesh family unreachable")
        record = _a1_v1_record(task=self.factory.task, x12_physical=x12_physical, starts=1)
        attempts_path = Path(self._kwargs()["run_dir"]) / "solver_attempts.jsonl"
        attempts_path.parent.mkdir(parents=True, exist_ok=True)
        with attempts_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "attempt_id": record["attempt_ids"][0],
                        "design_hash": record["design"]["design_hash"],
                        "physical_solver_starts": 1,
                        "internal_solver_cases": 7,
                    }
                )
                + "\n"
            )
        cap = int(self._kwargs().get("max_starts", APPROVAL_MAX_STARTS))
        before = self.starts_used
        self.starts_used += 1
        stamp = {
            "evaluate_id": P2A_EVALUATE_ID,
            "schema_version": P2A_EVALUATE_SCHEMA,
            "starts_before": before,
            "starts_after": self.starts_used,
            "approval_max_starts": cap,
        }
        if mode == "delta_mismatch":
            # A1 stamp claims two starts while the record claims one.
            stamp["starts_before"] = before
            stamp["starts_after"] = before + 2
        elif mode == "over_cap":
            stamp["starts_before"] = cap
            stamp["starts_after"] = cap + 1
        elif mode == "cap_mismatch":
            stamp["approval_max_starts"] = cap - 1
        elif mode == "bad_schema":
            stamp["schema_version"] = "dreal001.p2a_evaluate_fn.v0"
        record["p2a_evaluator"] = stamp
        return record


class _StampedBudgetEvaluateFn(_FakeP2AEvaluateFn):
    """A P2a callable whose evaluator returned NOT_RUN with a zero-delta stamp."""

    def __call__(self, x12, case_id=None, meta=None):
        self.calls.append({"x12": [float(v) for v in x12], "case_id": case_id, "meta": dict(meta or {})})
        cap = int(self._kwargs().get("max_starts", APPROVAL_MAX_STARTS))
        return {
            "schema_version": SCHEMA_VERSION,
            "evaluator_id": P2A_EVALUATE_ID,
            "backend": BACKEND_REAL,
            "source_kind": "REAL_VSPAERO",
            "physical_validation_status": "NOT_VALIDATED",
            "status": "NOT_RUN",
            "record_status": "NOT_RUN",
            "case_id": str(case_id),
            "design": {"x12": [], "design_hash": ""},
            "geometry": {},
            "solver": {"physical_solver_starts": 0, "attempt_ids": [], "argv": [], "command": []},
            "results": {"alpha_deg": [], "cltot": [], "cdi": [], "cdo": [], "cdtot": [], "cmy": []},
            "lift": {},
            "attempt_ids": [],
            "raw_artifacts": [],
            "errors": [{"code": "SOLVER_BUDGET_EXHAUSTED", "detail": "cap reached", "no_solver_start": True}],
            "cache_hit": False,
            "physical_solver_starts": 0,
            "objective": {"name": "D_i_N", "value": None, "unit": "N"},
            "fuel_burn_kg": None,
            "p2a_evaluator": {
                "evaluate_id": P2A_EVALUATE_ID,
                "schema_version": P2A_EVALUATE_SCHEMA,
                "starts_before": cap,
                "starts_after": cap,
                "approval_max_starts": cap,
            },
        }


class _StampedBudgetFactory(_FakeP2AFactory):
    def __call__(self, design_space, task, **kwargs):
        self.design_space = design_space
        self.task = task
        self.calls.append({"design_space": design_space, "task": task, "kwargs": dict(kwargs)})
        self.evaluate_fn = _StampedBudgetEvaluateFn(self)
        return self.evaluate_fn


def _p2a_adapter(tmp_path, design_space_12d, *, run_id, factory, approval=None, **adapter_kwargs):
    task = build_task()
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = SolverStartLedger(
        run_dir,
        batch_id=BATCH_ID,
        run_id=run_id,
        max_starts=APPROVAL_MAX_STARTS,
        backend=BACKEND_REAL,
        task_id=task.task_id,
        solver_config_sha256=task.solver_config_sha256,
    )
    approval = approval or {"approved": True, "batch_id": BATCH_ID, "max_starts": APPROVAL_MAX_STARTS}
    adapter = build_p2a_adapter(
        design_space=design_space_12d,
        task=task,
        ledger=ledger,
        run_dir=run_dir,
        approval=approval,
        a1_p2a_factory=factory,
        batch_id=BATCH_ID,
        run_id=run_id,
        arm_id="BO",
        seed=0,
        timeout_s=30.0,
        **adapter_kwargs,
    )
    return task, adapter, ledger, run_dir


def test_build_p2a_adapter_wires_v1_1_callable_and_reconciles_stamp(tmp_path, design_space_12d):
    factory = _FakeP2AFactory(mode="solved")
    task, adapter, ledger, run_dir = _p2a_adapter(tmp_path, design_space_12d, run_id="p2a-wire", factory=factory)
    evaluation = adapter.evaluate(X12)

    assert evaluation.status == "VALID"
    assert evaluation.record_status == "SOLVED_VALID"
    assert evaluation.physical_solver_starts == 1
    assert evaluation.simulated_solver_starts == 0
    assert evaluation.mesh_family == "543/472"
    assert evaluation.normalized_geometry_hash == "c" * 64
    assert evaluation.D_i_N == pytest.approx(evaluation.q_Pa * evaluation.Sref_m2 * evaluation.CDi, rel=1e-6)

    # P2a provenance and stamp reconciliation.
    assert adapter.a1_evaluator_contract == "P2A_V1_1"
    assert adapter.evaluate_fn_kind == "A1_P2A_V1_1"
    assert adapter.a1_p2a_evaluate_fn is factory.evaluate_fn
    assert adapter.p2a_evaluate_id == P2A_EVALUATE_ID
    assert adapter.p2a_calls == 1
    assert adapter.p2a_starts_reported == 1
    assert adapter.p2a_last_accounting == {
        "evaluate_id": P2A_EVALUATE_ID,
        "schema_version": P2A_EVALUATE_SCHEMA,
        "starts_before": 0,
        "starts_after": 1,
        "delta": 1,
        "approval_max_starts": APPROVAL_MAX_STARTS,
        "budget_exhausted": False,
    }

    # A1 factory received the v1.1 contract with the frozen P2a mesh target.
    call = factory.calls[0]
    kwargs = call["kwargs"]
    assert call["design_space"] is design_space_12d
    assert call["task"] is task
    assert kwargs["run_dir"] == str(run_dir)
    assert kwargs["approval"]["max_starts"] == APPROVAL_MAX_STARTS
    assert kwargs["batch_id"] == BATCH_ID
    assert kwargs["max_starts"] == APPROVAL_MAX_STARTS
    assert kwargs["allow_physical_starts"] is False
    assert kwargs["spawn"] is None
    assert kwargs["timeout_s"] == pytest.approx(30.0)
    assert kwargs["target_mesh_family"] == (543, 472)
    assert kwargs["max_mesh_attempts"] == 12
    assert kwargs["cache_enabled"] is False

    # A1 consumes physical x12, never the optimizer's unit-box vector.
    assert factory.evaluate_fn.calls[0]["x12"] == pytest.approx(_a1_physical_x12(design_space_12d, X12))
    assert any(value > 1.0 or value < 0.0 for value in factory.evaluate_fn.calls[0]["x12"])
    assert factory.evaluate_fn.calls[0]["meta"]["phase"] == "primary"
    assert factory.evaluate_fn.calls[0]["meta"]["arm"] == "BO"
    assert factory.evaluate_fn.calls[0]["meta"]["seed"] == 0

    assert ledger.physical_solver_starts == 1
    assert ledger.internal_solver_cases == 7
    assert len(_read_jsonl(run_dir / "solver_attempts.jsonl")) == 1


def test_p2a_budget_refusal_is_unbilled_and_not_run(tmp_path, design_space_12d):
    factory = _FakeP2AFactory(mode="budget_refusal")
    _task, adapter, ledger, run_dir = _p2a_adapter(tmp_path, design_space_12d, run_id="p2a-budget", factory=factory)
    evaluation = adapter.evaluate(X12)

    assert evaluation.status == "NOT_RUN"
    assert evaluation.record_status == "NOT_RUN"
    assert evaluation.physical_solver_starts == 0
    assert evaluation.D_i_N is None
    assert evaluation.L_N is None
    assert evaluation.error_code == "SOLVER_BUDGET_EXHAUSTED"
    assert factory.evaluate_fn.calls, "A2 must still hand the design to A1; A1 decides refusal"
    assert adapter.p2a_calls == 0
    assert adapter.p2a_starts_reported == 0
    assert adapter.p2a_budget_exhausted is True
    assert adapter.p2a_last_accounting is None
    assert ledger.physical_solver_starts == 0
    assert ledger.valid_evals == 0
    assert not _read_jsonl(run_dir / "solver_attempts.jsonl")


def test_p2a_stamped_not_run_zero_delta_marks_budget_exhausted(tmp_path, design_space_12d):
    factory = _StampedBudgetFactory()
    _task, adapter, ledger, _run_dir = _p2a_adapter(tmp_path, design_space_12d, run_id="p2a-stamp", factory=factory)
    evaluation = adapter.evaluate(X12)

    assert evaluation.status == "NOT_RUN"
    assert evaluation.physical_solver_starts == 0
    assert adapter.p2a_calls == 1
    assert adapter.p2a_last_accounting["delta"] == 0
    assert adapter.p2a_last_accounting["budget_exhausted"] is True
    assert adapter.p2a_budget_exhausted is True
    assert ledger.physical_solver_starts == 0
    assert ledger.valid_evals == 0


def test_p2a_mesh_refusal_is_not_run_without_budget_flag(tmp_path, design_space_12d):
    factory = _FakeP2AFactory(mode="mesh_refusal")
    _task, adapter, ledger, _run_dir = _p2a_adapter(tmp_path, design_space_12d, run_id="p2a-mesh", factory=factory)
    evaluation = adapter.evaluate(X12)

    assert evaluation.status == "NOT_RUN"
    assert evaluation.record_status == "NOT_RUN"
    assert evaluation.error_code == "MESH_FAMILY_UNAVAILABLE"
    assert evaluation.physical_solver_starts == 0
    assert adapter.p2a_budget_exhausted is False
    assert ledger.physical_solver_starts == 0


@pytest.mark.parametrize(
    "mode, message_part",
    [
        ("delta_mismatch", "delta 2 does not match record physical_solver_starts 1"),
        ("over_cap", "starts_after 5 exceeds approved cap 4"),
        ("cap_mismatch", "approval_max_starts 3 does not match A2 approval max_starts 4"),
        ("bad_schema", "schema_version 'dreal001.p2a_evaluate_fn.v0'"),
    ],
)
def test_p2a_stamp_contradictions_fail_closed(tmp_path, design_space_12d, mode, message_part):
    factory = _FakeP2AFactory(mode=mode)
    _task, adapter, ledger, _run_dir = _p2a_adapter(
        tmp_path, design_space_12d, run_id="p2a-contra-" + mode, factory=factory
    )
    with pytest.raises(AccountingViolation, match=message_part):
        adapter.evaluate(X12)
    # The reservation is cancelled; a contradiction bills nothing.
    assert ledger.physical_solver_starts == 0
    assert ledger.valid_evals == 0


def test_build_p2a_adapter_fails_closed_before_any_solver_call(tmp_path, design_space_12d):
    task = build_task()
    run_dir = tmp_path / "p2a-closed"
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = SolverStartLedger(
        run_dir,
        batch_id=BATCH_ID,
        run_id="p2a-closed",
        max_starts=APPROVAL_MAX_STARTS,
        backend=BACKEND_REAL,
        task_id=task.task_id,
        solver_config_sha256=task.solver_config_sha256,
    )
    common = dict(
        design_space=design_space_12d,
        task=task,
        ledger=ledger,
        run_dir=run_dir,
        batch_id=BATCH_ID,
        run_id="p2a-closed",
        arm_id="BO",
        seed=0,
    )
    approved = {"approved": True, "batch_id": BATCH_ID, "max_starts": APPROVAL_MAX_STARTS}

    with pytest.raises(RealSolverNotAuthorized, match="signed approval"):
        build_p2a_adapter(**common, approval=None, a1_p2a_factory=_FakeP2AFactory())
    with pytest.raises(RealSolverNotAuthorized, match="signed approval"):
        build_p2a_adapter(**common, approval=dict(approved, approved=False), a1_p2a_factory=_FakeP2AFactory())
    with pytest.raises(RealSolverNotAuthorized, match="max_starts must be positive"):
        build_p2a_adapter(**common, approval=dict(approved, max_starts=0), a1_p2a_factory=_FakeP2AFactory())
    with pytest.raises(RealSolverNotAuthorized, match="ledgered spawn"):
        build_p2a_adapter(
            **common,
            approval=approved,
            a1_p2a_factory=_FakeP2AFactory(),
            allow_physical_starts=True,
            spawn=None,
        )

    def _bad_signature_factory(*args, **kwargs):
        raise TypeError("unexpected keyword argument 'approval'")

    with pytest.raises(RealBackendUnavailable, match="v1.1 signature"):
        build_p2a_adapter(**common, approval=approved, a1_p2a_factory=_bad_signature_factory)
    with pytest.raises(RealBackendUnavailable, match="callable evaluate_fn"):
        build_p2a_adapter(**common, approval=approved, a1_p2a_factory=lambda *args, **kwargs: 123)

    with pytest.raises(RealBackendUnavailable, match="not importable"):
        load_a1_p2a_factory("does.not.exist.p2a_contract")
    with pytest.raises(RealBackendUnavailable, match="has no callable"):
        load_a1_p2a_factory("json", "make_evaluate_fn")


def test_p2a_adapter_factory_closure_builds_adapter_from_pilot_kwargs(tmp_path, design_space_12d):
    factory = _FakeP2AFactory(mode="solved")
    task = build_task()
    run_dir = tmp_path / "p2a-pilot"
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = SolverStartLedger(
        run_dir,
        batch_id=BATCH_ID,
        run_id="p2a-pilot",
        max_starts=APPROVAL_MAX_STARTS,
        backend=BACKEND_REAL,
        task_id=task.task_id,
        solver_config_sha256=task.solver_config_sha256,
    )
    approved = {"approved": True, "batch_id": BATCH_ID, "max_starts": APPROVAL_MAX_STARTS}
    build_adapter = p2a_adapter_factory(a1_p2a_factory=factory, timeout_s=30.0)
    adapter = build_adapter(
        kwargs={
            "design_space": design_space_12d,
            "task": task,
            "ledger": ledger,
            "run_dir": run_dir,
            "batch_id": BATCH_ID,
            "run_id": "p2a-pilot",
            "arm_id": "BO",
            "seed": 0,
        },
        plan={},
        approval=approved,
    )
    evaluation = adapter.evaluate(X12)

    assert evaluation.status == "VALID"
    assert adapter.a1_evaluator_contract == "P2A_V1_1"
    assert factory.calls[0]["kwargs"]["run_dir"] == str(run_dir)
    assert factory.calls[0]["kwargs"]["timeout_s"] == pytest.approx(30.0)
    assert len(_read_jsonl(run_dir / "solver_attempts.jsonl")) == 1
