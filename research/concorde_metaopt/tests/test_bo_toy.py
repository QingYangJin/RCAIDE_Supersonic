"""P4 tests: the ordinary constrained BO baseline on a toy evaluator.

No RCAIDE Mission and no SU2 run happens here. A deterministic synthetic
backend exercises the search mechanics, the shared budget ledger and every
P4 artefact, so the real small-budget BO can be authorised separately.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research.concorde_metaopt.aircraft.design_space import load_design_space
from research.concorde_metaopt.evaluation.contract import CONSTRAINT_NAMES
from research.concorde_metaopt.optimization.baseline_bo import (
    BaselineError,
    run_baseline_bo,
)
from research.concorde_metaopt.tasks.task_spec import load_task_spec

TMP_ROOT = Path(tempfile.mkdtemp(prefix="concorde-p4-tests-"))

BASELINE_OBJECTIVE = 34135.4
OPTIMUM_OBJECTIVE = 34000.0


def unit_coordinates(design):
    space = load_design_space()
    values = []
    for variable in space.variables:
        span = variable.upper - variable.lower
        values.append((float(design[variable.name]) - variable.lower) / span)
    return values


class ToyBackend:
    """Synthetic quadratic objective with one explicit feasibility constraint."""

    fidelity = "single_cruise"

    def __init__(self, impossible=False, scale=1.0):
        self.impossible = impossible
        self.scale = float(scale)
        self.calls = 0
        self.tasks = []

    def preflight(self):
        return {"status": "PREFLIGHT_OK", "physical_call_count": 0, "fidelity": self.fidelity}

    def evaluate(self, design, task=None, fidelity=None, purpose="search"):
        self.calls += 1
        self.tasks.append(task)
        u = unit_coordinates(design)
        objective = BASELINE_OBJECTIVE + self.scale * 1000.0 * (
            (u[0] - 0.25) ** 2 + 0.5 * ((u[9] - 0.1) ** 2) - 0.13540
        )
        constraints = {name: -0.05 for name in CONSTRAINT_NAMES}
        constraints["task_mass_balance"] = 0.0
        constraints["mission_convergence"] = 0.0
        constraints["cruise_range_error"] = 0.0
        if self.impossible:
            constraints["max_throttle"] = 1.0
        else:
            constraints["max_throttle"] = u[0] - 0.7
        return {
            "status": "VALID",
            "objective": objective,
            "constraints": constraints,
            "feasible": max(constraints.values()) <= 0.0,
            "fidelity": fidelity or self.fidelity,
            "diagnostics": [],
            "physical_call_count": 1,
        }


class BaselineBOTests(unittest.TestCase):
    def setUp(self):
        self.space = load_design_space()
        self.task = load_task_spec()
        self.output_root = TMP_ROOT / self._testMethodName
        if self.output_root.exists():
            shutil.rmtree(self.output_root)

    def _run(self, run_id="toy-bo", backend=None, budget=12, initial_design_count=4, **kwargs):
        return run_baseline_bo(
            output_root=self.output_root,
            run_id=run_id,
            budget=budget,
            seed=42,
            initial_design_count=initial_design_count,
            design_space=self.space,
            task=self.task,
            backend=backend if backend is not None else ToyBackend(),
            **kwargs
        )

    def test_toy_bo_improves_within_budget(self):
        backend = ToyBackend()
        summary = self._run(backend=backend)
        self.assertEqual(summary["status"], "baseline_bo_completed")
        self.assertEqual(summary["method"], "ordinary_constrained_bo")
        self.assertEqual(summary["algorithm"], "bo")
        self.assertEqual(summary["stage"], "P4")
        self.assertEqual(summary["total_true_evaluations"], 12)
        self.assertEqual(backend.calls, 12)
        self.assertIs(backend.tasks[0], self.task)
        bo = summary["baseline_bo"]
        self.assertGreaterEqual(bo["feasible_evaluations"], 1)
        self.assertEqual(bo["ledger"]["budget"], 12)
        self.assertEqual(bo["ledger"]["budget_remaining"], 0)
        self.assertIsNotNone(summary["best_feasible_fuel_kg"])
        self.assertIsNotNone(summary["best_design_id"])
        self.assertLessEqual(summary["best_feasible_fuel_kg"], BASELINE_OBJECTIVE)
        self.assertGreater(bo["improvement_kg"], 0.0)
        self.assertLessEqual(summary["best_feasible_fuel_kg"], BASELINE_OBJECTIVE - 10.0)
        self.assertGreaterEqual(summary["best_feasible_fuel_kg"], OPTIMUM_OBJECTIVE)

    def test_artifacts_and_trace_are_written(self):
        summary = self._run(run_id="toy-artifacts")
        run_dir = self.output_root / "toy-artifacts"
        for name in (
            "summary.json",
            "run_config.json",
            "environment.json",
            "best_design.json",
            "evaluations.jsonl",
            "opt_trace.jsonl",
            "observations.csv",
            "data_manifest.json",
            "README.md",
        ):
            self.assertTrue((run_dir / name).exists(), name)
        figures = summary["artifacts"]["figures"]
        self.assertTrue((run_dir / figures["convergence"]).stat().st_size > 1000)
        self.assertTrue((run_dir / figures["feasibility_rate"]).stat().st_size > 1000)
        trace = [
            json.loads(line)
            for line in (run_dir / "opt_trace.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(len(trace), 12)
        self.assertTrue(all(row["analysis_calls"] == 1 for row in trace))
        self.assertEqual([row["iteration"] for row in trace], list(range(0, 12)))
        evaluations = [
            line
            for line in (run_dir / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(len(evaluations), 12)
        observations = (run_dir / "observations.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(observations), 13)
        best = json.loads((run_dir / "best_design.json").read_text(encoding="utf-8"))
        self.assertTrue(best["feasible"])
        self.assertAlmostEqual(best["best_feasible_objective"], summary["best_feasible_fuel_kg"])
        self.assertEqual(best["algorithm"], "bo")
        index = json.loads((self.output_root / "index.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["run_id"] for entry in index["runs"]], ["toy-artifacts"])
        self.assertEqual(index["runs"][0]["status"], "completed")
        manifest = json.loads((run_dir / "data_manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["files"])
        self.assertTrue(all("sha256" in entry for entry in manifest["files"]))

    def test_no_feasible_solution_is_reported_without_a_fake_objective(self):
        summary = self._run(run_id="toy-infeasible", backend=ToyBackend(impossible=True))
        self.assertEqual(summary["status"], "baseline_bo_no_feasible_solution")
        self.assertIsNone(summary["best_feasible_fuel_kg"])
        self.assertIsNone(summary["best_design_id"])
        self.assertEqual(summary["baseline_bo"]["feasible_evaluations"], 0)
        self.assertGreaterEqual(summary["baseline_bo"]["valid_evaluations"], 1)
        best = json.loads(
            (self.output_root / "toy-infeasible" / "best_design.json").read_text(encoding="utf-8")
        )
        self.assertFalse(best["feasible"])
        self.assertIsNone(best["best_feasible_objective"])

    def test_random_strategy_still_uses_the_shared_ledger(self):
        summary = self._run(run_id="toy-random", budget=8, strategy="random")
        self.assertEqual(summary["status"], "baseline_bo_completed")
        self.assertEqual(summary["total_true_evaluations"], 8)
        self.assertEqual(summary["baseline_bo"]["strategy"], "random")

    def test_budget_and_initial_design_validation(self):
        with self.assertRaises(BaselineError):
            self._run(budget=0)
        with self.assertRaises(BaselineError):
            self._run(initial_design_count=1)
        with self.assertRaises(BaselineError):
            self._run(budget=4, initial_design_count=5)
        with self.assertRaises(BaselineError):
            self._run(strategy="unsupported")

    def test_existing_run_directory_is_never_reused(self):
        self._run(run_id="toy-existing", budget=4, initial_design_count=2)
        with self.assertRaises(FileExistsError):
            self._run(run_id="toy-existing", budget=4, initial_design_count=2)
        # allow_existing may reuse an empty directory, but never a directory that
        # already holds evidence: mixing two runs would corrupt both trails.
        with self.assertRaises(FileExistsError):
            self._run(
                run_id="toy-existing", budget=4, initial_design_count=2, allow_existing=True
            )

    def test_allow_existing_accepts_an_empty_run_directory(self):
        (TMP_ROOT / "toy-empty").mkdir(parents=True, exist_ok=True)
        summary = self._run(
            run_id="toy-empty", budget=4, initial_design_count=2, allow_existing=True
        )
        self.assertEqual(summary["total_true_evaluations"], 4)

    def test_run_id_cannot_escape_the_output_root(self):
        for bad_id in ("../escape", "nested/run", "C:/abs", "", "..", "run\\name"):
            with self.assertRaises(BaselineError):
                self._run(run_id=bad_id, budget=4, initial_design_count=2)


class EvaluatorResultTests(unittest.TestCase):
    """The BO adapter must never hand maml-opt a partial constraint mapping."""

    def _row(self, constraints, status="VALID", objective=34000.0, feasible=True):
        return {
            "iteration": 1,
            "design_id": "d-test",
            "x": {},
            "status": status,
            "objective": objective,
            "constraints": constraints,
            "feasible": feasible,
            "fidelity": "single_cruise",
            "cache_hit": False,
            "physical_call_count": 1,
            "wall_seconds": 0.0,
            "cumulative_calls": 1,
            "best_feasible_objective": objective,
        }

    def test_partial_constraints_are_downgraded(self):
        from research.concorde_metaopt.optimization.baseline_bo import _evaluator_result

        partial = {name: -0.05 for name in CONSTRAINT_NAMES[:3]}
        result = _evaluator_result(self._row(partial))
        self.assertFalse(result["valid"])
        self.assertEqual(result["status"], "INVALID_OR_MISSING_RESPONSE")
        self.assertIsNone(result["objective"])
        self.assertFalse(result["feasible"])
        self.assertEqual(result["constraints_g_le_zero"], {})
        self.assertIn("error", result)
        self.assertEqual(result["analysis_calls"], 1)

    def test_infeasible_row_is_still_valid_but_not_feasible(self):
        from research.concorde_metaopt.optimization.baseline_bo import _evaluator_result

        constraints = {name: -0.05 for name in CONSTRAINT_NAMES}
        constraints["max_throttle"] = 0.2
        result = _evaluator_result(self._row(constraints, feasible=False))
        self.assertTrue(result["valid"])
        self.assertFalse(result["feasible"])
        self.assertEqual(result["objective"], 34000.0)
        self.assertGreater(result["constraints_g_le_zero"]["max_throttle"], 0.0)

    def test_tolerance_sized_violation_is_shifted_to_feasible(self):
        from research.concorde_metaopt.evaluation.contract import FEASIBILITY_TOLERANCE
        from research.concorde_metaopt.optimization.baseline_bo import _evaluator_result

        constraints = {name: -0.05 for name in CONSTRAINT_NAMES}
        constraints["cruise_range_error"] = FEASIBILITY_TOLERANCE / 2.0
        result = _evaluator_result(self._row(constraints))
        self.assertTrue(result["valid"])
        self.assertLessEqual(result["constraints_g_le_zero"]["cruise_range_error"], 0.0)
        self.assertAlmostEqual(
            result["constraints_g_le_zero"]["cruise_range_error"],
            FEASIBILITY_TOLERANCE / 2.0 - FEASIBILITY_TOLERANCE,
            places=18,
        )

    def test_non_valid_row_cannot_carry_an_objective(self):
        from research.concorde_metaopt.optimization.baseline_bo import _evaluator_result

        constraints = {name: -0.05 for name in CONSTRAINT_NAMES}
        result = _evaluator_result(
            self._row(constraints, status="MISSION_FAILED", objective=1.0, feasible=True)
        )
        self.assertFalse(result["valid"])
        self.assertIsNone(result["objective"])
        self.assertFalse(result["feasible"])
        self.assertEqual(result["constraints_g_le_zero"], {})


class DuplicateTolerantOptimizerTests(unittest.TestCase):
    """A cached duplicate proposal must not abort the maml-opt search."""

    def _optimizer(self):
        from research.concorde_metaopt.optimization.baseline_bo import (
            _DuplicateTolerantOptimizer,
        )

        return _DuplicateTolerantOptimizer(
            lower_bounds=[0.0, 0.0],
            upper_bounds=[1.0, 1.0],
            seed=7,
        )

    @staticmethod
    def _result(objective=1.0):
        return {
            "status": "VALID",
            "valid": True,
            "objective": objective,
            "constraints_g_le_zero": {"g": -0.5},
            "objective_model_eligible": True,
            "analysis_calls": 1,
        }

    def test_duplicate_tell_is_ignored(self):
        optimizer = self._optimizer()
        optimizer.tell([0.5, 0.5], self._result())
        optimizer.tell([0.5, 0.5], self._result())
        self.assertEqual(optimizer.duplicates_ignored, 1)
        self.assertEqual(len(optimizer.observations), 1)

    def test_other_value_errors_still_propagate(self):
        optimizer = self._optimizer()
        with self.assertRaises(ValueError):
            optimizer.tell([2.0, 0.5], self._result())
        self.assertEqual(optimizer.duplicates_ignored, 0)


class BaselineBOFiguesRedrawTests(unittest.TestCase):
    def test_figures_are_redrawn_from_artifacts(self):
        from research.concorde_metaopt.reports.figures import plot_baseline_bo_artifacts

        run_dir = TMP_ROOT / "figures-redraw" / "run"
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_baseline_bo(
            output_root=TMP_ROOT / "figures-redraw",
            run_id="run",
            budget=6,
            seed=7,
            initial_design_count=3,
            design_space=load_design_space(),
            task=load_task_spec(),
            backend=ToyBackend(),
        )
        shutil.rmtree(run_dir / "figures")
        paths = plot_baseline_bo_artifacts(run_dir)
        self.assertIn("convergence", paths)
        self.assertIn("feasibility_rate", paths)
        for relative in paths.values():
            self.assertTrue((run_dir / relative).stat().st_size > 1000)


if __name__ == "__main__":
    unittest.main()
