
"""P0 unit tests for the target-lift adaptive alpha solver (synthetic only)."""
from __future__ import annotations

import unittest

from research.concorde_metaopt.dreal001.geometry.adaptive_alpha import (
    AdaptiveAlphaSolver, AdaptiveAlphaSpec, AlphaEvaluation,
    BUDGET_EXHAUSTED, INVALID_POLAR, NO_BRACKET, NO_CONVERGENCE,
    RAW_POINT_MATCHED, SOLVER_FAILED, replay_on_existing_rows,
    relative_cl_error)

ALPHAS = (4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0)


def linear_curve(target_cl, tol=1e-3, alphas=ALPHAS, max_cases=24,
                 max_steps=8, quadratic=0.0):
    """cl(alpha) = 0.04*alpha + 0.06 (+ quadratic term), monotone on [4, 7]."""
    spec = AdaptiveAlphaSpec(cl_target=target_cl, tol_cl=tol,
                             coarse_alphas=tuple(alphas),
                             max_solver_cases=max_cases,
                             max_refine_steps=max_steps)
    def evaluate(alpha):
        cl = 0.04 * alpha + 0.06 + quadratic * (alpha - 6.0) ** 2
        return AlphaEvaluation(alpha_deg=alpha, cl=cl, cdi=0.02)
    return spec, evaluate


class AdaptiveAlphaTests(unittest.TestCase):
    def test_exact_coarse_point_is_raw_matched(self):
        spec, evaluate = linear_curve(target_cl=0.30)
        result = AdaptiveAlphaSolver(spec).run(evaluate)
        self.assertEqual(result.status, RAW_POINT_MATCHED)
        self.assertEqual(result.solver_cases, 5)  # stops at the matching coarse point
        self.assertAlmostEqual(result.matched.alpha_deg, 6.0, places=12)
        self.assertLessEqual(relative_cl_error(result.matched.cl, spec.cl_target), spec.tol_cl)
        self.assertEqual(result.matched.cl, evaluate(6.0).cl)

    def test_refinement_reaches_raw_point_without_extrapolation(self):
        spec, evaluate = linear_curve(target_cl=0.29)
        result = AdaptiveAlphaSolver(spec).run(evaluate)
        self.assertEqual(result.status, RAW_POINT_MATCHED)
        self.assertGreater(result.solver_cases, 7)
        self.assertLessEqual(result.solver_cases, 9)
        self.assertTrue(4.0 <= result.matched.alpha_deg <= 7.0)
        self.assertLessEqual(relative_cl_error(result.matched.cl, spec.cl_target), spec.tol_cl)
        # every probe was a real evaluated alpha requested by the solver
        self.assertTrue(all(p.alpha_deg == evaluate(p.alpha_deg).alpha_deg
                            for p in result.probes))

    def test_target_above_polar_returns_no_bracket(self):
        spec, evaluate = linear_curve(target_cl=0.9)
        result = AdaptiveAlphaSolver(spec).run(evaluate)
        self.assertEqual(result.status, NO_BRACKET)
        self.assertIsNone(result.matched)
        self.assertEqual(result.solver_cases, 7)

    def test_decreasing_polar_never_interpolates(self):
        spec = AdaptiveAlphaSpec(cl_target=0.293, tol_cl=1e-3,
                                 coarse_alphas=ALPHAS, max_solver_cases=12)
        result = AdaptiveAlphaSolver(spec).run(
            lambda a: AlphaEvaluation(alpha_deg=a, cl=0.40 - 0.02 * a))
        self.assertEqual(result.status, NO_BRACKET)
        self.assertIsNone(result.matched)

    def test_nonmonotone_refinement_reports_invalid_polar(self):
        coarse = {4.0: 0.28, 4.5: 0.285, 5.0: 0.288, 5.5: 0.295, 6.0: 0.30,
                  6.5: 0.305, 7.0: 0.31}
        spec = AdaptiveAlphaSpec(cl_target=0.292, tol_cl=1e-3,
                                 coarse_alphas=ALPHAS, max_solver_cases=16)
        def evaluate(alpha):
            if alpha in coarse:
                return AlphaEvaluation(alpha_deg=alpha, cl=coarse[alpha])
            # a dip inside the bracket: interpolating here would be a lie
            return AlphaEvaluation(alpha_deg=alpha, cl=0.25)
        result = AdaptiveAlphaSolver(spec).run(evaluate)
        self.assertEqual(result.status, INVALID_POLAR)
        self.assertIsNone(result.matched)
        self.assertIsNotNone(result.bracket)

    def test_solver_failure_path(self):
        spec = AdaptiveAlphaSpec(cl_target=0.29, coarse_alphas=(4.0, 4.5, 5.0),
                                 max_solver_cases=6)
        def failing(alpha):
            return AlphaEvaluation(alpha_deg=alpha, cl=None, ok=False,
                                   reason="VSPAERO_NONZERO_EXIT")
        result = AdaptiveAlphaSolver(spec).run(failing)
        self.assertEqual(result.status, SOLVER_FAILED)
        self.assertEqual(result.solver_cases, 3)
        self.assertTrue(result.reasons)

    def test_budget_exhaustion_stops_without_label(self):
        spec, evaluate = linear_curve(target_cl=0.29, max_cases=7)
        result = AdaptiveAlphaSolver(spec).run(evaluate)
        self.assertEqual(result.status, BUDGET_EXHAUSTED)
        self.assertIsNone(result.matched)
        self.assertEqual(result.solver_cases, 7)

    def test_tolerance_too_strict_reports_estimate_not_label(self):
        spec, evaluate = linear_curve(target_cl=0.29, tol=1e-12, max_steps=4,
                                      quadratic=0.0004)
        result = AdaptiveAlphaSolver(spec).run(evaluate)
        self.assertEqual(result.status, NO_CONVERGENCE)
        self.assertIsNone(result.matched)
        self.assertIsNotNone(result.estimate_alpha_deg)
        self.assertIsNotNone(result.bracket)
        left, right = result.bracket
        self.assertLessEqual(left.alpha_deg, result.estimate_alpha_deg)
        self.assertLessEqual(result.estimate_alpha_deg, right.alpha_deg)
        self.assertGreater(result.best.cl, 0.0)
        self.assertGreater(relative_cl_error(result.best.cl, spec.cl_target), spec.tol_cl)

    def test_spec_validation(self):
        with self.assertRaises(ValueError):
            AdaptiveAlphaSpec(cl_target=0.0)
        with self.assertRaises(ValueError):
            AdaptiveAlphaSpec(cl_target=0.29, tol_cl=0.0)
        with self.assertRaises(ValueError):
            AdaptiveAlphaSpec(cl_target=0.29, coarse_alphas=(4.0, 5.0))
        with self.assertRaises(ValueError):
            AdaptiveAlphaSpec(cl_target=0.29, coarse_alphas=(4.0, 4.0, 5.0))
        with self.assertRaises(ValueError):
            AdaptiveAlphaSpec(cl_target=0.29, coarse_alphas=(4.0, 4.5, 5.0),
                              max_solver_cases=2)

    def test_evaluation_rejects_inconsistent_state(self):
        with self.assertRaises(ValueError):
            AlphaEvaluation(alpha_deg=5.0, cl=None, ok=True)
        with self.assertRaises(ValueError):
            AlphaEvaluation(alpha_deg=5.0, cl=0.2, ok=False)

    def test_replay_uses_only_existing_rows(self):
        alphas = tuple(round(6.0 + 0.03 * i, 10) for i in range(13))
        target = 0.29
        cl_values = tuple(0.22 + 0.0368 * (a - 6.0) + 0.0004 * (a - 6.0) ** 2
                          for a in alphas)
        spec = AdaptiveAlphaSpec(cl_target=target, tol_cl=1e-3,
                                 coarse_alphas=(alphas[0], alphas[6], alphas[12]),
                                 max_solver_cases=16, max_refine_steps=8)
        result = replay_on_existing_rows(alphas, cl_values, spec)
        self.assertLessEqual(result.solver_cases, len(alphas))
        row_alphas = {round(a, 10) for a in alphas}
        for probe in result.probes:
            if probe.ok:
                self.assertIn(probe.alpha_deg, row_alphas)
        if result.status == RAW_POINT_MATCHED:
            self.assertLessEqual(relative_cl_error(result.matched.cl, target),
                                 spec.tol_cl)

    def test_replay_fails_closed_when_row_missing(self):
        alphas = (6.0, 6.5, 7.0)
        cl_values = (0.22, 0.24, 0.26)
        spec = AdaptiveAlphaSpec(cl_target=0.25, tol_cl=1e-6,
                                 coarse_alphas=(6.0, 6.5, 7.0), max_solver_cases=8)
        result = replay_on_existing_rows(alphas, cl_values, spec)
        self.assertNotEqual(result.status, RAW_POINT_MATCHED)
        missing = [p for p in result.probes if not p.ok]
        self.assertTrue(missing)
        self.assertTrue(all(p.reason == "REPLAY_ROW_NOT_AVAILABLE" for p in missing))

    def test_deterministic(self):
        spec, evaluate = linear_curve(target_cl=0.293)
        first = AdaptiveAlphaSolver(spec).run(evaluate)
        second = AdaptiveAlphaSolver(spec).run(evaluate)
        self.assertEqual([p.alpha_deg for p in first.probes],
                         [p.alpha_deg for p in second.probes])
        self.assertEqual(first.status, second.status)


if __name__ == "__main__":
    unittest.main()
