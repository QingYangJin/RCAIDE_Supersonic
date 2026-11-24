"""Guard tests for the O0 real-feedback optimization protocol (no solver)."""
import unittest
from unittest import mock

from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0


class O0ProtocolTests(unittest.TestCase):
    def test_caps_match_the_preregistered_budget(self):
        self.assertEqual(o0.CAPS["max_design_attempts"], 12)
        self.assertEqual(o0.CAPS["max_solver_starts"], 36)
        self.assertEqual(o0.CAPS["max_internal_cases"], 240)
        self.assertEqual(o0.CAPS["max_starts_per_design"], 2)
        self.assertEqual(o0.CAPS["max_internal_per_design"], 20)

    def test_alpha_plan_fits_the_internal_cap_per_design(self):
        plan = o0.alpha_plan()
        self.assertLessEqual(plan["max_internal_cases_per_design"],
                             o0.CAPS["max_internal_per_design"])
        self.assertLessEqual(plan["starts_per_design_max"],
                             o0.CAPS["max_starts_per_design"])
        # The coarse window must bracket the fixed-lift alpha for any design in the
        # frozen box (measured alpha moves ~0.33 deg per deg of sweep_1), so it is
        # wider than a 6-point local guess and the refinement is correspondingly
        # coarse; only the joint 20-case per-design cap is contractual.
        self.assertEqual(plan["coarse_internal_cases"], 7)
        self.assertLessEqual(plan["refine_internal_cases"], 13)
        self.assertGreaterEqual(plan["coarse_alphas_deg"][-1]
                                - plan["coarse_alphas_deg"][0], 1.9)
        for alpha in plan["coarse_alphas_deg"]:
            self.assertGreaterEqual(alpha, o0.ALPHA_WINDOW_DEG[0])
            self.assertLessEqual(alpha, o0.ALPHA_WINDOW_DEG[1])

    def test_frozen_variables_may_not_move(self):
        design = list(o0.BASELINE_X12)
        o0.check_design(design)
        moved = list(design)
        moved[0] = moved[0] + 1.0  # wing_area is outside the O0 subspace
        with self.assertRaisesRegex(o0.ProtocolError, "frozen in the O0 subspace"):
            o0.check_design(moved)

    def test_subspace_bounds_are_enforced(self):
        with self.assertRaisesRegex(o0.ProtocolError, "outside the frozen local box"):
            o0.subspace_to_design([o0.SUBSPACE_BOUNDS["sweep_1"][1] + 1.0, 48.0])

    def test_bootstrap_starts_from_the_frozen_baseline(self):
        designs = o0.bootstrap_designs(4)
        self.assertEqual(len(designs), 4)
        first = o0.design_identity(designs[0])
        self.assertTrue(first["is_baseline"])
        self.assertEqual(designs[0], list(o0.BASELINE_X12))
        identities = {o0.design_identity(d)["design_id"] for d in designs}
        self.assertEqual(len(identities), 4, "bootstrap designs must be distinct")
        for design in designs:
            o0.check_design(design)

    def test_physical_15_reinjects_the_frozen_fuselage(self):
        vector = o0.physical_15(o0.BASELINE_X12)
        self.assertEqual(len(vector), 15)
        self.assertEqual(vector[12:], [61.66, 4.3, 1.152778])
        self.assertEqual(tuple(o0.PHYSICAL_15_NAMES),
                         o0.VARIABLE_ORDER + ("fuselage_length", "fuselage_fineness",
                                              "fuselage_height_width_ratio"))

    def test_lift_prediction_rejects_a_non_monotone_bracket(self):
        rows = [(5.0, 0.18), (5.16, 0.19), (5.32, 0.185)]
        result = o0.predict_alpha(rows, 0.1817)
        self.assertFalse(result["ok"])
        self.assertIn("monotonically", result["reason"])

    def test_lift_prediction_returns_the_fixed_lift_alpha(self):
        # rows on the real M202 slope 0.0345 CL/deg through the frozen CL target
        target = 0.18174391741992046
        slope = 0.0345
        intercept = target - slope * 5.1813
        rows = [(alpha, intercept + slope * alpha)
                for alpha in (4.94, 5.10, 5.26)]
        result = o0.predict_alpha(rows, target)
        self.assertTrue(result["ok"], result)
        alpha = result["predicted_alpha_deg"]
        self.assertAlmostEqual(alpha, 5.1813, places=2)

    def test_ledger_prevents_budget_overrun(self):
        ledger = o0.AttemptLedger()
        attempt = o0.AttemptRecord(0, "BOOTSTRAP", list(o0.BASELINE_X12), "id", "hash", True)
        ledger.add(attempt)
        ledger.charge(attempt, starts=1, internal=6)
        ledger.charge(attempt, starts=1, internal=14)
        self.assertEqual(ledger.remaining(), {"attempts": 11, "solver_starts": 34,
                                              "internal_cases": 220})
        with self.assertRaisesRegex(o0.ProtocolError, "20 internal cases"):
            ledger.charge(attempt, starts=0, internal=1)
        with self.assertRaisesRegex(o0.ProtocolError, "exceed 2 starts"):
            ledger.charge(attempt, starts=1, internal=0)

    def test_caps_are_exact_per_design_not_merely_upper_bounds(self):
        # A third start on one design must be architecturally impossible: the alpha
        # plan is exactly the two-start recipe and CAPS encodes the same number.
        self.assertEqual(o0.alpha_plan()["starts_per_design_max"],
                         o0.CAPS["max_starts_per_design"])
        self.assertEqual(o0.alpha_plan()["max_internal_cases_per_design"],
                         o0.CAPS["max_internal_per_design"])
        ledger = o0.AttemptLedger()
        attempt = o0.AttemptRecord(0, "BOOTSTRAP", list(o0.BASELINE_X12), "id", "hash", True)
        ledger.add(attempt)
        ledger.charge(attempt, starts=1, internal=7)
        ledger.charge(attempt, starts=1, internal=13)
        with self.assertRaisesRegex(o0.ProtocolError, "exceed 2 starts"):
            ledger.charge(attempt, starts=1, internal=0)
        self.assertEqual(ledger.summary()["solver_starts_actual"], 2)

    def test_execution_contract_is_serial_and_retry_free(self):
        o0.assert_execution_contract()
        self.assertEqual(o0.CAPS["parallelism"], 1)
        self.assertEqual(o0.CAPS["retries"], 0)
        # The guard reads the module CAPS, so prove each failure mode by patching it.
        with mock.patch.object(o0, "CAPS", {**o0.CAPS, "parallelism": 2}):
            with self.assertRaisesRegex(o0.ProtocolError, "parallelism 1 only"):
                o0.assert_execution_contract()
        with mock.patch.object(o0, "CAPS", {**o0.CAPS, "retries": 1}):
            with self.assertRaisesRegex(o0.ProtocolError, "zero retries"):
                o0.assert_execution_contract()
        with mock.patch.object(o0, "CAPS", {**o0.CAPS, "max_starts_per_design": 3}):
            with self.assertRaisesRegex(o0.ProtocolError, "exactly 2 charged starts"):
                o0.assert_execution_contract()

    def test_counterfactual_feedback_changes_the_next_candidate(self):
        result = o0.counterfactual_check(None)
        self.assertTrue(result["protocol_ok"], result)
        self.assertIsNotNone(result["first_divergence_index"])
        self.assertNotEqual(result["control_sequence"], result["counterfactual_sequence"])

    def test_loop_records_failures_as_null_objectives(self):
        def evaluator(attempt):
            attempt.starts = 1
            attempt.internal = 20
            if attempt.design_index == 0:
                attempt.status = "LIFT_NOT_MATCHED"
                attempt.feasible = False
                attempt.objective = None
                attempt.failure_kind = "NO_RAW_ROW_WITHIN_TOLERANCE"
                return attempt
            attempt.status = "SOLVED"
            attempt.feasible = True
            attempt.objective = 100000.0 - 100.0 * attempt.design_index
            return attempt

        result = o0.run_bo_loop(evaluate=evaluator, ledger=o0.AttemptLedger(),
                                seed=7, max_attempts=6, bootstrap_count=4)
        self.assertEqual(result["ledger"]["design_attempts"], 6)
        self.assertEqual(result["ledger"]["failed_designs"], 1)
        failed = [a for a in result["attempts"] if not a["feasible"]]
        self.assertEqual(len(failed), 1)
        self.assertIsNone(failed[0]["objective"])
        self.assertEqual(failed[0]["failure_kind"], "NO_RAW_ROW_WITHIN_TOLERANCE")
        self.assertEqual(result["physical_solver_starts_actual"], 6)
        self.assertFalse(result["physics_validated"])

    def test_a_streak_of_unadmitted_designs_stops_before_the_design_cap(self):
        def evaluator(attempt):
            attempt.starts = 2
            attempt.internal = 20
            attempt.status = "AUDIT_FAILED"
            attempt.feasible = False
            attempt.objective = None
            attempt.failure_kind = "NO_RAW_ROW_IN_LIFT_TOLERANCE"
            return attempt

        result = o0.run_bo_loop(evaluate=evaluator, ledger=o0.AttemptLedger(),
                                seed=13, max_attempts=12, bootstrap_count=4)
        self.assertEqual(result["ledger"]["design_attempts"], 3)
        self.assertEqual(result["physical_solver_starts_actual"], 6)
        self.assertIn("3 consecutive designs", result["stopped_by_unadmitted_streak"])
        self.assertEqual(result["unadmitted_streak_limit"], 3)
        # Budget is left deliberately unspent rather than grinding out 12 misses.
        self.assertEqual(result["ledger"]["remaining"]["solver_starts"], 30)

    def test_a_short_unadmitted_streak_does_not_stop_the_run(self):
        def evaluator(attempt):
            attempt.starts = 2
            attempt.internal = 20
            if attempt.design_index % 2 == 0 and attempt.design_index < 4:
                attempt.status = "AUDIT_FAILED"
                attempt.feasible = False
                attempt.objective = None
                attempt.failure_kind = "NO_RAW_ROW_IN_LIFT_TOLERANCE"
            else:
                attempt.status = "FEASIBLE_ADMITTED"
                attempt.feasible = True
                attempt.objective = 100000.0
            return attempt

        result = o0.run_bo_loop(evaluate=evaluator, ledger=o0.AttemptLedger(),
                                seed=17, max_attempts=6, bootstrap_count=4)
        self.assertEqual(result["ledger"]["design_attempts"], 6)
        self.assertIsNone(result["stopped_by_unadmitted_streak"])

    def test_evaluator_crash_still_settles_the_spent_start(self):
        calls = {"n": 0}

        def evaluator(attempt):
            calls["n"] += 1
            # O0-B01 shape: the start happened and the evaluator declared it, then a
            # bug inside the evaluator raised before the loop could settle.
            attempt.starts = 1
            attempt.internal = 7
            raise RuntimeError("fixture evaluator exploded after the solver ran")

        ledger = o0.AttemptLedger()
        with self.assertRaisesRegex(RuntimeError, "exploded"):
            o0.run_bo_loop(evaluate=evaluator, ledger=ledger, seed=23,
                           max_attempts=6, bootstrap_count=4)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(ledger.starts_used, 1, "a spent start must not vanish")
        self.assertEqual(ledger.internal_used, 7)
        summary = ledger.summary()
        self.assertEqual(summary["physical_solver_starts_actual"], 1)
        self.assertEqual(summary["internal_solver_cases_actual"], 7)
        self.assertEqual(summary["remaining"]["solver_starts"], 35)

    def test_evaluator_crash_that_overruns_the_caps_keeps_the_original_error(self):
        def evaluator(attempt):
            # An evaluator cannot quietly claim more starts than the caps allow.
            attempt.starts = 99
            attempt.internal = 999
            raise RuntimeError("fixture evaluator exploded after over-declaring")

        ledger = o0.AttemptLedger()
        with self.assertRaisesRegex(RuntimeError, "exploded"):
            o0.run_bo_loop(evaluate=evaluator, ledger=ledger, seed=29,
                           max_attempts=6, bootstrap_count=4)
        self.assertEqual(ledger.starts_used, 0)
        self.assertIn("could not settle", ledger.attempts[0].detail)
        self.assertEqual(ledger.attempts[0].starts, 99)

    def test_improvement_is_reported_against_the_measured_baseline(self):
        def evaluator(attempt):
            attempt.starts = 2
            attempt.internal = 20
            attempt.status = "SOLVED"
            attempt.feasible = True
            attempt.objective = 120000.0 if attempt.is_baseline else 114000.0
            return attempt

        result = o0.run_bo_loop(evaluate=evaluator, ledger=o0.AttemptLedger(),
                                seed=11, max_attempts=6, bootstrap_count=4)
        self.assertEqual(result["baseline_di_n"], 120000.0)
        self.assertEqual(result["best_feasible_di_n"], 114000.0)
        self.assertAlmostEqual(result["improvement_fraction"], 0.05)
        self.assertTrue(result["non_baseline_feasible"])


if __name__ == "__main__":
    unittest.main()