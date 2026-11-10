"""F1 合成评价器：基线锚点、几何拒绝、注入失败、确定性。"""

import pytest

from research.concorde_metaopt.f_line import (
    CONSTRAINT_NAMES,
    STATUS_EVALUATOR_ERROR,
    STATUS_GEOMETRY_INVALID,
    STATUS_SOLVER_NONCONVERGED,
    STATUS_VALID,
)
from research.concorde_metaopt.f_line.mock_evaluator import BASELINE_FUEL_KG


def test_baseline_is_valid_and_anchored(mock_evaluator):
    record = mock_evaluator.evaluate(mock_evaluator.design_space.baseline_dict())
    assert record.status == STATUS_VALID
    assert record.feasible is True
    assert record.objective == pytest.approx(BASELINE_FUEL_KG, abs=1e-6)
    assert record.physical_call_count == 0
    assert record.source_kind == "SYNTHETIC_MOCK"
    assert record.physical_validation_status == "NOT_APPLICABLE"
    assert list(record.constraints) == list(CONSTRAINT_NAMES)
    assert record.constraints["geometry_invalid"] == 0.0
    assert record.constraints["cruise_range_error"] == pytest.approx(0.0, abs=1e-12)
    assert record.provenance["model"] == "synthetic_linear_placeholder"


def test_out_of_bounds_design_is_geometry_invalid(mock_evaluator):
    design = mock_evaluator.design_space.baseline_dict()
    design["wing_area"] = 500.0  # 上界 420.0
    record = mock_evaluator.evaluate(design)
    assert record.status == STATUS_GEOMETRY_INVALID
    assert record.objective is None
    assert record.feasible is False
    assert record.constraints["geometry_invalid"] == 1.0
    assert record.physical_call_count == 0


def test_cross_constraint_violation_is_geometry_invalid(mock_evaluator):
    design = mock_evaluator.design_space.baseline_dict()
    design["span_location_2"] = 0.97
    design["span_location_3"] = 0.86  # 违反 C01: span_location_2 < span_location_3
    record = mock_evaluator.evaluate(design)
    assert record.status == STATUS_GEOMETRY_INVALID
    assert record.objective is None


def test_injected_nonconvergence_has_null_objective(design_space_12d, fixed_cruise_task):
    from research.concorde_metaopt.f_line import MockEvaluator

    evaluator = MockEvaluator(
        design_space_12d,
        fixed_cruise_task,
        failure_hook=lambda physical: STATUS_SOLVER_NONCONVERGED,
    )
    record = evaluator.evaluate(design_space_12d.baseline_dict())
    assert record.status == STATUS_SOLVER_NONCONVERGED
    assert record.objective is None
    assert record.physical_call_count == 0


def test_injected_exception_is_propagated_for_ledger(design_space_12d, fixed_cruise_task):
    from research.concorde_metaopt.f_line import BudgetLedgerError, BudgetLedger, MockEvaluator

    evaluator = MockEvaluator(
        design_space_12d,
        fixed_cruise_task,
        raise_hook=lambda physical: RuntimeError("boom"),
    )
    ledger = BudgetLedger(physical_budget=0)
    with pytest.raises(BudgetLedgerError):
        ledger.evaluate(evaluator, design_space_12d.baseline_dict())
    assert ledger.physical_calls == 0


def test_synthetic_response_is_deterministic(design_space_12d, fixed_cruise_task):
    from research.concorde_metaopt.f_line import MockEvaluator

    noisy = MockEvaluator(design_space_12d, fixed_cruise_task, noise_kg=25.0)
    design = design_space_12d.baseline_dict()
    first = noisy.evaluate(design)
    second = noisy.evaluate(design)
    assert first.objective == second.objective
    assert (first.design_sha256, second.design_sha256) == (
        first.design_sha256,
        first.design_sha256,
    )
    assert first.design_sha256 == second.design_sha256


def test_full_15_variable_design_is_accepted(mock_evaluator):
    record = mock_evaluator.evaluate(mock_evaluator.design_space.full_baseline_dict())
    assert record.status == STATUS_VALID
    assert len(record.design) == 15
    assert record.objective == pytest.approx(BASELINE_FUEL_KG, abs=1e-6)


def test_fidelity_mismatch_is_rejected(mock_evaluator):
    with pytest.raises(ValueError):
        mock_evaluator.evaluate(mock_evaluator.design_space.baseline_dict(), fidelity="single_cruise")
