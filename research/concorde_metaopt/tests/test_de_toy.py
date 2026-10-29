"""P4 tests: the differential-evolution baseline on a toy evaluator.

No RCAIDE Mission and no SU2 run happens here. A deterministic synthetic
backend exercises the DE search mechanics, the shared budget ledger and every
P4 artefact, so a real small-budget DE run can be authorised separately.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research.concorde_metaopt.aircraft.design_space import load_design_space
from research.concorde_metaopt.evaluation.contract import CONSTRAINT_NAMES
from research.concorde_metaopt.optimization.baseline_de import (
    BaselineError,
    run_baseline_de,
)
from research.concorde_metaopt.tasks.task_spec import load_task_spec

TMP_ROOT = Path(tempfile.mkdtemp(prefix="concorde-p4-de-tests-"))

BASELINE_OBJECTIVE = 34135.4


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

    def __init__(self, impossible=False):
        self.impossible = impossible
        self.calls = 0
        self.tasks = []

    def preflight(self):
        return {"status": "PREFLIGHT_OK", "physical_call_count": 0, "fidelity": self.fidelity}

    def evaluate(self, design, task=None, fidelity=None, purpose="search"):
        self.calls += 1
        self.tasks.append(task)
        u = unit_coordinates(design)
        objective = BASELINE_OBJECTIVE + 1000.0 * (
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


class BaselineDETests(unittest.TestCase):
    def setUp(self):
        self.space = load_design_space()
        self.task = load_task_spec()
        self.output_root = TMP_ROOT / self._testMethodName
        if self.output_root.exists():
            shutil.rmtree(self.output_root)

    def _run(self, run_id="toy-de", backend=None, budget=12, population_size=6, **kwargs):
        return run_baseline_de(
            output_root=self.output_root,
            run_id=run_id,
            budget=budget,
            seed=42,
            population_size=population_size,
            design_space=self.space,
            task=self.task,
            backend=backend if backend is not None else ToyBackend(),
            **kwargs
        )

    def test_toy_de_stays_within_budget_and_improves(self):
        backend = ToyBackend()
        summary = self._run(backend=backend)
        self.assertEqual(summary["status"], "baseline_de_completed")
        self.assertEqual(summary["method"], "ordinary_differential_evolution")
        self.assertEqual(summary["algorithm"], "de")
        self.assertEqual(summary["stage"], "P4")
        self.assertEqual(summary["total_true_evaluations"], 12)
        self.assertEqual(backend.calls, 12)
        self.assertIs(backend.tasks[0], self.task)
        de = summary["baseline_de"]
        self.assertGreaterEqual(de["feasible_evaluations"], 1)
        self.assertEqual(de["ledger"]["budget"], 12)
        self.assertEqual(de["ledger"]["budget_remaining"], 0)
        self.assertIsNotNone(summary["best_feasible_fuel_kg"])
        self.assertIsNotNone(summary["best_design_id"])
        self.assertLessEqual(summary["best_feasible_fuel_kg"], BASELINE_OBJECTIVE)
        self.assertGreater(de["improvement_kg"], 0.0)

    def test_first_evaluation_is_the_baseline_design(self):
        run_id = "toy-de-baseline-first"
        self._run(run_id=run_id)
        run_dir = self.output_root / run_id
        trace = [
            json.loads(line)
            for line in (run_dir / "opt_trace.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(trace[0]["selection_method"], "lhs_initial")
        self.assertTrue(trace[0]["phase"] in ("initialisation", "initialization"))
        baseline = self.space.baseline_dict()
        for name, value in trace[0]["design"].items():
            self.assertAlmostEqual(value, baseline[name], places=12)
        evaluations = [
            json.loads(line)
            for line in (run_dir / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        for name, value in evaluations[0]["x"].items():
            self.assertAlmostEqual(value, baseline[name], places=12)

    def test_artifacts_and_trace_are_written(self):
        summary = self._run(run_id="toy-de-artifacts")
        run_dir = self.output_root / "toy-de-artifacts"
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
        self.assertEqual(best["algorithm"], "de")
        index = json.loads((self.output_root / "index.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["run_id"] for entry in index["runs"]], ["toy-de-artifacts"])
        self.assertEqual(index["runs"][0]["status"], "completed")
        manifest = json.loads((run_dir / "data_manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["files"])
        self.assertTrue(all("sha256" in entry for entry in manifest["files"]))

    def test_same_seed_is_deterministic(self):
        first = self._run(run_id="toy-de-seed-a")
        second = self._run(run_id="toy-de-seed-b")
        self.assertEqual(first["best_feasible_fuel_kg"], second["best_feasible_fuel_kg"])
        self.assertEqual(first["best_design_id"], second["best_design_id"])
        trace_a = [
            json.loads(line)
            for line in (self.output_root / "toy-de-seed-a" / "opt_trace.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        trace_b = [
            json.loads(line)
            for line in (self.output_root / "toy-de-seed-b" / "opt_trace.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        self.assertEqual(
            [row["objective"] for row in trace_a],
            [row["objective"] for row in trace_b],
        )
        self.assertEqual(
            [row["design"] for row in trace_a],
            [row["design"] for row in trace_b],
        )

    def test_no_feasible_solution_is_reported_without_a_fake_objective(self):
        summary = self._run(run_id="toy-de-infeasible", backend=ToyBackend(impossible=True))
        self.assertEqual(summary["status"], "baseline_de_no_feasible_solution")
        self.assertIsNone(summary["best_feasible_fuel_kg"])
        self.assertIsNone(summary["best_design_id"])
        self.assertEqual(summary["baseline_de"]["feasible_evaluations"], 0)
        self.assertGreaterEqual(summary["baseline_de"]["valid_evaluations"], 1)
        best = json.loads(
            (self.output_root / "toy-de-infeasible" / "best_design.json").read_text(encoding="utf-8")
        )
        self.assertFalse(best["feasible"])
        self.assertIsNone(best["best_feasible_objective"])

    def test_budget_and_population_validation(self):
        with self.assertRaises(BaselineError):
            self._run(budget=3)
        with self.assertRaises(BaselineError):
            self._run(budget=12, population_size=3)
        with self.assertRaises(BaselineError):
            self._run(budget=12, population_size=13)
        with self.assertRaises(BaselineError):
            self._run(budget=12, mutation_factor=0.0)
        with self.assertRaises(BaselineError):
            self._run(budget=12, crossover_rate=1.5)

    def test_existing_run_directory_requires_allow_existing(self):
        self._run(run_id="toy-de-existing", budget=8, population_size=4)
        with self.assertRaises(FileExistsError):
            self._run(run_id="toy-de-existing", budget=8, population_size=4)
        summary = self._run(
            run_id="toy-de-existing", budget=8, population_size=4, allow_existing=True
        )
        self.assertEqual(summary["total_true_evaluations"], 8)


class BaselineDEFiguresRedrawTests(unittest.TestCase):
    def test_figures_are_redrawn_from_artifacts(self):
        from research.concorde_metaopt.reports.figures import plot_optimizer_trace_artifacts

        run_dir = TMP_ROOT / "de-figures-redraw" / "run"
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_baseline_de(
            output_root=TMP_ROOT / "de-figures-redraw",
            run_id="run",
            budget=8,
            seed=7,
            population_size=4,
            design_space=load_design_space(),
            task=load_task_spec(),
            backend=ToyBackend(),
        )
        shutil.rmtree(run_dir / "figures")
        paths = plot_optimizer_trace_artifacts(run_dir)
        self.assertIn("convergence", paths)
        self.assertIn("feasibility_rate", paths)
        for relative in paths.values():
            self.assertTrue((run_dir / relative).stat().st_size > 1000)

    def test_cli_accepts_algorithm_de(self):
        from research.concorde_metaopt.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "baseline",
                "--algorithm",
                "de",
                "--budget",
                "12",
                "--population-size",
                "6",
                "--mutation-factor",
                "0.6",
                "--crossover-rate",
                "0.8",
            ]
        )
        self.assertEqual(args.algorithm, "de")
        self.assertEqual(args.budget, 12)
        self.assertEqual(args.population_size, 6)
        self.assertAlmostEqual(args.mutation_factor, 0.6)
        self.assertAlmostEqual(args.crossover_rate, 0.8)


if __name__ == "__main__":
    unittest.main()
