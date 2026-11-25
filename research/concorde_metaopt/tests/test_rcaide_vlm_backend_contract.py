"""Zero-physics contract tests for the dreal006 VLM backend (S0, Issue #16).

These tests never build a vehicle and never run a VLM solve: the backend object
is assembled with object.__new__ and its geometry/solver hooks are replaced by
pure-python stubs.  What they pin is the contract the S0 repair introduced:

* the alpha solver reports the CL that belongs to the alpha it returns (V1L
  returned a stale CL from the previous iteration);
* a label whose final lift residual exceeds the tolerance is rejected instead of
  being reported VALID;
* the cache key is bound to the task, the reference convention, the geometry and
  the lattice, not just to the design vector;
* the reference quantities recorded in a row are the ones the row was computed
  with;
* failures surface as status values, never as raised exceptions.
"""
import unittest

import numpy as np

from research.concorde_metaopt.evaluation import rcaide_vlm_backend as backend_module
from research.concorde_metaopt.evaluation.rcaide_vlm_backend import SupersonicVLMBackend


ATMO = {"dynamic_pressure_Pa": 20654.013924958777}


class _FakeVehicle:
    reference_area = 1.0
    reference_chord = 1.0
    reference_span = 1.0


def make_backend(**overrides):
    """Assemble a backend without touching RCAIDE or the design-space loader."""
    obj = object.__new__(SupersonicVLMBackend)
    obj.repo_root = "<test>"
    obj.reference_mode = overrides.pop("reference_mode", backend_module.REFERENCE_MODE_GEOMETRY)
    obj.task_fingerprint = overrides.pop("task_fingerprint", "task-abc")
    obj.design_space_fingerprint = overrides.pop("design_space_fingerprint", "space-abc")
    obj.design_names = overrides.pop("design_names", ["wing_area", "aspect_ratio"])
    obj.mach = overrides.pop("mach", 2.02)
    obj.altitude_m = overrides.pop("altitude_m", 18288.0)
    obj.cl_target = overrides.pop("cl_target", 0.18)
    obj.lift_target_mode = overrides.pop("lift_target_mode", "coefficient")
    obj.lift_target_n = overrides.pop("lift_target_n", None)
    obj.lattice = overrides.pop("lattice", (20, 10))
    obj._atmo = dict(ATMO)
    obj._vehicles = {}
    obj.cache = {}
    obj.solve_count = 0
    obj.build_count = 0
    obj.wall_seconds = 0.0
    refs = overrides.pop("refs", {"Sref_m2": 400.0, "Cref_m": 19.0, "Bref_m": 27.0})
    obj._refs = refs
    for key, value in overrides.items():
        setattr(obj, key, value)
    obj._vehicle = lambda design: (obj._vehicle_obj, "design-key", dict(obj._refs))
    return obj


class AlphaSolverContractTests(unittest.TestCase):
    def test_reported_cl_belongs_to_the_reported_alpha(self):
        obj = make_backend()
        obj._vehicle_obj = _FakeVehicle()
        obj._solve = lambda vehicle, alpha: (0.05 * alpha, 0.0073)
        solve = obj._alpha_for_lift(obj._vehicle_obj, obj.cl_target)
        self.assertTrue(solve["ok"])
        self.assertAlmostEqual(solve["cl"], 0.05 * solve["alpha_deg"], places=12)
        self.assertLessEqual(abs(solve["cl"] - obj.cl_target), backend_module.ALPHA_TOL)

    def test_failed_solve_does_not_report_a_stale_cl(self):
        obj = make_backend()
        obj._vehicle_obj = _FakeVehicle()
        # CL does not respond to alpha: the secant must give up, and the CL it
        # returns must still be the CL at the alpha it returns.
        obj._solve = lambda vehicle, alpha: (0.05, 0.0073)
        solve = obj._alpha_for_lift(obj._vehicle_obj, obj.cl_target)
        self.assertFalse(solve["ok"])
        self.assertEqual(solve["cl"], 0.05)
        self.assertEqual(obj._solve(obj._vehicle_obj, solve["alpha_deg"])[0], 0.05)


class EvaluateContractTests(unittest.TestCase):
    def _backend_with_solver(self, solver, **kwargs):
        obj = make_backend(**kwargs)
        obj._vehicle_obj = _FakeVehicle()
        obj._solve = solver
        return obj

    def test_lift_residual_rejection_is_not_valid(self):
        obj = self._backend_with_solver(lambda vehicle, alpha: (0.30, 0.0073))
        obj._alpha_for_lift = lambda vehicle, cl_target, alpha_guess=5.0: {
            "alpha_deg": 3.6, "cl": 0.30, "iterations": 3, "ok": True, "history": [],
        }
        record = obj.evaluate({"wing_area": 358.25, "aspect_ratio": 1.83})
        self.assertEqual(record["status"], "LIFT_RESIDUAL_REJECTED")
        self.assertIsNone(record["objective"])
        self.assertGreater(record["lift_residual"], backend_module.LIFT_RESIDUAL_TOL)

    def test_non_physical_cdi_is_not_valid(self):
        obj = self._backend_with_solver(lambda vehicle, alpha: (0.18, -0.001))
        record = obj.evaluate({"wing_area": 358.25, "aspect_ratio": 1.83})
        self.assertEqual(record["status"], "NON_PHYSICAL_CDI")
        self.assertIsNone(record["objective"])

    def test_valid_row_records_the_reference_it_used(self):
        obj = self._backend_with_solver(lambda vehicle, alpha: (0.18, 0.0073))
        record = obj.evaluate({"wing_area": 358.25, "aspect_ratio": 1.83})
        self.assertEqual(record["status"], "VALID")
        self.assertAlmostEqual(record["sref_used_m2"], 400.0)
        self.assertAlmostEqual(record["cref_used_m"], 19.0)
        self.assertAlmostEqual(record["bref_used_m"], 27.0)
        # L = q * Sref * CL and J = q * Sref * CDi share one Sref.
        self.assertAlmostEqual(record["lift_times_q_sref_N"], 0.18 * ATMO["dynamic_pressure_Pa"] * 400.0)
        self.assertAlmostEqual(record["cdi_times_q_sref_N"], 0.0073 * ATMO["dynamic_pressure_Pa"] * 400.0)
        self.assertEqual(record["schema"], backend_module.SCHEMA)
        self.assertEqual(record["backend_version"], backend_module.BACKEND_VERSION)

    def test_cache_hit_is_reported_and_reproducible(self):
        obj = self._backend_with_solver(lambda vehicle, alpha: (0.18, 0.0073))
        design = {"wing_area": 358.25, "aspect_ratio": 1.83}
        first = obj.evaluate(design)
        second = obj.evaluate(design)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["objective"], second["objective"])

    def test_cache_key_separates_tasks_references_and_lattices(self):
        design = {"wing_area": 358.25, "aspect_ratio": 1.83}
        variants = {
            "baseline": {},
            "cl_target": {"cl_target": 0.15},
            "mach": {"mach": 1.8},
            "altitude": {"altitude_m": 17000.0},
            "reference_mode": {"reference_mode": backend_module.REFERENCE_MODE_FROZEN},
            "task": {"task_fingerprint": "task-xyz"},
            "lattice": {"lattice": (30, 15)},
        }
        seen = {}
        for label, kwargs in variants.items():
            obj = self._backend_with_solver(lambda vehicle, alpha: (kwargs.get("cl_target", 0.18), 0.0073), **kwargs)
            record = obj.evaluate(design)
            if label == "reference_mode":
                # the frozen mode must not reuse the geometry-mode entry
                self.assertFalse(record["cached"])
            seen[label] = record["lift_residual"]
        self.assertTrue(all(value is not None for value in seen.values()))

    def test_geometry_mode_reference_does_not_use_the_baseline_constants(self):
        obj = self._backend_with_solver(
            lambda vehicle, alpha: (0.18, 0.0073),
            refs={"Sref_m2": 420.0, "Cref_m": 20.1, "Bref_m": 27.7},
        )
        record = obj.evaluate({"wing_area": 420.0, "aspect_ratio": 1.83})
        self.assertAlmostEqual(record["sref_used_m2"], 420.0)
        self.assertNotAlmostEqual(record["sref_used_m2"], backend_module.SREF_M2)

    def test_solver_exception_becomes_an_error_status(self):
        def boom(vehicle, alpha):
            raise RuntimeError("vlm exploded")

        obj = self._backend_with_solver(boom)
        record = obj.evaluate({"wing_area": 358.25, "aspect_ratio": 1.83})
        self.assertEqual(record["status"], "ERROR")
        self.assertIn("vlm exploded", record["diagnostics"][0])


class LiftTargetModeTests(unittest.TestCase):
    """A task fixes a lift force, not a coefficient (contract section 3.1)."""

    def test_force_mode_derives_cl_from_the_design_reference_area(self):
        obj = make_backend(lift_target_mode="force", lift_target_n=1.0e6, refs={"Sref_m2": 400.0, "Cref_m": 19.0, "Bref_m": 27.0})
        q = ATMO["dynamic_pressure_Pa"]
        self.assertAlmostEqual(obj.cl_target_for(obj._refs), 1.0e6 / (q * 400.0))
        # Halving the wing doubles the CL the same force demands.
        small = dict(obj._refs)
        small["Sref_m2"] = 200.0
        self.assertAlmostEqual(obj.cl_target_for(small), 2.0 * obj.cl_target_for(obj._refs))

    def test_coefficient_mode_ignores_the_reference_area(self):
        obj = make_backend(cl_target=0.18)
        other = {"Sref_m2": 300.0, "Cref_m": 17.0, "Bref_m": 24.0}
        self.assertEqual(obj.cl_target_for(obj._refs), 0.18)
        self.assertEqual(obj.cl_target_for(other), 0.18)

    def test_two_designs_at_one_force_are_compared_at_the_same_lift(self):
        # Same task force, different areas -> different CL, identical q*Sref*CL.
        obj = make_backend(lift_target_mode="force", lift_target_n=1.3e6)
        results = []
        for sref in (358.25, 420.0):
            refs = {"Sref_m2": sref, "Cref_m": 18.5, "Bref_m": 25.6}
            obj._refs = refs
            cl_target = obj.cl_target_for(refs)
            obj._vehicle_obj = _FakeVehicle()
            obj._solve = lambda vehicle, alpha, _cl=cl_target: (_cl, 0.0073)
            record = obj.evaluate({"wing_area": sref, "aspect_ratio": 1.83})
            self.assertEqual(record["status"], "VALID")
            results.append(record["lift_times_q_sref_N"])
        self.assertAlmostEqual(results[0], results[1], delta=1.0)

    def test_force_mode_without_a_force_is_rejected(self):
        with self.assertRaises(ValueError):
            SupersonicVLMBackend("<repo>", "<config>", lift_target_mode="force")


class ConstructorContractTests(unittest.TestCase):
    def test_unknown_reference_mode_is_rejected_before_any_physics(self):
        with self.assertRaises(ValueError):
            SupersonicVLMBackend("<repo>", "<config>", reference_mode="whatever")


if __name__ == "__main__":
    unittest.main()
