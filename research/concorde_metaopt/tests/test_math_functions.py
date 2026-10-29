"""P4 tests: constrained optimisers on analytic test functions.

The Issue requires the constrained BO / DE machinery to be proven on cheap
mathematical functions (Branin and Ackley with an explicit constraint) before
it is pointed at the expensive Concorde single-cruise evaluator. These tests
are zero-physics: no RCAIDE Mission, no SU2 and no dataset are touched.
"""

from __future__ import annotations

import math
import unittest

import numpy as np

from maml_opt.bayesian import ConstrainedBayesianOptimizer, run_search
from maml_opt.initialization import generate_initial_designs
from research.concorde_metaopt.optimization.baseline_de import DifferentialEvolutionBaseline

BRANIN_BOUNDS = (np.array([-5.0, 0.0]), np.array([10.0, 15.0]))
ACKLEY_BOUNDS = (np.array([-8.0, -8.0]), np.array([8.0, 8.0]))


def branin(x):
    a = 1.0
    b = 5.1 / (4.0 * math.pi ** 2)
    c = 5.0 / math.pi
    d = 6.0
    x0, x1 = float(x[0]), float(x[1])
    return a * (x1 - b * x0 ** 2 + c * x0 - d) ** 2 + 10.0 * (1.0 - 1.0 / (8.0 * math.pi)) * math.cos(x0) + 10.0


def ackley(x):
    x0, x1 = float(x[0]), float(x[1])
    return (
        -20.0 * math.exp(-0.2 * math.sqrt(0.5 * (x0 ** 2 + x1 ** 2)))
        - math.exp(0.5 * (math.cos(2.0 * math.pi * x0) + math.cos(2.0 * math.pi * x1)))
        + 20.0
        + math.e
    )


def make_evaluator(objective, constraint, counter=None):
    def evaluate(vector):
        if counter is not None:
            counter.append(np.asarray(vector, dtype=float).copy())
        constraints = {"g": float(constraint(vector))}
        value = float(objective(vector))
        return {
            "status": "VALID",
            "valid": True,
            "objective": value,
            "constraints_g_le_zero": constraints,
            "feasible": max(constraints.values()) <= 0.0,
            "analysis_calls": 1,
        }

    return evaluate


def de_search(objective, constraint, budget=60, population_size=10, seed=42, bounds=BRANIN_BOUNDS, impossible=False):
    lower, upper = bounds
    calls = []
    last = {"objective": None}
    if impossible:
        def constraint_fn(vector):
            return 100.0  # always infeasible
    else:
        constraint_fn = constraint
    evaluator = make_evaluator(objective, constraint_fn, calls)
    search = DifferentialEvolutionBaseline(
        dimension=2,
        budget=budget,
        seed=seed,
        population_size=population_size,
        lower_bounds=lower,
        upper_bounds=upper,
    )
    result = search.run(evaluator)
    result["calls"] = calls
    return result


class AnalyticFunctionsTests(unittest.TestCase):
    def test_branin_known_minimum(self):
        self.assertAlmostEqual(branin([-math.pi, 12.275]), 0.39788735772973816, places=6)
        self.assertAlmostEqual(branin([math.pi, 2.275]), 0.39788735772973816, places=6)

    def test_ackley_known_minimum(self):
        self.assertAlmostEqual(ackley([0.0, 0.0]), 0.0, places=12)
        self.assertGreater(ackley([4.0, -3.0]), 1.0)


class DifferentialEvolutionMathTests(unittest.TestCase):
    def test_branin_with_constraint_reaches_a_feasible_minimum(self):
        result = de_search(
            branin, lambda x: x[0] - 5.0, budget=120, population_size=12
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["physical_calls"], 120)
        self.assertIsNotNone(result["best_feasible"])
        self.assertLess(result["best_feasible"]["objective"], 1.0)
        self.assertLessEqual(result["best_feasible"]["objective"], result["iteration_best_feasible_objective"][0])
        for vector in result["calls"]:
            self.assertTrue(np.all(vector >= BRANIN_BOUNDS[0]))
            self.assertTrue(np.all(vector <= BRANIN_BOUNDS[1]))

    def test_branin_de_is_deterministic_for_a_seed(self):
        first = de_search(branin, lambda x: x[0] - 5.0, budget=30, population_size=6, seed=7)
        second = de_search(branin, lambda x: x[0] - 5.0, budget=30, population_size=6, seed=7)
        self.assertEqual(first["best_feasible"]["objective"], second["best_feasible"]["objective"])
        self.assertEqual(
            [item["objective"] for item in first["trace"]],
            [item["objective"] for item in second["trace"]],
        )

    def test_branin_de_reports_no_feasible_solution(self):
        result = de_search(branin, lambda x: x[0] - 5.0, impossible=True)
        self.assertEqual(result["status"], "no_feasible_solution")
        self.assertIsNone(result["best_feasible"])
        self.assertEqual(result["termination_reason"], "no_accepted_trial_in_generation")
        self.assertLessEqual(result["physical_calls"], 60)

    def test_ackley_de_reaches_near_the_origin(self):
        result = de_search(
            ackley,
            lambda x: 0.0,
            budget=80,
            population_size=12,
            seed=11,
            bounds=ACKLEY_BOUNDS,
        )
        self.assertEqual(result["status"], "completed")
        self.assertIsNotNone(result["best_feasible"])
        self.assertLess(result["best_feasible"]["objective"], 5.0)
        self.assertLess(
            result["best_feasible"]["objective"],
            result["iteration_best_feasible_objective"][0],
        )


class BayesianOptimisationMathTests(unittest.TestCase):
    def _run(self, objective, constraint, budget=30, initial_count=10, seed=42, bounds=BRANIN_BOUNDS, impossible=False):
        lower, upper = bounds
        optimizer = ConstrainedBayesianOptimizer(
            lower_bounds=lower,
            upper_bounds=upper,
            seed=seed,
            candidate_count=256,
        )
        initial = generate_initial_designs(
            lower, upper, initial_count, seed=seed, method="lhs"
        )
        calls = []
        if impossible:
            def constraint_fn(vector):
                return 100.0
        else:
            constraint_fn = constraint

        def evaluator(vector):
            calls.append(np.asarray(vector, dtype=float).copy())
            constraints = {"g": float(constraint_fn(vector))}
            return {
                "status": "VALID",
                "valid": True,
                "objective": float(objective(vector)),
                "constraints_g_le_zero": constraints,
                "feasible": max(constraints.values()) <= 0.0,
                "analysis_calls": 1,
            }

        result = run_search(
            optimizer,
            evaluator,
            initial,
            max_design_evaluations=budget,
            strategy="bayesian",
        )
        result["calls"] = calls
        result["initial"] = np.asarray(initial, dtype=float)
        return result

    def test_branin_bo_finds_a_feasible_minimum(self):
        result = self._run(branin, lambda x: x[0] - 5.0)
        self.assertEqual(result["status"], "SEARCH_COMPLETE")
        self.assertEqual(result["design_evaluations"], 30)
        self.assertEqual(len(result["calls"]), 30)
        self.assertGreaterEqual(result["feasible_evaluations"], 1)
        self.assertLess(result["best_feasible"]["objective"], 1.0)
        for vector in result["calls"]:
            self.assertTrue(np.all(vector >= BRANIN_BOUNDS[0]))
            self.assertTrue(np.all(vector <= BRANIN_BOUNDS[1]))

    def test_branin_bo_is_deterministic_for_a_seed(self):
        first = self._run(branin, lambda x: x[0] - 5.0, budget=20, initial_count=8, seed=5)
        second = self._run(branin, lambda x: x[0] - 5.0, budget=20, initial_count=8, seed=5)
        self.assertEqual(first["best_feasible"]["objective"], second["best_feasible"]["objective"])
        self.assertEqual(
            [item["objective"] for item in first["history"]],
            [item["objective"] for item in second["history"]],
        )

    def test_branin_bo_reports_no_feasible_solution(self):
        result = self._run(branin, lambda x: x[0] - 5.0, budget=20, initial_count=8, impossible=True)
        self.assertEqual(result["status"], "NO_FEASIBLE_SOLUTION")
        self.assertIsNone(result["best_feasible"])
        self.assertEqual(result["design_evaluations"], 20)


class BudgetStoppingTests(unittest.TestCase):
    def test_de_never_exceeds_its_budget(self):
        result = de_search(branin, lambda x: x[0] - 5.0, budget=17, population_size=5)
        self.assertEqual(result["physical_calls"], 17)
        self.assertEqual(len(result["calls"]), 17)

    def test_bo_never_exceeds_its_budget(self):
        result = BayesianOptimisationMathTests()._run(
            branin, lambda x: x[0] - 5.0, budget=14, initial_count=6
        )
        self.assertEqual(result["design_evaluations"], 14)
        self.assertEqual(len(result["calls"]), 14)


if __name__ == "__main__":
    unittest.main()
