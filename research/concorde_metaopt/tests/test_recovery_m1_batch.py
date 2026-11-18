"""Offline tests for the M1 batch skeleton (zero physical starts).

The authorisation objects here are STRUCTURAL SOFTWARE FIXTURES. They exist to
exercise validation and accounting; they are not a real A5 verdict or Lead GO,
and no evaluator in this file knows how to reach a solver.
"""
from __future__ import annotations

import json
import os
import shutil
import unittest
from pathlib import Path

from research.concorde_metaopt.dreal001.m1 import task_evaluator as te
from research.concorde_metaopt.dreal001.meta import m1_batch as batch
from research.concorde_metaopt.dreal001.optimizers.ledger import SolverStartLedger

ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "research/concorde_metaopt/dreal001/meta/m1_batch.py"
RAW_SHA = "a" * 64


def _auth(**overrides):
    values = dict(
        run_id="DRECOVER001-M1-SOFTWARE-FIXTURE-20261118T000000Z",
        batch_id="FIXTURE-BATCH-001",
        authorization_id="FIXTURE-AUTH-001",
        approval_id="FIXTURE-APPROVAL-001",
        a5_review_id="A5-FIXTURE-REVIEW-001",
        a5_verdict="R2_FIXED_LOOP_GATE_APPROVED_WITH_DISCLOSURE",
        lead_go_id="LEAD-FIXTURE-GO-001",
        physical_go=True,
        issued_utc="2026-11-18T00:00:00Z",
    )
    values.update(overrides)
    return batch.BatchAuthorization(**values)


def _items(task_count=6):
    items = []
    for task in te.TASK_DEFINITIONS[:task_count]:
        for design in te.REFERENCE_DESIGNS:
            items.append(batch.WorkItem(
                task_id=task.task_id,
                design_id=design.design_id,
                design_hash=design.design_hash,
                design_x12=tuple(float(value) for value in getattr(
                    design, "x12", te.BASELINE_X12)),
                task_fingerprint=te.task_fingerprint(task)))
    return items


class FailingSettleLedger(SolverStartLedger):
    """A ledger whose settle rejects the sample after a reservation exists."""

    def settle(self, reservation, used, *, internal_solver_cases=0):
        raise RuntimeError("fixture accounting rejected settle")


class FailingQuarantineLedger(SolverStartLedger):
    """A ledger whose quarantine also fails, leaving the reservation open."""

    def quarantine(self, reservation, *, reason):
        raise RuntimeError("fixture quarantine rejected")

    def settle(self, reservation, used, *, internal_solver_cases=0):
        raise RuntimeError("fixture settle must not be reached")


def _ledger(auth, *, ledger_cls=SolverStartLedger, **overrides):
    values = dict(run_dir=None, batch_id=auth.batch_id, run_id=auth.run_id,
                  max_starts=auth.max_starts, backend="SOFTWARE_FIXTURE",
                  task_id="M1_FIXTURE", solver_config_sha256="0" * 64)
    values.update(overrides)
    return ledger_cls(**values)


class FakeClock:
    def __init__(self, step=0.005):
        self.now = 0.0
        self.step = float(step)

    def __call__(self):
        value = self.now
        self.now += self.step
        return value


class OkEvaluator:
    def __init__(self, *, internal=7, solver_started=True):
        self.calls = 0
        self.internal = internal
        self.solver_started = solver_started

    def __call__(self, item):
        self.calls += 1
        base = int(item.design_hash[:8], 16) % 500
        return batch.EvaluationSample(
            status="ok", solver_started=self.solver_started,
            internal_solver_cases=self.internal if self.solver_started else 0,
            di_n=5000.0 + float(base), cl=0.17, cdi=0.001,
            raw_path="fixture/raw.json", raw_sha256=RAW_SHA, wall_s=0.01)


class RetryableFailureEvaluator:
    def __init__(self):
        self.calls = 0

    def __call__(self, item):
        self.calls += 1
        return batch.EvaluationSample(
            status="failed", solver_started=True,
            internal_solver_cases=7,
            failure_kind="SOLVER_NONCONVERGED",
            detail="fixture nonconvergence", wall_s=0.02)


class RaisingEvaluator:
    def __init__(self):
        self.calls = 0

    def __call__(self, item):
        self.calls += 1
        raise RuntimeError("fixture evaluator exploded")


class M1BatchSkeletonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = ROOT / ("_tmp_m1_batch_tests-" + str(os.getpid()))
        if cls.scratch.exists():
            shutil.rmtree(cls.scratch)
        cls.scratch.mkdir(parents=True)

    @classmethod
    def tearDownClass(cls):
        if cls.scratch.exists():
            shutil.rmtree(cls.scratch)

    def test_plan_rejects_duplicates_by_default_and_oversize(self):
        auth = _auth()
        items = _items()
        self.assertEqual(len(items), 18)
        with self.assertRaises(batch.BatchContractError):
            batch.build_plan(auth, items + [items[0]])
        with self.assertRaises(batch.BatchContractError):
            batch.build_plan(_auth(max_starts=17), items)
        plan = batch.BatchPlan(authorization=auth, items=tuple(items + [items[0]]),
                               allow_duplicate_work_items=True)
        self.assertEqual(len(plan.items), 19)
        self.assertEqual(plan.plan_sha256, batch.BatchPlan(
            authorization=auth, items=tuple(items + [items[0]]),
            allow_duplicate_work_items=True).plan_sha256)

    def test_authorization_rejects_out_of_range_controls(self):
        cases = (
            dict(max_starts=25),
            dict(max_starts=0),
            dict(solver_timeout_s=601),
            dict(solver_timeout_s=10),
            dict(retries=2),
            dict(parallel=2),
            dict(max_batch_wall_s=10),
            dict(new_r2_gate=False),
            dict(physical_go="yes"),
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(batch.BatchContractError):
                    _auth(**overrides)

    def test_missing_physical_go_blocks_before_any_start(self):
        auth = _auth(physical_go=False)
        ledger = _ledger(auth)
        evaluator = OkEvaluator()
        plan = batch.build_plan(auth, _items())
        with self.assertRaises(batch.BatchNotAuthorized) as context:
            batch.run_batch(plan, evaluator=evaluator, ledger=ledger)
        self.assertIn("PHYSICAL_GO_NOT_ISSUED", str(context.exception))
        self.assertEqual(evaluator.calls, 0)
        self.assertEqual(ledger.starts_used, 0)
        self.assertEqual(ledger.evaluations_requested, 0)

    def test_placeholder_a5_or_lead_go_blocks(self):
        plan = batch.build_plan(_auth(a5_review_id="NOT_PERFORMED"), _items())
        with self.assertRaises(batch.BatchNotAuthorized):
            batch.run_batch(plan, evaluator=OkEvaluator(), ledger=_ledger(plan.authorization))
        plan = batch.build_plan(_auth(lead_go_id="PENDING"), _items())
        with self.assertRaises(batch.BatchNotAuthorized):
            batch.run_batch(plan, evaluator=OkEvaluator(), ledger=_ledger(plan.authorization))
        plan = batch.build_plan(_auth(a5_verdict="NO_PHYSICAL_GO"), _items())
        with self.assertRaises(batch.BatchNotAuthorized):
            batch.run_batch(plan, evaluator=OkEvaluator(), ledger=_ledger(plan.authorization))

    def test_successful_offline_batch_accounts_six_bases(self):
        auth = _auth()
        plan = batch.build_plan(auth, _items())
        ledger = _ledger(auth)
        evaluator = OkEvaluator()
        result = batch.run_batch(plan, evaluator=evaluator, ledger=ledger,
                                 clock=FakeClock())
        self.assertEqual(result["status"], "COMPLETE")
        self.assertIsNone(result["stop_reason"])
        self.assertEqual(result["scope"], batch.SCOPE)
        self.assertEqual(result["evidence_grade"], "SOFTWARE_CONTROL_PATH_ONLY")
        accounting = result["accounting"]
        self.assertEqual(accounting["physical_solver_starts_actual"], 0)
        self.assertEqual(accounting["simulated_solver_starts_actual"], 18)
        self.assertEqual(accounting["internal_solver_cases_actual"], 18 * 7)
        self.assertEqual(accounting["charged_planned_reserved"], 18)
        self.assertEqual(accounting["planned_reserved"], 18)
        self.assertEqual(accounting["design_evaluations"], 18)
        self.assertEqual(accounting["cached_reads"], 0)
        self.assertEqual(accounting["failed_evaluations"], 0)
        self.assertEqual(accounting["retries_used"], 0)
        self.assertEqual(accounting["starts_issued"], 18)
        self.assertEqual(result["controls"]["parallel"], 1)
        self.assertEqual(result["controls"]["solver_timeout_s"], 600)
        self.assertEqual(len(result["items"]), 18)
        for row in result["items"]:
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["objective"], row["di_n"])
            self.assertFalse(row["cached"])
            self.assertEqual(row["internal_solver_cases"], 7)
        batch.verify_result(result)
        self.assertEqual(result["result_sha256"],
                         batch.canonical_sha({key: value for key, value in result.items()
                                              if key != "result_sha256"}))
        self.assertEqual(evaluator.calls, 18)
        self.assertEqual(ledger.register_evaluation is not None, True)

    def test_deterministic_result_for_same_plan_and_clock(self):
        auth = _auth()
        plan = batch.build_plan(auth, _items())
        first = batch.run_batch(plan, evaluator=OkEvaluator(), ledger=_ledger(auth),
                                clock=FakeClock())
        second = batch.run_batch(plan, evaluator=OkEvaluator(), ledger=_ledger(auth),
                                 clock=FakeClock())
        self.assertEqual(first["result_sha256"], second["result_sha256"])
        self.assertEqual(first["accounting"], second["accounting"])
        changed = _items()
        changed[0] = batch.WorkItem(task_id=changed[0].task_id,
                                    design_id=changed[0].design_id,
                                    design_hash="0" * 16,
                                    design_x12=changed[0].design_x12,
                                    task_fingerprint=changed[0].task_fingerprint)
        self.assertNotEqual(batch.build_plan(auth, changed).plan_sha256,
                            plan.plan_sha256)

    def test_failed_sample_carries_null_objective(self):
        auth = _auth(retries=0)
        plan = batch.build_plan(auth, _items(task_count=1))
        ledger = _ledger(auth)
        result = batch.run_batch(plan, evaluator=RetryableFailureEvaluator(),
                                 ledger=ledger, clock=FakeClock())
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["accounting"]["failed_evaluations"], 3)
        self.assertEqual(result["accounting"]["design_evaluations"], 3)
        self.assertEqual(result["accounting"]["starts_issued"], 3)
        self.assertEqual(result["accounting"]["physical_solver_starts_actual"], 0)
        for row in result["items"]:
            self.assertEqual(row["status"], "failed")
            self.assertIsNone(row["objective"])
            self.assertIsNone(row["di_n"])
            self.assertIsNone(row["cl"])
            self.assertIsNone(row["cdi"])
            self.assertEqual(row["failure_kind"], "SOLVER_NONCONVERGED")
        self.assertEqual(ledger.internal_solver_cases, 3 * 7)

    def test_retry_stops_after_one_attempt(self):
        auth = _auth(retries=1)
        items = _items(task_count=1)[:1]
        plan = batch.build_plan(auth, items)
        evaluator = RetryableFailureEvaluator()
        result = batch.run_batch(plan, evaluator=evaluator, ledger=_ledger(auth),
                                 clock=FakeClock())
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["accounting"]["retries_used"], 1)
        self.assertEqual(result["accounting"]["starts_issued"], 2)
        self.assertEqual([row["attempt"] for row in result["items"]], [0, 1])
        self.assertEqual(evaluator.calls, 2)

    def test_infra_error_stops_batch_and_quarantines(self):
        auth = _auth()
        plan = batch.build_plan(auth, _items())
        ledger = _ledger(auth)
        evaluator = RaisingEvaluator()
        result = batch.run_batch(plan, evaluator=evaluator, ledger=ledger,
                                 clock=FakeClock())
        self.assertEqual(result["status"], "STOPPED_INFRA_ERROR")
        self.assertIn("RuntimeError", result["stop_reason"])
        self.assertEqual(len(result["items"]), 1)
        self.assertIsNone(result["items"][0]["objective"])
        self.assertEqual(result["items"][0]["failure_kind"], "INFRA_ERROR")
        self.assertEqual(evaluator.calls, 1)
        self.assertEqual(ledger.starts_used, 0)
        self.assertEqual(len(ledger._unresolved_reservations), 1)

    def test_infra_error_with_failing_stop_is_accounting_violation(self):
        auth = _auth()
        plan = batch.build_plan(auth, _items())
        ledger = _ledger(auth, ledger_cls=FailingQuarantineLedger)
        result = batch.run_batch(plan, evaluator=RaisingEvaluator(), ledger=ledger,
                                 clock=FakeClock())
        self.assertEqual(result["status"], "STOPPED_ACCOUNTING_VIOLATION")
        self.assertTrue(ledger._unresolved_reservations or ledger.starts_reserved)
        self.assertEqual(len(result["items"]), 1)
        row = result["items"][0]
        self.assertEqual(row["failure_kind"], "ACCOUNTING_VIOLATION")
        self.assertIn("fixture evaluator exploded", row["detail"])
        self.assertIn("fixture quarantine rejected", row["detail"])
        self.assertEqual(result["accounting"]["physical_solver_starts_actual"], 0)
        self.assertEqual(result["accounting"]["starts_issued"], 0)
        self.assertEqual(ledger.starts_used, 0)
        self.assertEqual(ledger.starts_reserved, 1)
        self.assertFalse(ledger.summary()["accounting_resolved"])

    def test_accounting_rejection_quarantines_open_reservation(self):
        auth = _auth()
        plan = batch.build_plan(auth, _items())
        ledger = _ledger(auth, ledger_cls=FailingSettleLedger)
        result = batch.run_batch(plan, evaluator=OkEvaluator(), ledger=ledger,
                                 clock=FakeClock())
        self.assertEqual(result["status"], "STOPPED_ACCOUNTING_VIOLATION")
        self.assertIn("RuntimeError", result["stop_reason"])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["failure_kind"],
                         "ACCOUNTING_VIOLATION")
        self.assertEqual(result["accounting"]["physical_solver_starts_actual"],
                         0)
        self.assertEqual(result["accounting"]["starts_issued"], 0)
        self.assertEqual(ledger.starts_used, 0)
        self.assertEqual(ledger.starts_reserved, 1)
        summary = ledger.summary()
        self.assertFalse(summary["accounting_resolved"])
        self.assertEqual(len(summary["unresolved_reservations"]), 1)

    def test_wall_clock_stop(self):
        auth = _auth(max_batch_wall_s=60)
        plan = batch.build_plan(auth, _items())
        clock = FakeClock(step=5.0)
        result = batch.run_batch(plan, evaluator=OkEvaluator(), ledger=_ledger(auth),
                                 clock=clock)
        self.assertEqual(result["status"], "STOPPED_WALL_CLOCK")
        self.assertLess(result["accounting"]["starts_issued"], 18)

    def test_budget_exhaustion_stops_without_overrun(self):
        auth = _auth(max_starts=2, retries=1)
        items = _items(task_count=1)[:2]
        plan = batch.build_plan(auth, items)
        result = batch.run_batch(plan, evaluator=RetryableFailureEvaluator(),
                                 ledger=_ledger(auth), clock=FakeClock())
        self.assertEqual(result["status"], "STOPPED_BUDGET_EXHAUSTED")
        self.assertEqual(result["accounting"]["starts_issued"], 2)
        self.assertEqual(result["accounting"]["charged_planned_reserved"], 2)
        self.assertEqual(result["accounting"]["physical_solver_starts_actual"], 0)

    def test_ledger_budget_mismatch_rejected(self):
        auth = _auth()
        plan = batch.build_plan(auth, _items())
        ledger = _ledger(auth, max_starts=10)
        with self.assertRaises(batch.BatchContractError):
            batch.run_batch(plan, evaluator=OkEvaluator(), ledger=ledger)

    def test_duplicate_items_become_cached_reads(self):
        auth = _auth(max_starts=2)
        base = _items(task_count=1)[:1]
        plan = batch.BatchPlan(authorization=auth, items=tuple(base + base),
                               allow_duplicate_work_items=True)
        ledger = _ledger(auth)
        result = batch.run_batch(plan, evaluator=OkEvaluator(), ledger=ledger,
                                 clock=FakeClock())
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["accounting"]["design_evaluations"], 1)
        self.assertEqual(result["accounting"]["cached_reads"], 1)
        self.assertEqual(result["accounting"]["starts_issued"], 1)
        self.assertEqual(ledger.evaluations_requested, 2)
        self.assertTrue(result["items"][1]["cached"])
        self.assertEqual(result["items"][0]["objective"],
                         result["items"][1]["objective"])

    def test_result_roundtrip_and_tamper_rejected(self):
        auth = _auth()
        plan = batch.build_plan(auth, _items(task_count=1))
        result = batch.run_batch(plan, evaluator=OkEvaluator(), ledger=_ledger(auth),
                                 clock=FakeClock())
        target = self.scratch / "batch_result.json"
        info = batch.write_result(result, target)
        self.assertEqual(info["bytes"], target.stat().st_size)
        loaded = batch.load_result(target)
        self.assertEqual(loaded["result_sha256"], result["result_sha256"])
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["accounting"]["physical_solver_starts_actual"] = 1
        target.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(batch.BatchContractError):
            batch.verify_result(payload)
        payload = json.loads(json.dumps(result))
        payload["items"][0]["objective"] = 1.0
        with self.assertRaises(batch.BatchContractError):
            batch.verify_result(payload)

    def test_module_has_no_process_launcher(self):
        source = MODULE_PATH.read_text(encoding="utf-8").lower()
        for token in ("subprocess", "popen", "os.system", "vspaero", "openvsp",
                      "os.fork", "spawnv"):
            self.assertNotIn(token, source)
        self.assertEqual(batch.module_source_sha256(),
                         __import__("hashlib").sha256(
                             MODULE_PATH.read_bytes()).hexdigest())

    def test_real_task_family_wiring(self):
        items = _items()
        self.assertEqual(len(items), 18)
        self.assertEqual({item.task_id for item in items},
                         {task.task_id for task in te.TASK_DEFINITIONS})
        for item in items:
            self.assertEqual(len(item.task_fingerprint), 64)
            self.assertEqual(item.task_fingerprint,
                             item.task_fingerprint.lower())
        plan = batch.build_plan(_auth(), items)
        self.assertEqual(plan.authorization.max_starts, 24)
        self.assertGreaterEqual(plan.authorization.max_starts, len(plan.items))

    def test_spawn_guard_sees_no_attempts(self):
        guard = te.SpawnGuard().install()
        try:
            auth = _auth()
            plan = batch.build_plan(auth, _items())
            result = batch.run_batch(plan, evaluator=OkEvaluator(),
                                     ledger=_ledger(auth), clock=FakeClock())
        finally:
            guard.uninstall()
        self.assertEqual(guard.attempts, [])
        self.assertEqual(result["accounting"]["physical_solver_starts_actual"], 0)

    def test_sample_contract_rejects_invented_values(self):
        with self.assertRaises(batch.BatchContractError):
            batch.EvaluationSample(status="failed", solver_started=True,
                                   failure_kind=None)
        with self.assertRaises(batch.BatchContractError):
            batch.EvaluationSample(status="failed", solver_started=True,
                                   failure_kind="SOLVER_FAILED", di_n=1.0)
        with self.assertRaises(batch.BatchContractError):
            batch.EvaluationSample(status="failed", solver_started=False,
                                   internal_solver_cases=7,
                                   failure_kind="SOLVER_FAILED")
        with self.assertRaises(batch.BatchContractError):
            batch.EvaluationSample(status="ok", solver_started=False,
                                   di_n=float("nan"))
        ok = batch.EvaluationSample(status="ok", solver_started=True,
                                    internal_solver_cases=7, di_n=1.0,
                                    cl=0.1, cdi=0.001)
        self.assertEqual(ok.objective, 1.0)


if __name__ == "__main__":
    unittest.main()
