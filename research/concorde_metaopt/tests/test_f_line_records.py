"""F1 记录契约：失败值必须为 null、约束补全顺序、物理调用来源限制。

这些测试不启动任何真实求解器（physical_call_count 恒为 0）。
"""

import pytest

from research.concorde_metaopt.f_line import (
    CONSTRAINT_NAMES,
    EvaluationRecord,
    STATUS_GEOMETRY_INVALID,
    STATUS_SOLVER_NONCONVERGED,
    STATUS_VALID,
    SOURCE_KIND_ARCHIVE_REPLAY,
    SOURCE_KIND_SYNTHETIC_MOCK,
    canonical_design_sha256,
    ordered_constraints,
)

DESIGN = {"wing_area": 358.25, "aspect_ratio": 1.83}


def make_record(**overrides):
    payload = dict(
        run_id="f1-test",
        task_id="concorde-fixed-cruise-p2-v1",
        design=dict(DESIGN),
        design_sha256=canonical_design_sha256(DESIGN),
        evaluator_id="unit-test",
        fidelity="synthetic",
        source_kind=SOURCE_KIND_SYNTHETIC_MOCK,
        physical_validation_status="NOT_APPLICABLE",
        solver_version="unit-0",
        objective=34109.482571,
        constraints={"geometry_invalid": 0.0},
        status=STATUS_VALID,
    )
    payload.update(overrides)
    return EvaluationRecord(**payload)


def test_valid_record_completes_constraints_in_frozen_order():
    record = make_record()
    assert record.status == STATUS_VALID
    assert record.objective is not None
    assert list(record.constraints) == list(CONSTRAINT_NAMES)
    assert len(record.constraints) == 10
    assert record.feasible is True
    assert record.objective_is_null is False


def test_valid_record_rejects_null_objective():
    with pytest.raises(ValueError):
        make_record(objective=None)


def test_failure_record_must_carry_null_objective():
    record = make_record(
        status=STATUS_GEOMETRY_INVALID, objective=None, constraints={"geometry_invalid": 1.0}
    )
    assert record.objective is None
    assert record.feasible is False
    assert record.objective_is_null is True
    with pytest.raises(ValueError):
        make_record(objective=1.0, status=STATUS_SOLVER_NONCONVERGED)


def test_software_sources_cannot_bill_physical_calls():
    with pytest.raises(ValueError):
        make_record(physical_call_count=1)
    with pytest.raises(ValueError):
        make_record(source_kind=SOURCE_KIND_ARCHIVE_REPLAY, physical_call_count=1)
    untouched = make_record(physical_call_count=0)
    assert untouched.has_physical_evidence is False


def test_unknown_constraint_name_is_rejected():
    with pytest.raises(ValueError):
        ordered_constraints({"drag_count": 0.0})
    with pytest.raises(ValueError):
        make_record(constraints={"bogus": 0.0})


def test_infeasible_constraint_keeps_status_but_flips_feasible():
    record = make_record(constraints={"max_throttle": 0.05, "geometry_invalid": 0.0})
    assert record.status == STATUS_VALID
    assert record.feasible is False


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError):
        make_record(status="PASS")
