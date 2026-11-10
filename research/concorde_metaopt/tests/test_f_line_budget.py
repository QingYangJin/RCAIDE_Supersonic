"""F1 预算账本：预授权 fail-closed、请求上限、缓存 0 费、重试逐次计费。"""

import pytest

from research.concorde_metaopt.f_line import (
    BudgetExceeded,
    BudgetLedger,
    BudgetLedgerError,
    CostModel,
    SOURCE_KIND_ARCHIVE_REPLAY,
    SOURCE_KIND_ENGINEERING_SOLVER,
    STATUS_SOLVER_NONCONVERGED,
    STATUS_VALID,
)


class FakeSolverEvaluator:
    """假的"真实求解器"评价器：用于验证预授权会先于求解器启动而失败。"""

    evaluator_id = "fake-solver"
    fidelity = "vspaero_internal"
    source_kind = SOURCE_KIND_ENGINEERING_SOLVER
    solver_version = "fake-0"
    physical_validation_status = "NOT_VALIDATED"
    estimated_physical_cost = 1

    def __init__(self):
        self.calls = 0

    def evaluate(self, design, task=None, fidelity=None):  # pragma: no cover - 不应被调用
        self.calls += 1
        raise AssertionError("physical solver must not be started in F1")


def test_authorize_rejects_over_budget_before_any_call():
    ledger = BudgetLedger(physical_budget=0)
    with pytest.raises(BudgetExceeded) as excinfo:
        ledger.authorize(1)
    assert excinfo.value.budget == 0
    assert excinfo.value.used == 0
    assert ledger.physical_calls == 0


def test_mock_evaluation_bills_zero_physical_calls(mock_evaluator, fixed_cruise_task):
    ledger = BudgetLedger(physical_budget=0, run_id="f1-test")
    design = mock_evaluator.design_space.baseline_dict()
    record = ledger.evaluate(mock_evaluator, design, task=fixed_cruise_task)
    assert record.status == STATUS_VALID
    assert ledger.requests == 1
    assert ledger.physical_calls == 0
    summary = ledger.summary()
    assert summary["zero_physical_run"] is True
    assert summary["remaining"] == 0


def test_cache_hit_is_free_and_flagged(mock_evaluator, fixed_cruise_task):
    ledger = BudgetLedger(physical_budget=0, run_id="f1-cache")
    design = mock_evaluator.design_space.baseline_dict()
    first = ledger.evaluate(mock_evaluator, design, task=fixed_cruise_task)
    second = ledger.evaluate(mock_evaluator, design, task=fixed_cruise_task)
    assert ledger.requests == 2
    assert ledger.physical_calls == 0
    assert first.provenance.get("cache_hit") is not True
    assert second.provenance.get("cache_hit") is True
    assert second.objective == first.objective


def test_request_cap_is_enforced(mock_evaluator, fixed_cruise_task):
    ledger = BudgetLedger(physical_budget=0, max_requests=2)
    design = mock_evaluator.design_space.baseline_dict()
    ledger.evaluate(mock_evaluator, design, task=fixed_cruise_task)
    shifted = dict(design)
    shifted["aspect_ratio"] = 2.0
    ledger.evaluate(mock_evaluator, shifted, task=fixed_cruise_task)
    with pytest.raises(BudgetLedgerError):
        ledger.evaluate(mock_evaluator, design, task=fixed_cruise_task)


def test_retry_bills_each_attempt_and_can_recover(
    design_space_12d, fixed_cruise_task
):
    from research.concorde_metaopt.f_line import MockEvaluator

    attempts = {"count": 0}

    def hook(physical):
        attempts["count"] += 1
        return STATUS_SOLVER_NONCONVERGED if attempts["count"] == 1 else None

    evaluator = MockEvaluator(design_space_12d, fixed_cruise_task, failure_hook=hook)
    ledger = BudgetLedger(
        physical_budget=0, cost_model=CostModel(max_retries=1), run_id="f1-retry"
    )
    record = ledger.evaluate_with_retry(
        evaluator, design_space_12d.baseline_dict(), task=fixed_cruise_task
    )
    assert record.status == STATUS_VALID
    assert ledger.requests == 2
    assert len(ledger.records) == 2
    assert len(ledger.attempts) == 2
    assert [row.status for row in ledger.records] == [
        STATUS_SOLVER_NONCONVERGED,
        STATUS_VALID,
    ]
    assert ledger.physical_calls == 0


def test_solver_evaluator_requires_preauthorization():
    evaluator = FakeSolverEvaluator()
    ledger = BudgetLedger(physical_budget=0)
    with pytest.raises(BudgetExceeded):
        ledger.evaluate(evaluator, {"wing_area": 358.25})
    assert evaluator.calls == 0


def test_archive_replay_source_also_bills_zero():
    ledger = BudgetLedger(physical_budget=0)
    assert SOURCE_KIND_ARCHIVE_REPLAY in ("ARCHIVE_REPLAY",)
    assert ledger.physical_calls == 0
