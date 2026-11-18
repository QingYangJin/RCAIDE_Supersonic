"""In-memory accounting only; synthetic reservations never represent physical runs."""
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from research.concorde_metaopt.dreal001.optimizers.evaluators import BaseLiftMatchEvaluator, ProbeResult
import unittest
from research.concorde_metaopt.dreal001.optimizers.ledger import (
    SolverStartLedger, Reservation, AccountingViolation, SolverBudgetExceeded)


def ledger(cap=4):
    return SolverStartLedger(None, batch_id="fixture", run_id="fixture", max_starts=cap,
                             backend="MOCK", write_attempts=False)


class LedgerTests(unittest.TestCase):
    def test_owned_reservation_charges_simulated_not_physical(self):
        book = ledger()
        token = book.reserve(2)
        book.settle(token, 2, internal_solver_cases=14)
        self.assertEqual(book.simulated_solver_starts, 2)
        self.assertEqual(book.physical_solver_starts, 0)
        self.assertEqual(book.internal_solver_cases, 14)
        self.assertEqual(book.starts_reserved, 0)
        book.assert_conserved()

    def test_forged_same_id_rejected_without_mutation(self):
        book = ledger()
        owned = book.reserve(1)
        forged = Reservation(owned.reservation_id, 100)
        for action in (lambda: book.settle(forged, 80), lambda: book.cancel(forged)):
            with self.assertRaises(AccountingViolation):
                action()
        self.assertFalse(owned.settled)
        self.assertEqual(book.starts_used, 0)

    def test_foreign_ledger_same_sequence_rejected(self):
        left, right = ledger(), ledger()
        a, b = left.reserve(), right.reserve()
        self.assertEqual(a.reservation_id, b.reservation_id)
        with self.assertRaises(AccountingViolation):
            left.settle(b, 1)
        with self.assertRaises(AccountingViolation):
            left.cancel(b)

    def test_open_reservation_is_not_accounting_resolved(self):
        book = ledger()
        token = book.reserve(2)
        report = book.summary()
        self.assertFalse(report["accounting_resolved"])
        self.assertEqual(report["starts_reserved"], 2)
        with self.assertRaisesRegex(AccountingViolation, "open solver-start reservation"):
            book.assert_conserved()
        book.settle(token, 2)
        self.assertTrue(book.summary()["accounting_resolved"])
        book.assert_conserved()

    def test_outstanding_reservations_prevent_oversubscription(self):
        book = ledger(3)
        a, b = book.reserve(2), book.reserve(9)
        self.assertEqual(b.n_starts, 1)
        with self.assertRaises(SolverBudgetExceeded):
            book.reserve()
        book.settle(a, 1)
        self.assertEqual(book.reserve().n_starts, 1)

    def test_overuse_does_not_partially_settle(self):
        book = ledger()
        token = book.reserve(1)
        with self.assertRaises(AccountingViolation):
            book.settle(token, 2, internal_solver_cases=14)
        self.assertFalse(token.settled)
        self.assertEqual(book.internal_solver_cases, 0)
        book.settle(token, 1, internal_solver_cases=7)

    def test_bad_usage_and_cases_leave_reservation_open(self):
        for used, cases in ((-1, 0), (True, 0), (1.5, 0), (1, -7), (1, True), (1, 1.5), (0, 7)):
            book = ledger()
            token = book.reserve()
            with self.assertRaises(AccountingViolation):
                book.settle(token, used, internal_solver_cases=cases)
            self.assertFalse(token.settled)
            self.assertEqual(book.starts_used, 0)

    def test_double_settlement_rejected(self):
        book = ledger()
        token = book.reserve()
        book.settle(token, 1)
        with self.assertRaises(AccountingViolation):
            book.settle(token, 1)
        self.assertEqual(book.starts_used, 1)

    def test_cancel_charged_reservation_cannot_erase_cost(self):
        book = ledger()
        token = book.reserve()
        book.settle(token, 1)
        with self.assertRaises(AccountingViolation):
            book.cancel(token)
        self.assertEqual(book.starts_used, 1)

    def test_cancel_unstarted_idempotent_releases_capacity(self):
        book = ledger(1)
        token = book.reserve()
        book.cancel(token)
        book.cancel(token)
        self.assertEqual(book.starts_reserved, 0)
        self.assertEqual(book.reserve().n_starts, 1)
        with self.assertRaises(AccountingViolation):
            book.settle(token, 0)

    def test_reservation_fields_cannot_be_reassigned(self):
        token = ledger().reserve()
        for key in ("n_starts", "reservation_id", "used", "settled"):
            with self.assertRaises(FrozenInstanceError):
                setattr(token, key, 999)

    def test_strict_integer_request_and_cap(self):
        for cap in (True, 1.5, "2", -1):
            with self.assertRaises(ValueError):
                ledger(cap)
        book = ledger()
        for request in (True, 1.5, "2", -1, 0):
            with self.assertRaises(ValueError):
                book.reserve(request)
        with self.assertRaises(SolverBudgetExceeded):
            ledger(0).reserve()

    def test_evaluation_conservation_and_no_synthetic_physics(self):
        book = ledger()
        book.register_evaluation(cache_hit=False, started=True, valid=False)
        book.register_evaluation(cache_hit=True, started=False, valid=False)
        book.assert_conserved()
        report = book.summary()
        self.assertEqual(report["evaluations_requested"], 2)
        self.assertEqual(report["physical_solver_starts"], 0)
        self.assertEqual(report["physical_solver_starts_from_attempts"], 0)


class UncertainProbeTests(unittest.TestCase):
    def runner(self, *, sweep, response=None, error=None, requires=True):
        def callback(*args, **kwargs):
            if error is not None:
                raise error
            return response
        return SimpleNamespace(ledger=ledger(8), supports_alpha_sweep=sweep,
            _reservation_size=lambda: 1 if requires else 0,
            _probe_single=callback, _probe_batch=callback)

    def test_unknown_callback_outcome_blocks_new_starts_and_conservation(self):
        for sweep in (True, False):
            with self.subTest(sweep=sweep):
                runner = self.runner(sweep=sweep, error=RuntimeError("fixture uncertain outcome"))
                with self.assertRaisesRegex(RuntimeError, "fixture uncertain outcome"):
                    BaseLiftMatchEvaluator._collect(runner, [0.] * 12, [0.], "fixture", phase="test")
                self.assertEqual(runner.ledger.starts_used, 0)
                self.assertEqual(runner.ledger.starts_reserved, 1)
                self.assertFalse(runner.ledger.summary()["accounting_resolved"])
                with self.assertRaises(AccountingViolation):
                    runner.ledger.reserve()
                with self.assertRaises(AccountingViolation):
                    runner.ledger.assert_conserved()

    def test_interruption_is_quarantined_and_original_exception_preserved(self):
        for error in (KeyboardInterrupt(), SystemExit(7)):
            runner = self.runner(sweep=True, error=error)
            with self.assertRaises(type(error)):
                BaseLiftMatchEvaluator._collect(runner, [], [0.], "fixture", phase="test")
            self.assertFalse(runner.ledger.summary()["accounting_resolved"])

    def test_invalid_returned_cost_is_also_quarantined(self):
        for sweep in (True, False):
            runner = self.runner(sweep=sweep, response=ProbeResult([], 2, "FAIL"))
            with self.assertRaises(AccountingViolation):
                BaseLiftMatchEvaluator._collect(runner, [], [0.], "fixture", phase="test")
            with self.assertRaises(AccountingViolation):
                runner.ledger.reserve()

    def test_success_or_known_zero_can_settle_normally(self):
        for sweep in (True, False):
            for starts in (0, 1):
                runner = self.runner(sweep=sweep, response=ProbeResult([], starts, "FAIL"))
                BaseLiftMatchEvaluator._collect(runner, [], [0.], "fixture", phase="test")
                self.assertEqual(runner.ledger.starts_used, starts)
                self.assertEqual(runner.ledger.starts_reserved, 0)
                runner.ledger.assert_conserved()

    def test_replay_callback_exception_has_no_reservation(self):
        runner = self.runner(sweep=True, requires=False, error=ValueError("fixture replay"))
        with self.assertRaises(ValueError):
            BaseLiftMatchEvaluator._collect(runner, [], [0.], "fixture", phase="test")
        self.assertTrue(runner.ledger.summary()["accounting_resolved"])
        self.assertEqual(runner.ledger.starts_reserved, 0)

    def test_unresolved_token_cannot_be_canceled_or_settled(self):
        book = ledger()
        token = book.reserve()
        book.quarantine(token, reason="fixture unknown spawn state")
        for operation in (lambda: book.cancel(token), lambda: book.settle(token, 0)):
            with self.assertRaises(AccountingViolation):
                operation()
        self.assertEqual(book.starts_reserved, 1)
        self.assertEqual(book.physical_solver_starts, 0)

    def test_quarantine_requires_owned_open_token_and_reason(self):
        book = ledger()
        token = book.reserve()
        for other, reason in ((Reservation(token.reservation_id, 1), "fixture"), (token, "")):
            with self.assertRaises(AccountingViolation):
                book.quarantine(other, reason=reason)
        book.cancel(token)
        with self.assertRaises(AccountingViolation):
            book.quarantine(token, reason="fixture")


if __name__ == "__main__":
    unittest.main()
