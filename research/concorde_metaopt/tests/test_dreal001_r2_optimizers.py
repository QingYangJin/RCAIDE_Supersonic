"""D-REAL-001 A2: lift-match evaluator, solver-start accounting, six-arm fairness.

All tests run without a real solver. MOCK runs record simulated_solver_starts
and MUST report physical_solver_starts == 0; they are never physical evidence.
The REAL-adapter wiring tests inject a fake A1 evaluate callable that returns
synthetic dreal001.aero_eval.v1 records (and synthetic attempt rows); no
vspaero.exe is launched and those numbers are not evidence either.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from research.concorde_metaopt.dreal001.optimizers import (
    ADAPTIVE_ARM_IDS,
    ARM_IDS,
    BACKEND_MOCK,
    BACKEND_REAL,
    DIMENSION,
    LIFT_TOL_REL,
    ArmSpec,
    EvaluationCache,
    MockLiftMatchEvaluator,
    PreregistrationConfig,
    SolverBudgetExceeded,
    SolverStartLedger,
    VisibleLabelStore,
    WarmStartSpec,
    build_preregistration,
    build_task,
    canonical_x12,
    design_hash,
    run_arm,
    run_pilot,
    sref_from_x12,
)
from research.concorde_metaopt.dreal001.optimizers.pilot import (
    PilotNotApproved,
    approval_template,
    validate_approval,
)
from research.concorde_metaopt.dreal001.optimizers import (
    INTERNAL_SOLVER_CASES_PER_START,
    AccountingViolation,
    RealBackendUnavailable,
    RealSolverNotAuthorized,
    SCHEMA_VERSION,
    build_real_adapter,
    pilot_real_adapter_factory,
)
from research.concorde_metaopt.dreal001.optimizers.constants import RECORD_MOCK
from research.concorde_metaopt.dreal001.optimizers.evaluators import (
    BaseLiftMatchEvaluator,
    ProbeResult,
)
from research.concorde_metaopt.dreal001.optimizers.records import AlphaSample

X12 = np.full(DIMENSION, 0.5)


def _evaluator(tmp_path, design_space, *, run_id, arm="BO", seed=0, budget=8, cache=None, label_run="", visible_labels=True):
    task = build_task()
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = SolverStartLedger(
        run_dir,
        batch_id="pytest-batch",
        run_id=run_id,
        max_starts=budget,
        backend=BACKEND_MOCK,
        task_id=task.task_id,
        solver_config_sha256=task.solver_config_sha256,
    )
    cache = cache if cache is not None else EvaluationCache(run_dir / "evaluation_cache.json")
    label_store = VisibleLabelStore(label_run or run_id) if visible_labels else None
    evaluator = MockLiftMatchEvaluator(
        design_space,
        task,
        ledger,
        batch_id="pytest-batch",
        run_id=run_id,
        arm_id=arm,
        seed=seed,
        cache=cache,
        label_store=label_store,
        run_dir=run_dir,
    )
    return task, evaluator, ledger, cache, label_store, run_dir


def _read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def test_mock_evaluation_contract_and_accounting(tmp_path, design_space_12d):
    task, evaluator, ledger, _cache, label_store, run_dir = _evaluator(
        tmp_path, design_space_12d, run_id="contract"
    )
    evaluation = evaluator.evaluate(X12)

    assert evaluation.status == "VALID"
    assert evaluation.backend == BACKEND_MOCK
    assert evaluation.source_kind == "MOCK"
    assert evaluation.physical_solver_starts == 0
    assert evaluation.simulated_solver_starts >= 1
    assert evaluation.labels_visible_to_arm is True  # own paid label, in-run only
    assert evaluation.lift_rel_error is not None and evaluation.lift_rel_error <= LIFT_TOL_REL

    # D_i = q * Sref(x) * CDi and L = q * Sref(x) * CLtot, both on this model
    assert evaluation.D_i_N == pytest.approx(
        evaluation.q_Pa * evaluation.Sref_m2 * evaluation.CDi, rel=1e-6
    )
    assert evaluation.L_N == pytest.approx(
        evaluation.q_Pa * evaluation.Sref_m2 * evaluation.CLtot, rel=1e-6
    )
    assert evaluation.Sref_m2 > 0.0 and evaluation.D_i_N > 0.0

    summary = ledger.summary()
    assert summary["physical_solver_starts"] == 0
    assert summary["simulated_solver_starts"] == ledger.starts_used == 1
    assert summary["evaluations_requested"] == 1
    assert summary["unique_design_evals"] == 1
    assert summary["conservation_ok"] is True
    assert len(label_store) == 1

    assert len(_read_jsonl(run_dir / "solver_attempts.jsonl")) == 1
    assert len(_read_jsonl(run_dir / "evaluations.jsonl")) == 1

    # exact repeat in the same run is an in-run cache read: no new solver start
    again = evaluator.evaluate(X12)
    assert again.cache_hit is True
    assert again.simulated_solver_starts == 0
    assert ledger.summary()["cached_reads"] == 1
    assert ledger.starts_used == 1
    assert len(evaluator.history) == 2


def test_cache_isolation_between_runs_never_leaks_labels(tmp_path, design_space_12d):
    cache = EvaluationCache(tmp_path / "shared_cache.json")
    task_a, eval_a, ledger_a, cache, _label_a, _dir_a = _evaluator(
        tmp_path, design_space_12d, run_id="run-a", cache=cache
    )
    task_b, eval_b, ledger_b, cache, _label_b, _dir_b = _evaluator(
        tmp_path, design_space_12d, run_id="run-b", cache=cache
    )
    first = eval_a.evaluate(X12)
    assert first.cache_hit is False and ledger_a.starts_used == 1

    key = cache.key(canonical_x12(X12), task_a.fingerprint(), task_a.solver_config_sha256)
    assert cache.lookup_scoped(key, "run-a") is not None
    assert cache.lookup_scoped(key, "run-b") is None
    assert cache.foreign_entry(key, "run-b") is not None
    assert cache.runs_for_key(key) == ["run-a"]

    foreign = eval_b.evaluate(X12)
    assert foreign.cache_hit is False
    assert foreign.simulated_solver_starts >= 1
    assert ledger_b.starts_used == 1
    assert ledger_b.cached_reads == 0
    # same design evaluated in run-b is now an in-run read
    in_run = eval_b.evaluate(X12)
    assert in_run.cache_hit is True and ledger_b.starts_used == 1


def test_ledger_fails_closed_on_over_budget_and_double_settle(tmp_path):
    ledger = SolverStartLedger(
        tmp_path, batch_id="b", run_id="r", max_starts=1, backend=BACKEND_MOCK, task_id="t"
    )
    reservation = ledger.reserve(1)
    ledger.settle(reservation, 1)
    assert ledger.remaining_starts == 0
    with pytest.raises(SolverBudgetExceeded):
        ledger.reserve(1)
    ledger2 = SolverStartLedger(
        tmp_path, batch_id="b", run_id="r2", max_starts=2, backend=BACKEND_MOCK, task_id="t"
    )
    granted = ledger2.reserve(1)
    with pytest.raises(Exception):
        ledger2.settle(granted, 2)  # actual starts exceed reservation: accounting violation


def test_visible_label_store_is_run_scoped(tmp_path, design_space_12d):
    _task, eval_a, _la, _ca, labels_a, _da = _evaluator(tmp_path, design_space_12d, run_id="labels-a")
    _task, eval_b, _lb, _cb, labels_b, _db = _evaluator(tmp_path, design_space_12d, run_id="labels-b")
    eval_a.evaluate(X12)
    eval_a.evaluate(np.full(DIMENSION, 0.4))
    eval_b.evaluate(X12)
    assert len(labels_a) == 2 and len(labels_b) == 1
    assert labels_a.run_id == "labels-a" and labels_b.run_id == "labels-b"
    support = labels_a.to_support()
    assert support is not None and len(support["records"]) == 2


def test_six_arms_share_interface_and_conserve_budget(tmp_path, design_space_12d):
    budget = 8
    task = build_task()
    for arm in ARM_IDS:
        _task, evaluator, ledger, _cache, _labels, run_dir = _evaluator(
            tmp_path, design_space_12d, run_id="arm-" + arm, arm=arm, seed=3, budget=budget
        )
        spec = ArmSpec(
            arm_id=arm,
            budget_starts=budget,
            seed=3,
            batch_id="pytest-batch",
            run_id="arm-" + arm,
            warmstart=WarmStartSpec() if arm in ADAPTIVE_ARM_IDS else None,
        )
        result = run_arm(spec, task, design_space_12d, evaluator)
        result.write_artifacts(run_dir)
        summary = ledger.summary()

        assert result.status == "COMPLETED", (arm, result.status, result.optimizer)
        assert result.backend == BACKEND_MOCK
        assert result.physical_solver_starts == 0
        assert result.starts_used == budget, (arm, result.starts_used, budget)
        assert result.starts_used == summary["starts_used"]
        assert summary["physical_solver_starts"] == 0
        assert summary["conservation_ok"] is True
        assert result.best_valid_D_i_N is not None and np.isfinite(result.best_valid_D_i_N)
        assert result.first_feasible_solver_start is not None
        assert 1 <= result.first_feasible_solver_start <= budget
        assert 0.0 < result.valid_solve_rate <= 1.0

        # anytime data covers every evaluation and never worsens
        assert len(result.anytime) == result.evaluations_requested
        best_seen = None
        for row in result.anytime:
            value = row["best_valid_D_i_N"]
            if value is not None:
                if best_seen is not None:
                    assert value <= best_seen + 1e-9
                best_seen = value
        assert best_seen == pytest.approx(result.best_valid_D_i_N)
        if arm in ADAPTIVE_ARM_IDS:
            assert result.warmstart.get("physical_call_count") == 0
            assert result.warmstart.get("label_free") is True
            assert result.warmstart.get("in_run_labels_visible") == 0

        for name in (
            "arm_summary.json",
            "optimization_history.csv",
            "anytime_curve.csv",
            "solver_attempts.jsonl",
            "evaluations.jsonl",
        ):
            assert (run_dir / name).exists(), (arm, name)
        with (run_dir / "optimization_history.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == len(result.history)
        assert all(row["physical_solver_starts"] == "0" for row in rows)


def test_seeded_runs_are_reproducible(tmp_path, design_space_12d):
    task = build_task()
    best = []
    designs = []
    for replica in range(2):
        run_id = "repro-%d" % replica
        _task, evaluator, _ledger, _cache, _labels, _dir = _evaluator(
            tmp_path, design_space_12d, run_id=run_id, arm="DE", seed=7, budget=8
        )
        spec = ArmSpec(arm_id="DE", budget_starts=8, seed=7, batch_id="pytest-batch", run_id=run_id)
        result = run_arm(spec, task, design_space_12d, evaluator)
        best.append(result.best_valid_D_i_N)
        designs.append(result.best_design_unit)
    assert best[0] == pytest.approx(best[1], rel=1e-12)
    assert designs[0] == designs[1]


def test_real_execution_requires_signed_approval(tmp_path, design_space_12d):
    config = PreregistrationConfig(
        batch_id="pytest-approval",
        backend=BACKEND_MOCK,
        arms=("BO",),
        budgets=(4,),
        seeds=(0,),
    )
    plan = build_preregistration(config, task=build_task())
    template = approval_template(plan)
    assert template["approved"] is False
    with pytest.raises(PilotNotApproved):
        validate_approval(plan, template)
    forged = dict(template)
    forged.update({"approved": True, "plan_sha256": "0" * 64, "max_starts": plan["planned_starts"]})
    with pytest.raises(PilotNotApproved):
        validate_approval(plan, forged)
    signed = dict(template)
    signed.update(
        {
            "approved": True,
            "approved_by": "pytest",
            "plan_sha256": plan["plan_sha256"],
            "batch_id": plan["batch_id"],
            "max_starts": plan["planned_starts"],
        }
    )
    validate_approval(plan, signed)


def test_mock_pilot_end_to_end_and_plan_declarations(tmp_path, design_space_12d):
    config = PreregistrationConfig(
        batch_id="pytest-e2e",
        backend=BACKEND_MOCK,
        arms=("BO", "ADE"),
        budgets=(8,),
        seeds=(0, 1),
        warmstart=WarmStartSpec(source="zero_shot_surrogate", support_size=0),
    )
    plan = build_preregistration(config, task=build_task())
    assert plan["budget_metric"] == "physical_solver_starts"
    assert plan["fuel_burn_kg"] is None
    assert len(plan["run_matrix"]) == 4
    assert "label-free" in plan["warmstart_policy"]
    assert plan["planned_starts"] == 32

    batch = run_pilot(tmp_path / "pilot", plan, task=build_task(), design_space=design_space_12d)
    assert batch["n_runs_with_summary"] == 4
    assert batch["physical_solver_starts"] == 0
    assert batch["simulated_solver_starts"] == 32
    assert batch["budget_conserved"] is True
    assert batch["synthetic_not_real_solver"] is True
    assert batch["evidence_statement"] == "SYNTHETIC_NOT_REAL_SOLVER"
    assert batch["errors"] == []

    run_dirs = sorted((tmp_path / "pilot" / "pytest-e2e" / "runs").iterdir())
    assert len(run_dirs) == 4
    for run_dir in run_dirs:
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        assert summary["physical_solver_starts"] == 0
        assert summary["synthetic_not_real_solver"] is True
        assert summary["fuel_burn_kg"] is None
        assert summary["budget_starts"] == 8
        assert summary["starts_used"] <= summary["budget_starts"]
        assert summary["n_solver_attempt_rows"] == summary["starts_used"]
        for name in (
            "run_config.json",
            "evaluations.jsonl",
            "solver_attempts.jsonl",
            "optimization_history.csv",
            "anytime_curve.csv",
            "summary.json",
            "data_manifest.json",
            "SHA256SUMS.txt",
        ):
            assert (run_dir / name).exists(), (run_dir.name, name)


def test_mesh_family_covariate_round_trips_and_real_adapter_records_it(tmp_path, design_space_12d):
    """A1 E6-GAP-01: thin-mesh family is persisted and carried from the A1 record."""
    from research.concorde_metaopt.dreal001.optimizers.records import evaluation_from_dict
    from research.concorde_metaopt.dreal001.optimizers import RealVspaeroAdapter

    task, evaluator, _ledger, *_ = _evaluator(
        tmp_path, design_space_12d, run_id="mesh-records", budget=2
    )
    record = evaluator.evaluate(X12)
    row = record.as_dict()
    assert row["mesh_family"] == ""
    row["mesh_family"] = "483/418"
    row["mesh_nodes"] = 483
    row["mesh_elements"] = 418
    row["normalized_geometry_hash"] = "norm-483"
    row["vspgeom_sha256"] = "vsp-483"
    restored = evaluation_from_dict(row)
    assert restored.mesh_family == "483/418"
    assert restored.mesh_nodes == 483
    assert restored.mesh_elements == 418
    assert restored.normalized_geometry_hash == "norm-483"
    assert restored.vspgeom_sha256 == "vsp-483"
    assert restored.as_dict()["mesh_family"] == "483/418"
    assert restored.as_dict()["normalized_geometry_hash"] == "norm-483"

    real_dir = tmp_path / "real-mesh"
    real_dir.mkdir(parents=True, exist_ok=True)
    real_ledger = SolverStartLedger(
        real_dir,
        batch_id="pytest-real-mesh",
        run_id="real-mesh",
        max_starts=4,
        backend=BACKEND_REAL,
        task_id=task.task_id,
        solver_config_sha256=task.solver_config_sha256,
    )
    attempts_path = real_dir / "solver_attempts.jsonl"
    attempts_path.write_text("", encoding="utf-8")

    def fake_evaluate(vector, case_id=None, meta=None):
        return {
            "status": "SOLVED_VALID",
            "backend": "REAL_VSPAERO",
            "solver": {
                "physical_solver_starts": 0,
                "solver_config_sha256": task.solver_config_sha256,
                "command": ["vspaero"],
            },
            "geometry": {
                "geometry_sha256": "deadbeef",
                "mesh_family": "483/418",
                "mesh_nodes": 483,
                "mesh_elements": 418,
                "normalized_geometry_hash": "norm-483",
                "vspgeom_sha256": "vsp-483",
            },
            "results": {
                "alpha_deg": [2.0, 3.0],
                "cltot": [0.20, 0.30],
                "cdi": [0.010, 0.020],
                "cdo": [0.005, 0.006],
                "cdtot": [0.015, 0.026],
                "cmy": [0.0, 0.0],
            },
            "attempt_ids": [],
            "raw_artifacts": [],
            "errors": [],
        }

    adapter = RealVspaeroAdapter(
        design_space_12d,
        task,
        real_ledger,
        evaluate_fn=fake_evaluate,
        approval={"approved": True, "batch_id": "pytest-real-mesh", "max_starts": 4},
        external_attempts_path=attempts_path,
    )
    probe = adapter._probe_batch(np.full(DIMENSION, 0.5), [2.0, 3.0], "case-mesh")
    assert probe.mesh_family == "483/418"
    assert probe.mesh_nodes == 483
    assert probe.mesh_elements == 418
    assert probe.normalized_geometry_hash == "norm-483"
    assert probe.vspgeom_sha256 == "vsp-483"
    assert probe.launches == 0
    assert real_ledger.starts_used == 0


def test_real_cache_key_includes_mesh_family_and_forbids_cross_run_reuse(tmp_path, design_space_12d):
    """Lead m00426: REAL labels keyed by mesh family + normalized geometry; cross-run reuse fails closed."""
    from research.concorde_metaopt.dreal001.optimizers import CrossRunCacheReuse, RealVspaeroAdapter

    task = build_task()
    cache = EvaluationCache(tmp_path / "real_cache.json")
    cl_target = task.cl_required(sref_from_x12(design_space_12d, X12))

    def make_adapter(run_id):
        run_dir = tmp_path / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        ledger = SolverStartLedger(
            run_dir,
            batch_id="pytest-real-cache",
            run_id=run_id,
            max_starts=4,
            backend=BACKEND_REAL,
            task_id=task.task_id,
            solver_config_sha256=task.solver_config_sha256,
        )
        attempts_path = run_dir / "a1_solver_attempts.jsonl"
        attempts_path.write_text("", encoding="utf-8")

        def fake_evaluate(vector, case_id=None, meta=None):
            return {
                "status": "SOLVED_VALID",
                "backend": "REAL_VSPAERO",
                "solver": {
                    "physical_solver_starts": 0,
                    "solver_config_sha256": task.solver_config_sha256,
                    "command": ["vspaero"],
                },
                "geometry": {
                    "geometry_sha256": "vsp-483",
                    "mesh_family": "483/418",
                    "mesh_nodes": 483,
                    "mesh_elements": 418,
                    "normalized_geometry_hash": "norm-483",
                    "vspgeom_sha256": "vsp-483",
                },
                "results": {
                    "alpha_deg": [2.0, 3.0],
                    "cltot": [cl_target * 0.9, cl_target * 1.1],
                    "cdi": [0.010, 0.020],
                    "cdo": [0.005, 0.006],
                    "cdtot": [0.015, 0.026],
                    "cmy": [0.0, 0.0],
                },
                "attempt_ids": [],
                "raw_artifacts": [],
                "errors": [],
            }

        adapter = RealVspaeroAdapter(
            design_space_12d,
            task,
            ledger,
            evaluate_fn=fake_evaluate,
            approval={"approved": True, "batch_id": "pytest-real-cache", "max_starts": 4},
            external_attempts_path=attempts_path,
            batch_id="pytest-real-cache",
            run_id=run_id,
            arm_id="BO",
            seed=0,
            cache=cache,
        )
        return adapter, ledger

    adapter, ledger = make_adapter("real-a")
    first = adapter.evaluate(X12)
    assert first.cache_hit is False
    assert first.backend == BACKEND_REAL
    assert first.physical_solver_starts == 0  # fake A1 reports zero starts
    assert first.mesh_family == "483/418"
    assert first.normalized_geometry_hash == "norm-483"
    assert first.vspgeom_sha256 == "vsp-483"

    design_key = adapter.cache_key(canonical_x12(X12))
    assert first.cache_key != design_key  # REAL entry key includes mesh covariates
    assert cache.lookup_scoped(design_key, "real-a") is None
    variants = cache.lookup_design_scoped(design_key, "real-a")
    assert len(variants) == 1
    assert variants[0]["key"] == first.cache_key
    assert variants[0]["mesh_family"] == "483/418"
    assert variants[0]["normalized_geometry_hash"] == "norm-483"

    repeat = adapter.evaluate(X12)
    assert repeat.cache_hit is True
    assert repeat.mesh_family == "483/418"
    assert repeat.normalized_geometry_hash == "norm-483"
    assert ledger.cached_reads == 1

    # a second mesh variant of the same design makes intra-run reuse ambiguous:
    # the design is re-measured rather than mixing families.
    cache.store(
        "mesh-family-b-entry",
        "real-a",
        {"status": "VALID"},
        design_key=design_key,
        mesh_family="543/472",
        normalized_geometry_hash="norm-543",
        vspgeom_sha256="vsp-543",
    )
    assert len(cache.lookup_design_scoped(design_key, "real-a")) == 2
    ambiguous = adapter.evaluate(X12)
    assert ambiguous.cache_hit is False
    assert ledger.cached_reads == 1

    # persisted v2 metadata survives save/load
    cache.save()
    reloaded = EvaluationCache.load(cache.path)
    variants_reloaded = reloaded.lookup_design_scoped(design_key, "real-a")
    assert len(variants_reloaded) == 2
    families = sorted(item["mesh_family"] for item in variants_reloaded)
    assert families == ["483/418", "543/472"]

    # REAL adapter for another run must refuse to serve this cache (fail closed)
    adapter_b, _ledger_b = make_adapter("real-b")
    with pytest.raises(CrossRunCacheReuse):
        adapter_b.evaluate(X12)


def test_real_adapter_rejects_label_without_mesh_covariates(tmp_path, design_space_12d):
    """Lead m00426: a REAL label without mesh_family / normalized hash must fail closed."""
    from research.concorde_metaopt.dreal001.optimizers import AccountingViolation, RealVspaeroAdapter

    task = build_task()
    run_dir = tmp_path / "real-nocov"
    run_dir.mkdir()
    ledger = SolverStartLedger(
        run_dir,
        batch_id="pytest-no-mesh",
        run_id="real-nocov",
        max_starts=4,
        backend=BACKEND_REAL,
        task_id=task.task_id,
        solver_config_sha256=task.solver_config_sha256,
    )
    attempts_path = run_dir / "a1_solver_attempts.jsonl"
    attempts_path.write_text("", encoding="utf-8")
    cl_target = task.cl_required(sref_from_x12(design_space_12d, X12))

    def fake_evaluate(vector, case_id=None, meta=None):
        return {
            "status": "SOLVED_VALID",
            "backend": "REAL_VSPAERO",
            "solver": {
                "physical_solver_starts": 0,
                "solver_config_sha256": task.solver_config_sha256,
                "command": ["vspaero"],
            },
            "geometry": {"geometry_sha256": "vsp-no-mesh"},  # no mesh covariates
            "results": {
                "alpha_deg": [2.0, 3.0],
                "cltot": [cl_target * 0.9, cl_target * 1.1],
                "cdi": [0.010, 0.020],
                "cdo": [0.005, 0.006],
                "cdtot": [0.015, 0.026],
                "cmy": [0.0, 0.0],
            },
            "attempt_ids": [],
            "raw_artifacts": [],
            "errors": [],
        }

    adapter = RealVspaeroAdapter(
        design_space_12d,
        task,
        ledger,
        evaluate_fn=fake_evaluate,
        approval={"approved": True, "batch_id": "pytest-no-mesh", "max_starts": 4},
        external_attempts_path=attempts_path,
        batch_id="pytest-no-mesh",
        run_id="real-nocov",
        arm_id="BO",
        seed=0,
    )
    with pytest.raises(AccountingViolation):
        adapter.evaluate(X12)
    assert adapter.cache is None
    assert ledger.starts_used == 0


# ---------------------------------------------------------------------------
# REAL backend wiring: fake A1 records only, no vspaero.exe is ever launched.
# ---------------------------------------------------------------------------

ALPHA_GRID = (-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0)


def _a1_physical_x12(design_space, unit_vector):
    physical = design_space.from_unit_interval([float(value) for value in unit_vector])
    names = list(design_space.names)
    assert len(names) == DIMENSION
    return [float(physical[name]) for name in names]


def _a1_v1_record(*, task, x12_physical, starts=1, cltot=None):
    cl = list(cltot) if cltot is not None else [0.05, 0.09, 0.13, 0.17, 0.21, 0.25, 0.29]
    cdi = [0.0060, 0.0064, 0.0068, 0.0072, 0.0076, 0.0080, 0.0084]
    cdo = [0.0040] * 7
    cdtot = [i + j for i, j in zip(cdi, cdo)]
    attempt_id = "a1-attempt-01"
    return {
        "schema_version": SCHEMA_VERSION,
        "evaluator_id": "a1-real-vspaero:test",
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
            "attempt_ids": [attempt_id],
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
        "attempt_ids": [attempt_id],
        "raw_artifacts": [],
        "errors": [],
        "fuel_burn_kg": None,
        "objective": {"name": "D_i_N", "value": None, "unit": "N"},
    }


class _FakeAeroEvaluator:
    """Stand-in for A1's AeroEvaluator; writes an A1-style attempt row."""

    def __init__(self, design_space, **kwargs):
        self.design_space = design_space
        self.kwargs = dict(kwargs)
        self.calls = []

    def _record(self, x12_physical):
        return _a1_v1_record(task=self.kwargs["task"], x12_physical=x12_physical, starts=1)

    def evaluate(self, x12, case_id=None, meta=None):
        x12_physical = [float(value) for value in x12]
        self.calls.append({"x12": x12_physical, "case_id": case_id, "meta": dict(meta or {})})
        record = self._record(x12_physical)
        attempts_path = Path(self.kwargs["run_dir"]) / "solver_attempts.jsonl"
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
        return record


class _UnbracketedFakeAeroEvaluator(_FakeAeroEvaluator):
    def _record(self, x12_physical):
        return _a1_v1_record(
            task=self.kwargs["task"],
            x12_physical=x12_physical,
            starts=1,
            cltot=[0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05],
        )


def _real_adapter(tmp_path, design_space_12d, *, run_id, factory, attempt_name="solver_attempts.jsonl", approval=None):
    task = build_task()
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = SolverStartLedger(
        run_dir,
        batch_id="pytest-real-wire",
        run_id=run_id,
        max_starts=4,
        backend=BACKEND_REAL,
        task_id=task.task_id,
        solver_config_sha256=task.solver_config_sha256,
    )
    cache = EvaluationCache(run_dir / "evaluation_cache.json")
    adapter = build_real_adapter(
        design_space=design_space_12d,
        task=task,
        ledger=ledger,
        run_dir=run_dir,
        approval=approval or {"approved": True, "batch_id": "pytest-real-wire", "max_starts": 4},
        a1_evaluator_factory=factory,
        a1_evaluator_kwargs={"task": task},
        batch_id="pytest-real-wire",
        run_id=run_id,
        arm_id="BO",
        seed=0,
        cache=cache,
        label_store=VisibleLabelStore(run_id),
    )
    return task, adapter, ledger, cache, run_dir


def test_real_adapter_maps_a1_v1_record_and_verifies_attempts(tmp_path, design_space_12d):
    task, adapter, ledger, cache, run_dir = _real_adapter(
        tmp_path, design_space_12d, run_id="real-wire", factory=_FakeAeroEvaluator
    )
    evaluation = adapter.evaluate(X12)

    assert evaluation.status == "VALID"
    assert evaluation.record_status == "SOLVED_VALID"
    assert evaluation.backend == BACKEND_REAL
    assert evaluation.physical_solver_starts == 1
    assert evaluation.simulated_solver_starts == 0
    assert evaluation.mesh_family == "543/472"
    assert evaluation.mesh_nodes == 543
    assert evaluation.mesh_elements == 472
    assert evaluation.normalized_geometry_hash == "c" * 64
    assert evaluation.D_i_N == pytest.approx(evaluation.q_Pa * evaluation.Sref_m2 * evaluation.CDi, rel=1e-6)
    assert ledger.physical_solver_starts == 1
    assert ledger.internal_solver_cases == 7
    assert cache.forbid_cross_run_reuse is True
    assert len(_read_jsonl(run_dir / "solver_attempts.jsonl")) == 1

    calls = adapter.a1_evaluator.calls
    assert len(calls) == 1
    assert calls[0]["meta"]["phase"] == "primary"
    assert calls[0]["x12"] == pytest.approx(_a1_physical_x12(design_space_12d, X12))
    assert adapter.a1_evaluator.kwargs["allow_physical_starts"] is False

    cached = adapter.evaluate(X12)
    assert cached.cache_hit is True
    assert cached.physical_solver_starts == 0
    assert ledger.physical_solver_starts == 1
    assert ledger.cached_reads == 1


def test_real_adapter_lift_failure_does_not_spend_second_launch(tmp_path, design_space_12d):
    _task, adapter, ledger, _cache, run_dir = _real_adapter(
        tmp_path, design_space_12d, run_id="real-unbracketed", factory=_UnbracketedFakeAeroEvaluator
    )
    evaluation = adapter.evaluate(X12)

    assert evaluation.status == "NOT_CONVERGED"
    assert evaluation.record_status == "LIFT_MATCH_FAILED"
    assert evaluation.physical_solver_starts == 1
    assert len(adapter.a1_evaluator.calls) == 1  # A1 v1.0 has no alpha override: no refine launch
    assert ledger.physical_solver_starts == 1
    assert len(_read_jsonl(run_dir / "solver_attempts.jsonl")) == 1


def test_build_real_adapter_fails_closed_without_authorization(tmp_path, design_space_12d):
    task = build_task()
    run_dir = tmp_path / "real-closed"
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = SolverStartLedger(
        run_dir,
        batch_id="pytest-real-closed",
        run_id="real-closed",
        max_starts=2,
        backend=BACKEND_REAL,
        task_id=task.task_id,
        solver_config_sha256=task.solver_config_sha256,
    )
    approval = {"approved": True, "batch_id": "pytest-real-closed", "max_starts": 2}
    common = dict(
        design_space=design_space_12d,
        task=task,
        ledger=ledger,
        run_dir=run_dir,
        a1_evaluator_factory=_FakeAeroEvaluator,
        batch_id="pytest-real-closed",
        run_id="real-closed",
        arm_id="BO",
        seed=0,
    )
    with pytest.raises(RealSolverNotAuthorized):
        build_real_adapter(**common, approval=approval, allow_physical_starts=True, spawn=None)
    with pytest.raises(RealSolverNotAuthorized):
        build_real_adapter(**common, approval={"approved": False, "batch_id": "pytest-real-closed", "max_starts": 2})
    with pytest.raises(RealBackendUnavailable):
        build_real_adapter(
            design_space=design_space_12d,
            task=task,
            ledger=ledger,
            run_dir=run_dir,
            approval=approval,
            a1_module_name="does.not.exist.a1_evaluator",
            batch_id="pytest-real-closed",
            run_id="real-closed",
            arm_id="BO",
            seed=0,
        )


class _TwoStageEvaluator(BaseLiftMatchEvaluator):
    """Synthetic non-REAL evaluator with a primary + optional refine sweep."""

    backend = BACKEND_MOCK
    source_kind = "SYNTHETIC_TEST"
    physical_validation_status = "NOT_VALIDATED"
    supports_alpha_sweep = True
    supports_refine_sweep = True
    requires_starts = True

    def __init__(self, design_space, task, ledger, **kwargs):
        super().__init__(design_space, task, ledger, **kwargs)
        self.calls = []
        self._launch = 0

    @staticmethod
    def _samples(alphas, cltot):
        return [
            AlphaSample(alpha_deg=float(alpha), cltot=float(cl), cdi=0.01, cdo=0.004, cdtot=0.014, cm=(0.0, 0.0, 0.0))
            for alpha, cl in zip(alphas, cltot)
        ]

    def _probe_batch(self, vector, alphas, case_id, *, phase="primary"):
        self.calls.append((phase, tuple(float(alpha) for alpha in alphas)))
        self._launch += 1
        if phase == "primary":
            cltot = [0.01 + 0.005 * index for index in range(len(alphas))]
            status = RECORD_MOCK
        else:
            cltot = [0.05 + 0.02 * float(alpha) for alpha in alphas]
            status = RECORD_MOCK
        return ProbeResult(
            samples=self._samples(alphas, cltot),
            launches=1,
            status=status,
            attempt_refs=("synthetic-a%02d" % self._launch,),
        )


def test_refine_accounting_and_no_refine_gate(tmp_path, design_space_12d):
    task = build_task()
    expectations = ((True, "VALID", 2), (False, "NOT_CONVERGED", 1))
    for enable_refine, expected_status, expected_calls in expectations:
        run_id = "refine-%s" % enable_refine
        run_dir = tmp_path / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        ledger = SolverStartLedger(
            run_dir,
            batch_id="pytest-refine",
            run_id=run_id,
            max_starts=2,
            backend=BACKEND_MOCK,
            task_id=task.task_id,
            solver_config_sha256=task.solver_config_sha256,
        )
        evaluator = _TwoStageEvaluator(
            design_space_12d,
            task,
            ledger,
            batch_id="pytest-refine",
            run_id=run_id,
            arm_id="BO",
            seed=0,
        )
        if not enable_refine:
            evaluator.supports_refine_sweep = False
        evaluation = evaluator.evaluate(X12)

        assert len(evaluator.calls) == expected_calls
        assert [phase for phase, _alphas in evaluator.calls][0] == "primary"
        assert evaluation.status == expected_status
        assert evaluation.physical_solver_starts == 0
        assert ledger.starts_used == expected_calls
        if enable_refine:
            assert evaluation.refines_used == 1
            assert evaluator.calls[1][0] == "refine"


def test_real_pilot_zero_physical_with_injected_fake_a1_factory(tmp_path, design_space_12d):
    task = build_task()
    config = PreregistrationConfig(
        batch_id="pytest-real-pilot",
        backend=BACKEND_REAL,
        arms=("BO",),
        budgets=(2,),
        seeds=(0,),
    )
    plan = build_preregistration(config, task=task)
    approval = {
        "approved": True,
        "plan_sha256": plan["plan_sha256"],
        "batch_id": plan["batch_id"],
        "max_starts": plan["planned_starts"],
        "max_internal_solver_cases": plan["budget_model"]["max_internal_solver_cases"],
    }

    class _NotRunA1Evaluator:
        def __init__(self, design_space, **kwargs):
            self.kwargs = dict(kwargs)
            self.calls = []

        def evaluate(self, x12, case_id=None, meta=None):
            self.calls.append(case_id)
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "NOT_RUN",
                "backend": BACKEND_REAL,
                "design": {"x12": [float(value) for value in x12]},
                "solver": {
                    "physical_solver_starts": 0,
                    "internal_solver_cases": 0,
                    "internal_solver_cases_expected": 7,
                    "solver_config_sha256": task.solver_config_sha256,
                    "command": ["vspaero"],
                },
                "geometry": {},
                "results": {
                    "alpha_deg": [],
                    "cltot": [],
                    "cdi": [],
                    "cdo": [],
                    "cdtot": [],
                    "cmy": [],
                },
                "physical_solver_starts": 0,
                "attempt_ids": [],
                "raw_artifacts": [],
                "errors": [],
            }

    factory = pilot_real_adapter_factory(
        a1_evaluator_factory=_NotRunA1Evaluator, allow_physical_starts=False
    )
    batch = run_pilot(
        tmp_path / "realpilot",
        plan,
        task=task,
        design_space=design_space_12d,
        approval=approval,
        real_adapter_factory=factory,
    )

    assert batch["backend"] == BACKEND_REAL
    assert batch["physical_solver_starts"] == 0
    assert batch["errors"] == []
    assert batch["budget_conserved"] is True
    run_dir = tmp_path / "realpilot" / plan["batch_id"] / "runs" / plan["run_matrix"][0]["run_id"]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    run_config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
    assert summary["physical_solver_starts"] == 0
    assert summary["physical_starts_authorized"] is False
    assert summary["internal_solver_cases"] == 0
    assert run_config["real_starts_authorized"] is False
    assert run_config["a1_evaluator_contract"]["schema_version"] == SCHEMA_VERSION
    assert (
        run_config["budget_model"]["internal_solver_cases_per_start"]
        == INTERNAL_SOLVER_CASES_PER_START
    )
    assert run_config["cache"]["cross_run_reuse"] == "forbidden"


def test_force_rerun_excludes_stale_runs_from_batch_aggregation(tmp_path, design_space_12d):
    task = build_task()
    plan = build_preregistration(
        PreregistrationConfig(
            batch_id="pytest-force",
            backend=BACKEND_MOCK,
            arms=("BO",),
            budgets=(2,),
            seeds=(0,),
        ),
        task=task,
    )
    run_pilot(tmp_path / "force", plan, task=task, design_space=design_space_12d)
    second = run_pilot(
        tmp_path / "force",
        plan,
        task=task,
        design_space=design_space_12d,
        resume=False,
        force=True,
    )
    assert second["n_runs_with_summary"] == 1
    assert second["simulated_solver_starts"] == 2
    assert second["budget_conserved"] is True
    stale = list((tmp_path / "force" / plan["batch_id"] / "runs").glob("_stale_*"))
    assert len(stale) == 1

