"""Recovery feedback wiring only: synthetic responses, zero solver execution.

A spy acquisition backend tests callback causality, not BO effectiveness. The
regenerated executable GP backend is tested separately; a true-physics feedback
trajectory still requires the issue gates.
"""
from types import SimpleNamespace
import unittest
from unittest import mock
import numpy as np
from research.concorde_metaopt.dreal001.optimizers import arms


class FixtureHarness:
    def __init__(self, values, cap=4):
        self.values = values
        self.cap = cap
        self.evaluator = SimpleNamespace(ledger=SimpleNamespace(starts_used=0))
        self.budget_exhausted = False
        self.events = []

    def _guard(self):
        if self.evaluator.ledger.starts_used >= self.cap:
            raise arms.SolverBudgetExceeded("software fixture cap")

    def evaluate(self, vector, *, phase):
        self._guard()
        index = self.evaluator.ledger.starts_used
        self.evaluator.ledger.starts_used += 1
        value = self.values[index] if index < len(self.values) else 10.0
        result = dict(objective=value, valid=value is not None, feasible=value is not None)
        self.events.append((np.array(vector, copy=True), result, phase))
        return result


class SpyBO:
    instances = []
    def __init__(self, lower, upper, *, seed):
        self.rows = []
        self.ask_states = []
        self.instances.append(self)

    def tell(self, vector, result):
        self.rows.append((np.array(vector, copy=True), result))

    def ask(self):
        self.ask_states.append(len(self.rows))
        usable = [row for row in self.rows if row[1]["valid"]]
        if usable:
            best = min(usable, key=lambda row: row[1]["objective"])[0]
            vector = np.clip(best + 0.01 * len(self.rows), 0, 1)
        else:
            vector = np.full(12, 0.5)
        return dict(design_vector=vector)


def initials(*args, **kwargs):
    return np.array([np.full(12, 0.2), np.full(12, 0.8)])


class RecoveryFeedbackTests(unittest.TestCase):
    def setUp(self):
        SpyBO.instances.clear()
        self.spec = arms.ArmSpec("BO", budget_starts=4, initial_designs=2)

    def run_fixture(self, values, cap=4, backend=SpyBO):
        harness = FixtureHarness(values, cap)
        with mock.patch.object(arms, "ConstrainedBayesianOptimizer", backend), \
             mock.patch.object(arms, "generate_initial_designs", initials):
            info = arms._run_bo(self.spec, harness, None)
        return harness, SpyBO.instances[-1], info

    def test_all_initial_and_search_responses_are_told(self):
        harness, optimizer, info = self.run_fixture([4.0, 1.0])
        self.assertEqual(optimizer.ask_states, [2, 3])
        self.assertEqual(len(optimizer.rows), 4)
        self.assertEqual(info["initial_evaluated"], 2)
        self.assertEqual(info["acquisitions"], 2)
        for (_, returned, _), (_, told) in zip(harness.events, optimizer.rows):
            self.assertIs(returned, told)

    def test_swapping_returned_values_changes_next_proposal(self):
        left, _, _ = self.run_fixture([1.0, 4.0])
        right, _, _ = self.run_fixture([4.0, 1.0])
        np.testing.assert_array_equal(left.events[0][0], right.events[0][0])
        np.testing.assert_array_equal(left.events[1][0], right.events[1][0])
        self.assertFalse(np.array_equal(left.events[2][0], right.events[2][0]))

    def test_failed_evaluation_keeps_null_not_penalty_label(self):
        harness, optimizer, _ = self.run_fixture([None, 2.0])
        self.assertIsNone(optimizer.rows[0][1]["objective"])
        self.assertFalse(optimizer.rows[0][1]["valid"])
        self.assertIs(harness.events[0][1], optimizer.rows[0][1])

    def test_budget_during_initialization_reports_actual_count(self):
        harness, optimizer, info = self.run_fixture([1.0], cap=1)
        self.assertEqual(info["initial_evaluated"], 1)
        self.assertEqual(len(optimizer.rows), 1)
        self.assertFalse(optimizer.ask_states)
        self.assertTrue(harness.budget_exhausted)

    def test_ask_failure_is_not_silently_completed(self):
        class Broken(SpyBO):
            def ask(self):
                raise RuntimeError("fixture acquisition failure")
        with self.assertRaisesRegex(RuntimeError, "fixture acquisition failure"):
            self.run_fixture([1.0, 2.0], backend=Broken)

    def test_search_tell_failure_is_not_silently_completed(self):
        class Broken(SpyBO):
            def tell(self, vector, result):
                if len(self.rows) >= 2:
                    raise ValueError("fixture tell failure")
                super().tell(vector, result)
        with self.assertRaisesRegex(ValueError, "fixture tell failure"):
            self.run_fixture([1.0, 2.0], backend=Broken)

    def test_run_arm_records_propagated_failure(self):
        harness = SimpleNamespace(budget_exhausted=False)
        harness.result = lambda **kwargs: kwargs
        with mock.patch.object(arms, "ArmHarness", return_value=harness), \
             mock.patch.object(arms, "_run_bo", side_effect=RuntimeError("broken BO")):
            result = arms.run_arm(self.spec, None, None, None)
        self.assertEqual(result["status"], "ARM_ERROR")
        self.assertIn("broken BO", result["optimizer"]["error"])


class FeedbackRecordTests(unittest.TestCase):
    def evaluate(self, **changes):
        fields = dict(status=arms.STATUS_VALID, D_i_N=10.0, lift_rel_error=0.0,
                      design_hash="fixture", L_N=100.0, L_ref_N=100.0, alpha_deg=2.0,
                      CLtot=0.2, CDi=0.01, Sref_m2=1.0, q_Pa=100.0,
                      backend="MOCK", source_kind="MOCK", cache_hit=False,
                      physical_solver_starts=0, simulated_solver_starts=1,
                      labels_visible_to_arm=True, error_code="")
        fields.update(changes)
        ledger = SimpleNamespace(starts_used=1, remaining_starts=4)
        evaluator = SimpleNamespace(ledger=ledger, requires_starts=True,
                                    evaluate=lambda vector: SimpleNamespace(**fields))
        harness = arms.ArmHarness(arms.ArmSpec("BO", budget_starts=5), None, None, evaluator)
        result = harness.evaluate(np.full(12, 0.5))
        return harness, result

    def test_failed_record_keeps_null(self):
        harness, result = self.evaluate(status="FAIL", D_i_N=None, lift_rel_error=None)
        self.assertIsNone(result["objective"])
        self.assertFalse(result["feasible"])
        self.assertIsNone(harness.best_D_i)

    def test_rejects_failed_finite_penalty(self):
        with self.assertRaisesRegex(ValueError, "objective must remain null"):
            self.evaluate(status="FAIL", D_i_N=1e9)

    def test_rejects_valid_nonfinite_or_missing_objective(self):
        for value in (None, float("nan"), float("inf"), -1.0):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "D_i_N"):
                self.evaluate(D_i_N=value)

    def test_rejects_missing_or_nonfinite_lift_error(self):
        for value in (None, float("nan"), float("inf"), -1.0):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "lift_rel_error"):
                self.evaluate(lift_rel_error=value)

    def test_lift_infeasible_point_does_not_become_best(self):
        harness, result = self.evaluate(lift_rel_error=arms.LIFT_TOL_REL * 2)
        self.assertTrue(result["valid"])
        self.assertFalse(result["feasible"])
        self.assertIsNone(harness.best_D_i)
        self.assertIsNone(harness.first_feasible_solver_start)

    def test_feasible_feedback_sets_best(self):
        harness, result = self.evaluate()
        self.assertEqual(harness.best_D_i, 10.0)
        self.assertEqual(harness.first_feasible_solver_start, 1)
        self.assertEqual(result["analysis_calls"], 1)

    def test_de_pso_failure_is_not_completed(self):
        for name in ("DE", "PSO"):
            harness = SimpleNamespace(budget_exhausted=False)
            harness.result = lambda **kwargs: kwargs
            with self.subTest(name=name), mock.patch.object(arms, "ArmHarness", return_value=harness), \
                 mock.patch.object(arms, "_run_" + name.lower(),
                                   return_value=dict(status="OPTIMIZER_ERROR", error="broken " + name)):
                result = arms.run_arm(arms.ArmSpec(name, budget_starts=4), None, None, None)
            self.assertEqual(result["status"], "ARM_ERROR")
            self.assertIn("broken", result["optimizer"]["error"])


if __name__ == "__main__":
    unittest.main()
