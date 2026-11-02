"""Physical-call accounting contract tests (no RCAIDE Mission, no SU2).

The management review on 2026-10-30 found that the low-fidelity backend started
each record at physical_call_count=1 even when the mission solver was never
invoked. These tests pin the repaired semantics: a rejected request, a geometry
rejection and a mission-build failure cost 0; a real solver attempt costs 1 even
when it fails; cache hits add no solve. The ledger must expose enough accounting
data that JSONL rows and the run summary agree.
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from research.concorde_metaopt.aircraft.concorde_adapter import AdapterError
from research.concorde_metaopt.aircraft.design_space import load_design_space
from research.concorde_metaopt.aircraft.geometry_model import GeometryError
from research.concorde_metaopt.evaluation.contract import (
    CALL_ACCOUNTING_FLAGS,
    CONSTRAINT_NAMES,
    STATUS_VALID,
    new_call_accounting,
    validate_call_accounting,
)
from research.concorde_metaopt.evaluation.ledger import BudgetExceeded, EvaluationLedger
from research.concorde_metaopt.evaluation.low_fidelity import SingleCruiseBackend
from research.concorde_metaopt.evaluation.mission import MissionBuildError, ObservationError
from research.concorde_metaopt.tasks.task_spec import load_task_spec

LOW_FIDELITY = "research.concorde_metaopt.evaluation.low_fidelity"


class MoveOnlyMission:
    """Minimal mission object: the solver is 'entered' but does nothing."""

    def evaluate(self) -> None:
        return None


class FailingMission:
    def evaluate(self) -> None:
        raise RuntimeError("synthetic solver failure")


class CallAccountingContractTests(unittest.TestCase):
    """The validator must reject ambiguous or impossible accounting blocks."""

    def _valid(self):
        block = new_call_accounting()
        block["mission_solve_attempted"] = 1
        block["mission_solve_completed"] = 1
        block["billable_physical_calls"] = 1
        return block

    def test_valid_block_is_normalized(self):
        block = self._valid()
        normalized, error = validate_call_accounting(block)
        self.assertIsNone(error)
        self.assertEqual(normalized["billable_physical_calls"], 1)
        self.assertEqual(set(CALL_ACCOUNTING_FLAGS) - set(normalized), set())

    def test_zero_outcomes_are_rejected(self):
        block = new_call_accounting()
        normalized, error = validate_call_accounting(block)
        self.assertIsNone(normalized)
        self.assertIn("exactly one outcome", error)

    def test_two_outcomes_are_rejected(self):
        block = self._valid()
        block["geometry_rejected"] = 1
        normalized, error = validate_call_accounting(block)
        self.assertIsNone(normalized)
        self.assertIn("exactly one outcome", error)

    def test_billable_call_without_attempt_is_rejected(self):
        block = new_call_accounting()
        block["request_rejected"] = 1
        block["billable_physical_calls"] = 1
        normalized, error = validate_call_accounting(block)
        self.assertIsNone(normalized)
        self.assertIn("billable_physical_calls", error)

    def test_backend_cache_hit_is_rejected(self):
        block = self._valid()
        block["cache_hit"] = 1
        normalized, error = validate_call_accounting(block)
        self.assertIsNone(normalized)
        self.assertIn("cache hits", error)


class LowFidelityCallAccountingTests(unittest.TestCase):
    """Branch-level accounting for the real single-cruise backend (no solve)."""

    @classmethod
    def setUpClass(cls):
        cls.space = load_design_space()
        cls.task = load_task_spec()
        cls.backend = SingleCruiseBackend(cls.space, cls.task)
        cls.baseline = dict(cls.space.baseline_dict())

    def _evaluate(self, design, patches=()):
        stack = []
        for name, side_effect in patches:
            patcher = mock.patch(name, side_effect=side_effect)
            stack.append(patcher)
            patcher.start()
        try:
            return self.backend.evaluate(design)
        finally:
            for patcher in reversed(stack):
                patcher.stop()

    def test_parameter_error_is_not_billed(self):
        design = dict(self.baseline)
        design.pop("tip_twist")
        record = self.backend.evaluate(design)
        acct = record["call_accounting"]
        self.assertEqual(record["status"], "GEOMETRY_INVALID")
        self.assertEqual(record["physical_call_count"], 0)
        self.assertEqual(acct["request_rejected"], 1)
        self.assertEqual(acct["failure_stage"], "design_vector")

    def test_out_of_bounds_request_is_not_billed(self):
        design = dict(self.baseline)
        design["wing_area"] = 9999.0
        record = self.backend.evaluate(design)
        acct = record["call_accounting"]
        self.assertEqual(record["status"], "GEOMETRY_INVALID")
        self.assertEqual(record["physical_call_count"], 0)
        self.assertEqual(acct["request_rejected"], 1)
        self.assertEqual(acct["failure_stage"], "design_space")

    def test_geometry_rejection_is_not_billed(self):
        record = self._evaluate(
            self.baseline,
            [(LOW_FIDELITY + ".build_geometry", GeometryError("synthetic degenerate geometry"))],
        )
        acct = record["call_accounting"]
        self.assertEqual(record["status"], "GEOMETRY_INVALID")
        self.assertEqual(record["physical_call_count"], 0)
        self.assertEqual(acct["geometry_rejected"], 1)
        self.assertEqual(acct["failure_stage"], "geometry_model")

    def test_analysis_build_failure_is_not_billed(self):
        record = self._evaluate(
            self.baseline,
            [(LOW_FIDELITY + ".build_vehicle", AdapterError("synthetic adapter failure"))],
        )
        acct = record["call_accounting"]
        self.assertEqual(record["status"], "MISSION_BUILD_FAILED")
        self.assertEqual(record["physical_call_count"], 0)
        self.assertEqual(acct["mission_build_failed"], 1)
        self.assertEqual(acct["failure_stage"], "analysis_build")

    def test_mission_build_failure_is_not_billed(self):
        record = self._evaluate(
            self.baseline,
            [
                (
                    LOW_FIDELITY + ".build_single_cruise_mission",
                    MissionBuildError("synthetic mission build failure"),
                )
            ],
        )
        acct = record["call_accounting"]
        self.assertEqual(record["status"], "MISSION_BUILD_FAILED")
        self.assertEqual(record["physical_call_count"], 0)
        self.assertEqual(acct["mission_build_failed"], 1)
        self.assertEqual(acct["failure_stage"], "mission_build")

    def test_failed_solver_attempt_is_billed_once(self):
        record = self._evaluate(
            self.baseline,
            [(LOW_FIDELITY + ".build_single_cruise_mission", lambda *a, **k: (FailingMission(), object()))],
        )
        acct = record["call_accounting"]
        self.assertEqual(record["status"], "MISSION_FAILED")
        self.assertEqual(record["physical_call_count"], 1)
        self.assertEqual(acct["mission_solve_attempted"], 1)
        self.assertEqual(acct["mission_solve_completed"], 0)
        self.assertEqual(acct["billable_physical_calls"], 1)

    def test_post_solve_failure_still_bills_the_attempt(self):
        record = self._evaluate(
            self.baseline,
            [
                (
                    LOW_FIDELITY + ".build_single_cruise_mission",
                    lambda *a, **k: (MoveOnlyMission(), object()),
                ),
                (
                    LOW_FIDELITY + ".extract_observations",
                    ObservationError("synthetic observation failure"),
                ),
            ],
        )
        acct = record["call_accounting"]
        self.assertEqual(record["status"], "INVALID_OR_MISSING_RESPONSE")
        self.assertEqual(record["physical_call_count"], 1)
        self.assertEqual(acct["mission_solve_attempted"], 1)
        self.assertEqual(acct["mission_solve_completed"], 1)
        self.assertEqual(acct["billable_physical_calls"], 1)
        self.assertEqual(acct["failure_stage"], "observation")


class TaskMismatchAccountingTests(unittest.TestCase):
    def test_foreign_task_request_is_not_billed(self):
        space = load_design_space()
        task = load_task_spec()
        backend = SingleCruiseBackend(space, task)
        other = dataclasses.replace(task, task_id=task.task_id + "-other")
        self.assertNotEqual(other.fingerprint(), task.fingerprint())
        with tempfile.TemporaryDirectory() as tmp:
            ledger = EvaluationLedger(budget=1, run_dir=Path(tmp))
            row = ledger.evaluate(backend, dict(space.baseline_dict()), other)
            summary = ledger.summary()
        self.assertEqual(row["status"], "BACKEND_ERROR")
        self.assertEqual(row["physical_call_count"], 0)
        self.assertEqual(summary["total_true_evaluations"], 0)
        self.assertEqual(summary["request_rejected_requests"], 1)
        self.assertEqual(summary["accounting_errors"], 0)
        self.assertEqual(summary["budget_remaining"], 1)


class ExplicitAccountingBackend:
    """Offline backend returning an explicit valid accounting block."""

    fidelity = "single_cruise"

    def __init__(self, fail_after_bill: bool = False) -> None:
        self.fail_after_bill = fail_after_bill
        self.calls = 0

    def evaluate(self, design, task=None, fidelity=None, purpose="search"):
        self.calls += 1
        acct = new_call_accounting()
        acct["mission_solve_attempted"] = 1
        acct["mission_solve_completed"] = 1
        acct["billable_physical_calls"] = 1
        record = {
            "status": STATUS_VALID,
            "objective": 34000.0 + float(design["wing_area"]),
            "constraints": {name: 0.0 for name in CONSTRAINT_NAMES},
            "feasible": True,
            "fidelity": fidelity or self.fidelity,
            "diagnostics": [],
            "physical_call_count": 1,
            "call_accounting": acct,
        }
        if self.fail_after_bill:
            self.last_physical_call_count = 1
            self.last_call_accounting = dict(acct)
            raise RuntimeError("synthetic post-billing backend failure")
        return record


class LedgerCallAccountingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name)
        self.space = load_design_space()
        self.task = load_task_spec()
        self.baseline = dict(self.space.baseline_dict())

    def tearDown(self):
        self._tmp.cleanup()

    def _ledger(self, budget):
        return EvaluationLedger(budget=budget, run_dir=self.run_dir)

    def _rows_from_jsonl(self):
        lines = (self.run_dir / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line]

    def test_cache_hit_accounting_and_jsonl_summary_consistency(self):
        ledger = self._ledger(2)
        backend = ExplicitAccountingBackend()
        first = ledger.evaluate(backend, self.baseline, self.task)
        second = ledger.evaluate(backend, self.baseline, self.task)
        summary = ledger.summary()
        self.assertEqual(first["physical_call_count"], 1)
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["request_count"], 1)
        self.assertEqual(second["physical_call_count"], 0)
        self.assertEqual(second["call_accounting"]["cache_hit"], 1)
        self.assertEqual(summary["total_true_evaluations"], 1)
        self.assertEqual(summary["total_requests"], 2)
        self.assertEqual(summary["cache_hits"], 1)
        self.assertEqual(summary["mission_solve_attempts"], 1)
        self.assertEqual(summary["mission_solve_successes"], 1)
        self.assertTrue(summary["call_accounting_consistent"])
        rows = self._rows_from_jsonl()
        self.assertEqual(len(rows), summary["total_requests"])
        self.assertEqual(sum(row["physical_call_count"] for row in rows), summary["total_true_evaluations"])

    def test_budget_exhaustion_writes_no_extra_row(self):
        ledger = self._ledger(1)
        backend = ExplicitAccountingBackend()
        ledger.evaluate(backend, self.baseline, self.task)
        other = dict(self.baseline)
        other["wing_area"] = 359.0
        with self.assertRaises(BudgetExceeded):
            ledger.evaluate(backend, other, self.task)
        summary = ledger.summary()
        self.assertEqual(summary["total_requests"], 1)
        self.assertEqual(summary["total_true_evaluations"], 1)
        self.assertEqual(summary["budget_remaining"], 0)
        self.assertEqual(len(self._rows_from_jsonl()), 1)

    def test_exception_after_billing_is_recorded_and_consistent(self):
        ledger = self._ledger(1)
        backend = ExplicitAccountingBackend(fail_after_bill=True)
        row = ledger.evaluate(backend, self.baseline, self.task)
        summary = ledger.summary()
        self.assertEqual(row["status"], "BACKEND_ERROR")
        self.assertEqual(row["physical_call_count"], 1)
        self.assertEqual(summary["mission_solve_attempts"], 1)
        self.assertEqual(summary["accounting_errors"], 0)
        self.assertTrue(summary["call_accounting_consistent"])
        rows = self._rows_from_jsonl()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["physical_call_count"], 1)

    def test_rejected_requests_are_zero_billed_and_traceable(self):
        backend = SingleCruiseBackend(self.space, self.task)
        ledger = self._ledger(2)
        missing = dict(self.baseline)
        missing.pop("tip_twist")
        out_of_bounds = dict(self.baseline)
        out_of_bounds["wing_area"] = 9999.0
        first = ledger.evaluate(backend, missing, self.task)
        second = ledger.evaluate(backend, out_of_bounds, self.task)
        summary = ledger.summary()
        for row in (first, second):
            self.assertEqual(row["status"], "GEOMETRY_INVALID")
            self.assertEqual(row["physical_call_count"], 0)
            self.assertEqual(row["call_accounting"]["request"], 1)
        self.assertEqual(summary["total_requests"], 2)
        self.assertEqual(summary["total_true_evaluations"], 0)
        self.assertEqual(summary["request_rejected_requests"], 2)
        self.assertEqual(summary["accounting_errors"], 0)
        self.assertFalse(summary["budget_exceeded"])
        self.assertEqual(summary["budget_remaining"], 2)
        rows = self._rows_from_jsonl()
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row["physical_call_count"] for row in rows), 0)
        detail_lines = (self.run_dir / "evaluations_detail.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len([line for line in detail_lines if line]), 2)
        detail = json.loads([line for line in detail_lines if line][0])
        self.assertIn("call_accounting", detail)


if __name__ == "__main__":
    unittest.main()
