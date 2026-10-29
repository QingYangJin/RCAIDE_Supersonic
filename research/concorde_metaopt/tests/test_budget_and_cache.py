"""P2 tests: budget accounting, caching, the JSONL contract and the offline smoke flow.

Every test uses a fake backend; no test in this module launches a RCAIDE Mission
or an SU2 run. The real-evidence run is executed once from the CLI and reviewed
separately.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research.concorde_metaopt.aircraft.design_space import load_design_space
from research.concorde_metaopt.evaluation.contract import CONSTRAINT_NAMES
from research.concorde_metaopt.evaluation.ledger import (
    BudgetExceeded,
    EvaluationLedger,
    canonical_design,
    design_id,
)
from research.concorde_metaopt.evaluation.low_fidelity import SingleCruiseBackend
from research.concorde_metaopt.evaluation.smoke import SmokeError, run_smoke
from research.concorde_metaopt.reports.figures import plot_smoke_artifacts
from research.concorde_metaopt.tasks.task_spec import load_task_spec

TMP_ROOT = Path(tempfile.mkdtemp(prefix="concorde-p2-tests-"))

REQUIRED_ROW_FIELDS = {
    "iteration",
    "design_id",
    "x",
    "status",
    "objective",
    "constraints",
    "feasible",
    "fidelity",
    "cache_hit",
    "physical_call_count",
    "wall_seconds",
    "cumulative_calls",
    "best_feasible_objective",
}

BASELINE_OBJECTIVE = 35700.0


class FakeBackend:
    """Deterministic offline backend used to exercise the ledger and smoke flow."""

    fidelity = "single_cruise"

    def __init__(
        self,
        status="VALID",
        raise_error=False,
        jitter=0.0,
        fail_perturbations=False,
        constraint_excess=0.0,
        objective_override=None,
        feasible_override=None,
        drop_constraints=False,
        fail_calls=(),
    ):
        self.status = status
        self.raise_error = raise_error
        self.jitter = jitter
        self.fail_perturbations = fail_perturbations
        self.constraint_excess = float(constraint_excess)
        self.objective_override = objective_override
        self.feasible_override = feasible_override
        self.drop_constraints = drop_constraints
        self.fail_calls = set(fail_calls)
        self.calls = 0
        self.tasks = []
        self.designs = []

    def preflight(self):
        return {"status": "PREFLIGHT_OK", "physical_call_count": 0}

    def evaluate(self, design, task=None, fidelity=None, purpose="search"):
        self.calls += 1
        self.tasks.append(task)
        self.designs.append(dict(design))
        if self.raise_error:
            raise RuntimeError("synthetic backend failure")
        status = self.status
        if self.calls in self.fail_calls:
            status = "MISSION_NOT_CONVERGED"
        if self.fail_perturbations and self._is_perturbed(design):
            status = "MISSION_NOT_CONVERGED"
        objective = None
        if self.objective_override is not None:
            objective = self.objective_override
        elif status == "VALID":
            objective = BASELINE_OBJECTIVE
            objective += 0.5 * (float(design["wing_area"]) - 358.25)
            objective += 30.0 * float(design["tip_twist"])
            if self.jitter:
                objective *= 1.0 + self.jitter * self.calls
        constraints = {} if self.drop_constraints else {name: -0.05 for name in CONSTRAINT_NAMES}
        if constraints:
            constraints["task_mass_balance"] = 0.0
            constraints["mission_convergence"] = 0.0
            constraints["cruise_range_error"] = self.constraint_excess
        feasible = status == "VALID" if self.feasible_override is None else bool(self.feasible_override)
        return {
            "status": status,
            "objective": objective,
            "constraints": constraints,
            "feasible": feasible,
            "fidelity": fidelity or self.fidelity,
            "diagnostics": [] if status == "VALID" else ["synthetic non-convergence"],
            "physical_call_count": 1,
        }

    @staticmethod
    def _is_perturbed(design):
        return (
            abs(float(design["wing_area"]) - 358.25) > 1.0e-9
            or abs(float(design["tip_twist"])) > 1.0e-9
        )


class LedgerTestBase(unittest.TestCase):
    def setUp(self):
        self.space = load_design_space()
        self.task = load_task_spec()
        self.run_dir = TMP_ROOT / ("ledger-" + self._testMethodName)
        if self.run_dir.exists():
            shutil.rmtree(self.run_dir)
        self.baseline = dict(self.space.baseline_dict())

    def _ledger(self, budget, cache_enabled=True):
        return EvaluationLedger(budget=budget, run_dir=self.run_dir, cache_enabled=cache_enabled)

    def _design(self, tip_twist=0.0):
        design = dict(self.baseline)
        design["tip_twist"] = tip_twist
        return design


class BudgetTests(LedgerTestBase):
    def test_budget_is_enforced(self):
        backend = FakeBackend()
        ledger = self._ledger(2)
        ledger.evaluate(backend, self._design(0.0), self.task)
        ledger.evaluate(backend, self._design(1.0), self.task)
        with self.assertRaises(BudgetExceeded):
            ledger.evaluate(backend, self._design(2.0), self.task)
        self.assertEqual(ledger.physical_calls, 2)
        self.assertEqual(ledger.remaining, 0)
        self.assertEqual(len(ledger.rows), 2)

    def test_zero_budget_rejects_first_call(self):
        ledger = self._ledger(0)
        with self.assertRaises(BudgetExceeded):
            ledger.evaluate(FakeBackend(), self.baseline, self.task)
        self.assertEqual(len(ledger.rows), 0)

    def test_rejected_call_does_not_write_a_row(self):
        ledger = self._ledger(1)
        backend = FakeBackend()
        ledger.evaluate(backend, self._design(0.0), self.task)
        before = (self.run_dir / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
        with self.assertRaises(BudgetExceeded):
            ledger.evaluate(backend, self._design(1.0), self.task)
        after = (self.run_dir / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(before, after)

    def test_negative_budget_rejected(self):
        with self.assertRaises(ValueError):
            self._ledger(-1)


class CacheTests(LedgerTestBase):
    def test_cache_hit_does_not_consume_budget(self):
        backend = FakeBackend()
        ledger = self._ledger(1)
        first = ledger.evaluate(backend, self.baseline, self.task)
        second = ledger.evaluate(backend, self.baseline, self.task)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["physical_call_count"], 0)
        self.assertEqual(second["cumulative_calls"], 1)
        self.assertEqual(second["objective"], first["objective"])
        self.assertEqual(backend.calls, 1)
        self.assertEqual(ledger.physical_calls, 1)
        self.assertEqual(ledger.summary()["cache_hits"], 1)

    def test_cache_disabled_forces_physical_calls(self):
        backend = FakeBackend()
        ledger = self._ledger(2, cache_enabled=False)
        ledger.evaluate(backend, self.baseline, self.task)
        second = ledger.evaluate(backend, self.baseline, self.task)
        self.assertFalse(second["cache_hit"])
        self.assertEqual(second["cumulative_calls"], 2)
        self.assertEqual(backend.calls, 2)

    def test_invalid_results_are_not_cached(self):
        backend = FakeBackend(status="MISSION_NOT_CONVERGED")
        ledger = self._ledger(2)
        first = ledger.evaluate(backend, self.baseline, self.task)
        second = ledger.evaluate(backend, self.baseline, self.task)
        self.assertEqual(first["status"], "MISSION_NOT_CONVERGED")
        self.assertIsNone(first["objective"])
        self.assertFalse(first["feasible"])
        self.assertFalse(second["cache_hit"])
        self.assertEqual(second["cumulative_calls"], 2)
        self.assertEqual(ledger.summary()["failed_count"], 2)

    def test_backend_exception_is_recorded_not_raised(self):
        backend = FakeBackend(raise_error=True)
        ledger = self._ledger(1)
        row = ledger.evaluate(backend, self.baseline, self.task)
        self.assertEqual(row["status"], "BACKEND_ERROR")
        self.assertIsNone(row["objective"])
        self.assertFalse(row["feasible"])
        self.assertEqual(ledger.summary()["failed_count"], 1)


class LedgerFailClosedTests(LedgerTestBase):
    """A backend cannot smuggle an objective/feasible value through a failed status."""

    def test_non_valid_result_cannot_carry_objective_or_feasible(self):
        backend = FakeBackend(status="MISSION_FAILED", objective_override=1.23, feasible_override=True)
        ledger = self._ledger(1)
        row = ledger.evaluate(backend, self.baseline, self.task)
        self.assertEqual(row["status"], "MISSION_FAILED")
        self.assertIsNone(row["objective"])
        self.assertFalse(row["feasible"])
        summary = ledger.summary()
        self.assertIsNone(summary["best_feasible_fuel_kg"])
        self.assertIsNone(summary["first_feasible_evaluation"])
        self.assertEqual(summary["failed_count"], 1)

    def test_valid_result_with_non_finite_objective_is_downgraded(self):
        backend = FakeBackend(objective_override=float("nan"))
        ledger = self._ledger(1)
        row = ledger.evaluate(backend, self.baseline, self.task)
        self.assertEqual(row["status"], "INVALID_OR_MISSING_RESPONSE")
        self.assertIsNone(row["objective"])
        self.assertFalse(row["feasible"])
        self.assertIsNone(ledger.summary()["best_feasible_fuel_kg"])
        lines = [
            line
            for line in (self.run_dir / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertIsNone(json.loads(lines[0])["objective"])

    def test_valid_result_without_constraints_is_downgraded(self):
        backend = FakeBackend(drop_constraints=True)
        ledger = self._ledger(1)
        row = ledger.evaluate(backend, self.baseline, self.task)
        self.assertEqual(row["status"], "INVALID_OR_MISSING_RESPONSE")
        self.assertIsNone(row["objective"])
        self.assertFalse(row["feasible"])

    def test_backend_receives_task_and_fidelity(self):
        backend = FakeBackend()
        ledger = self._ledger(1)
        ledger.evaluate(backend, self.baseline, self.task, fidelity="single_cruise")
        self.assertIs(backend.tasks[-1], self.task)


class TaskAwarenessTests(LedgerTestBase):
    def test_low_fidelity_rejects_foreign_task(self):
        backend = SingleCruiseBackend(self.space, self.task)
        other = dataclasses.replace(self.task, task_id=self.task.task_id + "-other")
        self.assertNotEqual(other.fingerprint(), self.task.fingerprint())
        with self.assertRaises(ValueError):
            backend.evaluate(self.baseline, task=other)


class JsonlContractTests(LedgerTestBase):
    def test_required_fields_are_present(self):
        ledger = self._ledger(1)
        ledger.evaluate(FakeBackend(), self.baseline, self.task)
        lines = [
            line
            for line in (self.run_dir / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertTrue(REQUIRED_ROW_FIELDS.issubset(row), REQUIRED_ROW_FIELDS - set(row))
        self.assertEqual(set(row["x"]), set(self.space.names))
        self.assertEqual(set(row["constraints"]), set(CONSTRAINT_NAMES))
        self.assertEqual(row["design_id"], design_id(self.baseline))
        self.assertEqual(row["fidelity"], "single_cruise")
        self.assertEqual(row["physical_call_count"], 1)
        self.assertEqual(row["cumulative_calls"], 1)

    def test_design_id_is_deterministic_and_order_independent(self):
        first = canonical_design({"wing_area": 358.25, "aspect_ratio": 1.83})
        second = canonical_design({"aspect_ratio": 1.83, "wing_area": 358.25})
        self.assertEqual(first, second)
        changed = canonical_design({"wing_area": 359.0, "aspect_ratio": 1.83})
        self.assertNotEqual(first, changed)
        identifier = design_id(self.baseline)
        self.assertTrue(identifier.startswith("d-"))
        self.assertEqual(identifier, design_id(dict(reversed(list(self.baseline.items())))))

    def test_best_and_first_feasible_are_tracked(self):
        backend = FakeBackend()
        ledger = self._ledger(3)
        higher = dict(self.baseline)
        higher["tip_twist"] = 2.0
        lower = dict(self.baseline)
        lower["tip_twist"] = -1.0
        ledger.evaluate(backend, higher, self.task)
        ledger.evaluate(backend, lower, self.task)
        ledger.evaluate(backend, self.baseline, self.task)
        summary = ledger.summary()
        expected_best = BASELINE_OBJECTIVE - 30.0 * 1.0
        self.assertAlmostEqual(summary["best_feasible_fuel_kg"], expected_best, places=6)
        self.assertEqual(summary["first_feasible_evaluation"], 1)
        self.assertEqual(summary["total_true_evaluations"], 3)


class SmokeWorkflowTests(LedgerTestBase):
    def _run(self, run_id, backend, budget=5, allow_existing=False):
        return run_smoke(
            output_root=TMP_ROOT / ("smoke-runs-" + self._testMethodName),
            run_id=run_id,
            budget=budget,
            design_space=self.space,
            task=self.task,
            backend=backend,
            allow_existing=allow_existing,
        )

    def test_offline_smoke_happy_path(self):
        backend = FakeBackend()
        summary = self._run("offline-ok", backend)
        run_dir = TMP_ROOT / ("smoke-runs-" + self._testMethodName) / "offline-ok"
        self.assertEqual(summary["status"], "smoke_completed")
        self.assertEqual(summary["total_true_evaluations"], 5)
        self.assertEqual(backend.calls, 5)
        self.assertEqual(summary["smoke"]["budget"], 5)
        self.assertTrue(summary["smoke"]["repeatability"]["passed"])
        self.assertEqual(summary["smoke"]["repeatability"]["count"], 3)
        self.assertAlmostEqual(summary["best_feasible_fuel_kg"], BASELINE_OBJECTIVE, places=6)
        for name in (
            "summary.json",
            "run_config.json",
            "environment.json",
            "best_design.json",
            "evaluations.jsonl",
            "evaluations_detail.jsonl",
            "smoke_cases.csv",
            "README.md",
            "task_spec.json",
        ):
            self.assertTrue((run_dir / name).exists(), name)
        self.assertTrue((run_dir / "figures" / "repeatability.png").stat().st_size > 1000)
        self.assertTrue((run_dir / "figures" / "perturbation_sensitivity.png").stat().st_size > 1000)
        evaluations = [
            line
            for line in (run_dir / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(len(evaluations), 5)
        detail = [
            line
            for line in (run_dir / "evaluations_detail.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(len(detail), 5)
        self.assertIn("responses", json.loads(detail[0]))
        header = (run_dir / "smoke_cases.csv").read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("max_throttle", header)
        self.assertIn("violated_constraints", header)
        self.assertIn("geometry_cross_check_failed", header)
        run_config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
        self.assertEqual(run_config["task_fingerprint"], self.task.fingerprint())
        self.assertEqual(summary["smoke"]["perturbations"][0]["max_throttle"], -0.05)
        self.assertEqual(len(summary["smoke"]["perturbations"]), 2)
        self.assertTrue(all(case["status"] == "VALID" for case in summary["smoke"]["perturbations"]))
        index = json.loads(
            (TMP_ROOT / ("smoke-runs-" + self._testMethodName) / "index.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual([entry["run_id"] for entry in index["runs"]], ["offline-ok"])
        entry = index["runs"][0]
        self.assertEqual(entry["path"], "offline-ok")
        self.assertEqual(entry["status"], "smoke_completed")
        self.assertIn("created_at", entry)
        self.assertIn("P2 single-cruise smoke", entry["summary"])
        self.assertIn("baseline objective", entry["summary"])
        self.assertEqual(
            run_config["design_space"]["config_path"],
            "research/concorde_metaopt/configs/design_space_15d.yaml",
        )

    def test_absolute_config_paths_in_preflight_are_sanitized(self):
        class NestedConfigBackend(FakeBackend):
            def preflight(self):
                data = super().preflight()
                repo_root = Path(__file__).resolve().parents[3]
                data["design_space_config"] = {
                    "task_id": "concorde_fixed_cruise_15d",
                    "config_path": str(
                        repo_root
                        / "research"
                        / "concorde_metaopt"
                        / "configs"
                        / "design_space_15d.yaml"
                    ),
                }
                return data

        summary = self._run("offline-sanitize", NestedConfigBackend())
        preflight = summary["smoke"]["preflight"]["design_space_config"]
        self.assertEqual(
            preflight["config_path"],
            "research/concorde_metaopt/configs/design_space_15d.yaml",
        )
        run_dir = TMP_ROOT / ("smoke-runs-" + self._testMethodName) / "offline-sanitize"
        run_config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
        self.assertEqual(
            run_config["design_space"]["config_path"],
            "research/concorde_metaopt/configs/design_space_15d.yaml",
        )

    def test_repeatability_failure_is_reported(self):
        summary = self._run("offline-repeat-fail", FakeBackend(jitter=1.0e-3))
        self.assertEqual(summary["status"], "smoke_repeatability_failed")
        self.assertFalse(summary["smoke"]["repeatability"]["passed"])
        self.assertGreater(summary["smoke"]["repeatability"]["relative_spread"], 1.0e-6)

    def test_case_failure_is_reported(self):
        summary = self._run("offline-case-fail", FakeBackend(fail_perturbations=True))
        self.assertEqual(summary["status"], "smoke_completed_with_failures")
        statuses = [case["status"] for case in summary["smoke"]["perturbations"]]
        self.assertTrue(all(status != "VALID" for status in statuses), statuses)
        self.assertEqual(summary["smoke"]["baseline"]["status"], "VALID")
        # The baseline repeats are feasible, so a best point still exists even
        # though both perturbation cases failed.
        self.assertAlmostEqual(summary["best_feasible_fuel_kg"], BASELINE_OBJECTIVE, places=6)

    def test_partial_repeat_is_not_reported_as_passed(self):
        summary = self._run("offline-partial-repeat", FakeBackend(fail_calls=(3,)))
        repeat = summary["smoke"]["repeatability"]
        self.assertFalse(repeat["passed"])
        self.assertEqual(repeat["rows_recorded"], 3)
        self.assertEqual(repeat["valid_rows"], 2)
        self.assertEqual(repeat["required_rows"], 3)
        self.assertIn("expected 3 VALID baseline repeats", repeat["reason"])
        self.assertEqual(summary["status"], "smoke_repeatability_failed")

    def test_constraint_gate_separates_round_off_from_strict_feasibility(self):
        summary = self._run("offline-roundoff", FakeBackend(constraint_excess=2.0e-15))
        constraints = summary["constraints"]
        self.assertFalse(constraints["all_g_le_zero"])
        self.assertTrue(constraints["all_g_le_zero_within_tolerance"])
        self.assertGreater(constraints["max_constraint_excess"], 0.0)
        self.assertEqual(constraints["rows_checked"], 5)
        offenders = constraints["positive_constraint_offenders"]
        self.assertTrue(any(item["constraint"] == "cruise_range_error" for item in offenders), offenders)

    def test_happy_path_constraint_gate_is_strictly_clean(self):
        summary = self._run("offline-gate-clean", FakeBackend())
        constraints = summary["constraints"]
        self.assertTrue(constraints["all_g_le_zero"])
        self.assertTrue(constraints["all_g_le_zero_within_tolerance"])
        self.assertEqual(constraints["max_constraint_excess"], 0.0)
        self.assertEqual(constraints["rows_checked"], 5)
        self.assertEqual(constraints["positive_constraint_offenders"], [])
        self.assertEqual(constraints["missing_constraint_entries"], [])

    def test_budget_below_minimum_is_rejected(self):
        with self.assertRaises(SmokeError):
            self._run("offline-low-budget", FakeBackend(), budget=4)

    def test_existing_run_directory_requires_allow_existing(self):
        self._run("offline-existing", FakeBackend())
        with self.assertRaises(FileExistsError):
            self._run("offline-existing", FakeBackend())

    def test_figures_are_redrawn_from_artifacts(self):
        self._run("offline-redraw", FakeBackend())
        run_dir = TMP_ROOT / ("smoke-runs-" + self._testMethodName) / "offline-redraw"
        shutil.rmtree(run_dir / "figures")
        paths = plot_smoke_artifacts(run_dir)
        self.assertIn("repeatability", paths)
        self.assertIn("perturbation_sensitivity", paths)
        for path in paths.values():
            self.assertTrue((run_dir / path).stat().st_size > 1000)


class ReadmeMassContractTests(unittest.TestCase):
    def test_nested_contract_renders_measured_masses(self):
        from research.concorde_metaopt.evaluation.smoke import _mass_contract_line

        line = _mass_contract_line(
            {
                "applied": {
                    "operating_empty": 78700.0,
                    "payload": 9500.0,
                    "cargo": 1000.0,
                    "fuel": 46800.0,
                    "takeoff": 136000.0,
                },
                "readback": {
                    "operating_empty": 78700.0,
                    "payload": 9500.0,
                    "cargo": 1000.0,
                    "fuel": 46800.0,
                    "takeoff": 136000.0,
                },
            }
        )
        self.assertIn("start 136000 kg", line)
        self.assertIn("loaded fuel 46800 kg", line)
        self.assertIn("ZFW 89200 kg", line)
        self.assertNotIn("unknown", line)
        self.assertNotIn("readback", line)

    def test_flat_contract_is_still_accepted(self):
        from research.concorde_metaopt.evaluation.smoke import _mass_contract_line

        line = _mass_contract_line(
            {
                "start_mass_kg": 136000.0,
                "fuel_loaded_kg": 46800.0,
                "zero_fuel_mass_kg": 89200.0,
            }
        )
        self.assertIn("start 136000 kg", line)
        self.assertIn("loaded fuel 46800 kg", line)
        self.assertIn("ZFW 89200 kg", line)

    def test_readback_mismatch_is_disclosed(self):
        from research.concorde_metaopt.evaluation.smoke import _mass_contract_line

        line = _mass_contract_line(
            {
                "applied": {"operating_empty": 78700.0, "payload": 9500.0, "cargo": 1000.0, "fuel": 46800.0, "takeoff": 136000.0},
                "readback": {"fuel": 46000.0},
            }
        )
        self.assertIn("readback fuel 46000 kg", line)

    def test_missing_contract_is_explicit(self):
        from research.concorde_metaopt.evaluation.smoke import _mass_contract_line

        self.assertIn("not recorded", _mass_contract_line(None))


if __name__ == "__main__":
    unittest.main()
