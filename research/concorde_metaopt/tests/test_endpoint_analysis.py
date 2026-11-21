
"""Tests for the primary endpoint analyzer (synthetic records only)."""
from __future__ import annotations

import unittest

from research.concorde_metaopt.dreal001.meta.endpoint_analysis import (
    DesignEvaluation, anytime_curve, best_feasible_at_budget, cost_to_target,
    feasible_hit_rate, first_feasible, simple_regret, summarize_run)


def rec(design, feasible, di_n=None, cases=0, starts=1, task="T1", source="real"):
    return DesignEvaluation(task_id=task, design_id=design, feasible=feasible,
                            di_n=di_n, internal_solver_cases=cases,
                            design_starts=starts, source=source)


SEQ = [rec("d0", False, cases=40), rec("d1", True, 120.0, cases=45),
       rec("d2", False, cases=50), rec("d3", True, 110.0, cases=48),
       rec("d4", True, 130.0, cases=42)]


class EndpointTests(unittest.TestCase):
    def test_first_feasible(self):
        out = first_feasible(SEQ)
        self.assertEqual(out["design_evaluations"], 2)
        self.assertEqual(out["design_starts"], 2)
        self.assertEqual(out["internal_solver_cases"], 85)
        self.assertEqual(out["di_n"], 120.0)

    def test_first_feasible_none(self):
        self.assertIsNone(first_feasible([rec("d0", False), rec("d1", False)]))

    def test_best_feasible_at_budget(self):
        self.assertIsNone(best_feasible_at_budget(SEQ, 1))
        self.assertEqual(best_feasible_at_budget(SEQ, 2)["best_feasible_di_n"], 120.0)
        self.assertEqual(best_feasible_at_budget(SEQ, 4)["best_feasible_di_n"], 110.0)
        self.assertEqual(best_feasible_at_budget(SEQ, 5)["best_feasible_di_n"], 110.0)

    def test_best_feasible_by_internal_cases(self):
        out = best_feasible_at_budget(SEQ, 100, cost_key="internal_solver_cases")
        self.assertEqual(out["design_id"], "d1")
        self.assertIsNone(best_feasible_at_budget(SEQ, 40, cost_key="internal_solver_cases"))

    def test_anytime_curve_is_monotone_non_increasing(self):
        curve = anytime_curve(SEQ, (1, 2, 3, 4, 5))
        values = [row["best_feasible_di_n"] for row in curve if row["best_feasible_di_n"] is not None]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertIsNone(curve[0]["best_feasible_di_n"])
        self.assertEqual(curve[-1]["best_feasible_di_n"], 110.0)

    def test_hit_rate(self):
        out = feasible_hit_rate(SEQ)
        self.assertEqual(out["feasible_evaluations"], 3)
        self.assertAlmostEqual(out["point_feasible_hit_rate"], 0.6)
        self.assertTrue(out["run_found_feasible"])

    def test_simple_regret_requires_reference(self):
        self.assertIsNone(simple_regret(SEQ, None))
        out = simple_regret(SEQ, 100.0)
        self.assertEqual(out["simple_regret"], 10.0)
        self.assertIsNone(simple_regret([rec("d0", False)], 100.0))
        with self.assertRaises(ValueError):
            simple_regret(SEQ, -1.0)

    def test_cost_to_target(self):
        out = cost_to_target(SEQ, 115.0)
        self.assertEqual(out["design_id"], "d3")
        self.assertEqual(out["design_starts"], 4)
        self.assertIsNone(cost_to_target(SEQ, 50.0))

    def test_records_are_validated(self):
        with self.assertRaises(ValueError):
            DesignEvaluation(task_id="T", design_id="d", feasible=True)
        with self.assertRaises(ValueError):
            DesignEvaluation(task_id="T", design_id="d", feasible=False, di_n=1.0)
        with self.assertRaises(ValueError):
            DesignEvaluation(task_id="T", design_id="d", feasible=True, di_n=1.0,
                             source="synthetic")
        with self.assertRaises(ValueError):
            best_feasible_at_budget(SEQ, 0)
        with self.assertRaises(ValueError):
            feasible_hit_rate([])

    def test_summarize_run(self):
        out = summarize_run(SEQ, budgets=(2, 4), reference_di_n=100.0,
                            target_di_n=115.0)
        self.assertEqual(out["evaluations"], 5)
        self.assertEqual(out["hit_rate"]["feasible_evaluations"], 3)
        self.assertEqual(out["first_feasible"]["design_starts"], 2)
        self.assertEqual(len(out["anytime_curve"]), 2)
        self.assertEqual(out["simple_regret"]["simple_regret"], 10.0)
        self.assertEqual(out["cost_to_target"]["design_id"], "d3")
        self.assertEqual(out["total_design_starts"], 5)
        self.assertEqual(out["total_internal_solver_cases"], 225)


if __name__ == "__main__":
    unittest.main()
