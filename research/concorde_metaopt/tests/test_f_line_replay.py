"""F1 归档 replay：只读归档、精确匹配、物理状态保持 NOT_VALIDATED。"""

import pytest

from research.concorde_metaopt.f_line import (
    ArchiveReplayEvaluator,
    BudgetLedger,
    STATUS_EVALUATOR_ERROR,
    STATUS_PHYSICS_NOT_VALIDATED,
)

CG_X_M = 28.287395109126685
WING_AC_X_M = 16.821978259514246


def test_archive_index_has_31_designs(archive_replay_evaluator):
    assert archive_replay_evaluator.available_design_count == 31
    assert archive_replay_evaluator.evaluator_id == "archive-replay-geometry-p1-1835-v1"
    assert archive_replay_evaluator.source_kind == "ARCHIVE_REPLAY"


def test_baseline_replay_matches_archived_baseline(archive_replay_evaluator):
    record = archive_replay_evaluator.evaluate(archive_replay_evaluator.design_space.baseline_dict())
    assert record.status == STATUS_PHYSICS_NOT_VALIDATED
    assert record.objective is None
    assert record.physical_validation_status == "NOT_VALIDATED"
    assert record.physical_call_count == 0
    assert record.provenance["matched_design_id"] == "baseline"
    assert record.provenance["archive_sha256"].startswith("5850a57c")
    metrics = record.provenance["archived_metrics"]
    assert metrics["cg_x_m"] == pytest.approx(CG_X_M, abs=1e-9)
    assert metrics["wing_ac_x_m"] == pytest.approx(WING_AC_X_M, abs=1e-9)
    # 机翼 AC 不是全机 CG：两者相差 > 11 m，绝不能混用。
    assert abs(metrics["wing_ac_x_m"] - metrics["cg_x_m"]) > 11.0


def test_unmatched_design_fails_closed(archive_replay_evaluator):
    design = archive_replay_evaluator.design_space.baseline_dict()
    variable = archive_replay_evaluator.design_space.variable("wing_area")
    design["wing_area"] = 0.5 * (variable.lower + variable.upper)
    record = archive_replay_evaluator.evaluate(design)
    assert record.status == STATUS_EVALUATOR_ERROR
    assert record.objective is None
    assert "requested_design_sha256" in record.provenance


def test_replay_design_sha256_is_stable(design_space_12d, fixed_cruise_task):
    first = ArchiveReplayEvaluator(design_space_12d, fixed_cruise_task)
    second = ArchiveReplayEvaluator(design_space_12d, fixed_cruise_task)
    design = design_space_12d.baseline_dict()
    assert first.evaluate(design).design_sha256 == second.evaluate(design).design_sha256
    assert first.evaluate(design).design == second.evaluate(design).design


def test_replay_through_ledger_bills_zero(archive_replay_evaluator, fixed_cruise_task):
    ledger = BudgetLedger(physical_budget=0, run_id="f1-replay-test")
    record = ledger.evaluate(
        archive_replay_evaluator,
        archive_replay_evaluator.design_space.baseline_dict(),
        task=fixed_cruise_task,
    )
    assert record.status == STATUS_PHYSICS_NOT_VALIDATED
    assert ledger.requests == 1
    assert ledger.physical_calls == 0
    assert ledger.summary()["zero_physical_run"] is True
    # 归档路径必须是工作树内相对路径，不能泄漏绝对盘符。
    assert ":" not in record.provenance["archive_path"]
