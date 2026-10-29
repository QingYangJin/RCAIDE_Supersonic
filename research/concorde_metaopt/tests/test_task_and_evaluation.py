"""P2 tests: frozen task contract, constraint math, mission assembly and observations.

No test in this module launches a Mission evaluation or a CFD run. Mission
assembly uses a stub analysis container; observation extraction uses a synthetic
conditions tree so the fail-closed rules can be exercised cheaply.
"""

from __future__ import annotations

import copy
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from research.concorde_metaopt.config_io import load_config
from research.concorde_metaopt.evaluation import contract
from research.concorde_metaopt.evaluation.contract import (
    CONSTRAINT_NAMES,
    STATUS_VALID,
    empty_constraints,
    evaluate_constraints,
    feasibility,
    violated_constraints,
)
from research.concorde_metaopt.evaluation.mission import (
    MissionBuildError,
    ObservationError,
    build_single_cruise_mission,
    extract_observations,
)
from research.concorde_metaopt.tasks.task_spec import (
    FixedCruiseTask,
    TaskSpecError,
    load_task_spec,
)

TASK_PATH = Path(__file__).resolve().parent.parent / "configs" / "task_fixed_cruise.yaml"

BASELINE_MASS_START = 145000.0
BASELINE_BURN = 35700.0
BASELINE_RANGE = 3028020.0


def baseline_observations(**overrides):
    observations = {
        "objective_name": "fuel_burn_kg",
        "objective_unit": "kg",
        "mass_start_kg": BASELINE_MASS_START,
        "mass_end_kg": BASELINE_MASS_START - BASELINE_BURN,
        "fuel_burn_kg": BASELINE_BURN,
        "range_start_m": 0.0,
        "range_end_m": BASELINE_RANGE,
        "range_span_m": BASELINE_RANGE,
        "time_start_s": 0.0,
        "time_end_s": 5080.0,
        "time_span_s": 5080.0,
        "max_throttle": 0.9642,
        "max_fuel_mass_flow_kg_s": 2.0,
        "max_thrust_x_n": 43000.0,
        "alpha_end_deg": 1.0,
        "lift_coefficient_end": 0.1,
        "drag_coefficient_end": 0.02,
        "converged": True,
        "solver_converged": True,
        "residual_max": 1.0e-14,
        "propulsors": {},
        "history_samples": 5,
        "residual_limit": contract.RESIDUAL_LIMIT,
    }
    observations.update(overrides)
    return observations


def synthetic_segment(*, mass=None, range_history=None, time_history=None, throttle=None, missing_propulsor=False):
    mass = np.asarray(mass if mass is not None else [145000.0, 109300.0], dtype=float)
    range_history = np.asarray(
        range_history if range_history is not None else [0.0, BASELINE_RANGE], dtype=float
    )
    time_history = np.asarray(time_history if time_history is not None else [0.0, 5080.0], dtype=float)
    throttle = np.asarray(throttle if throttle is not None else [0.9642, 0.9642], dtype=float)
    flow = np.asarray([2.0, 1.9], dtype=float)
    thrust = np.asarray([[43000.0, 0.0, 0.0], [42000.0, 0.0, 0.0]], dtype=float)
    propulsor = SimpleNamespace(
        throttle=throttle,
        fuel_mass_flow_rate=flow,
        thrust=thrust,
    )
    propulsors = {} if missing_propulsor else {
        "inner_right_turbojet": propulsor,
        "outer_right_turbojet": propulsor,
        "outer_left_turbojet": propulsor,
        "inner_left_turbojet": propulsor,
    }
    conditions = SimpleNamespace(
        weights=SimpleNamespace(vehicle=SimpleNamespace(mass=mass)),
        frames=SimpleNamespace(inertial=SimpleNamespace(aircraft_range=range_history, time=time_history)),
        energy=SimpleNamespace(propulsors=propulsors),
        aerodynamics=SimpleNamespace(
            angles=SimpleNamespace(alpha=np.asarray([[0.05], [0.04]], dtype=float)),
            coefficients=SimpleNamespace(
                lift=SimpleNamespace(total=np.asarray([[0.12], [0.10]], dtype=float)),
                drag=SimpleNamespace(total=np.asarray([[0.03], [0.02]], dtype=float)),
            ),
        ),
    )
    residuals = SimpleNamespace(pack_array=lambda: np.asarray([[1.0e-14, 2.0e-14]], dtype=float))
    state = SimpleNamespace(
        conditions=conditions,
        residuals=residuals,
        numerics=SimpleNamespace(solver=SimpleNamespace(converged=True)),
    )
    return SimpleNamespace(state=state, converged=True)


class TaskSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = load_task_spec()
        cls.config = load_config(TASK_PATH)

    def test_frozen_contract_values(self):
        task = self.task
        self.assertEqual(task.task_id, "concorde-fixed-cruise-p2-v1")
        self.assertAlmostEqual(task.cruise_altitude_m, 18288.0, places=9)
        self.assertAlmostEqual(task.cruise_mach, 2.02, places=12)
        self.assertAlmostEqual(task.cruise_distance_m, 3028020.0, places=6)
        self.assertAlmostEqual(task.operating_empty_kg, 78700.0, places=9)
        self.assertAlmostEqual(task.payload_kg, 9500.0, places=9)
        self.assertAlmostEqual(task.cargo_kg, 1000.0, places=9)
        self.assertAlmostEqual(task.fuel_loaded_kg, 55800.0, places=9)
        self.assertAlmostEqual(task.start_mass_kg, 145000.0, places=9)
        self.assertAlmostEqual(task.zero_fuel_mass_kg, 89200.0, places=9)
        self.assertAlmostEqual(task.fuel_margin_kg, 95680.0 - 55800.0, places=9)
        self.assertAlmostEqual(task.zero_fuel_margin_kg, 92000.0 - 89200.0, places=9)
        self.assertAlmostEqual(task.takeoff_margin_kg, 185000.0 - 145000.0, places=9)
        self.assertEqual(task.objective_name, "fuel_burn_kg")
        self.assertEqual(task.objective_unit, "kg")
        self.assertEqual(len(task.propulsor_tags), 4)

    def test_fingerprint_is_stable_and_contract_specific(self):
        self.assertEqual(self.task.fingerprint(), load_task_spec().fingerprint())
        config = copy.deepcopy(self.config)
        config["masses"]["payload_kg"] = 9000.0
        config["masses"]["start_mass_kg"] = 144500.0
        changed = FixedCruiseTask.from_config(config)
        self.assertNotEqual(self.task.fingerprint(), changed.fingerprint())

    def test_mass_balance_violation_rejected(self):
        config = copy.deepcopy(self.config)
        config["masses"]["start_mass_kg"] = 140000.0
        with self.assertRaises(TaskSpecError):
            FixedCruiseTask.from_config(config)

    def test_unfrozen_contract_rejected(self):
        config = copy.deepcopy(self.config)
        config["mass_contract"]["status"] = "provisional"
        with self.assertRaises(TaskSpecError):
            FixedCruiseTask.from_config(config)

    def test_objective_name_cannot_change(self):
        config = copy.deepcopy(self.config)
        config["objective"]["name"] = "fuel_mass"
        with self.assertRaises(TaskSpecError):
            FixedCruiseTask.from_config(config)

    def test_missing_freeze_evidence_rejected(self):
        config = copy.deepcopy(self.config)
        config["mass_contract"]["evidence"] = ""
        with self.assertRaises(TaskSpecError):
            FixedCruiseTask.from_config(config)

    def test_out_of_range_mach_rejected(self):
        config = copy.deepcopy(self.config)
        config["cruise"]["mach_number"] = 9.0
        with self.assertRaises(TaskSpecError):
            FixedCruiseTask.from_config(config)

    def test_load_from_modified_yaml_file_rejected(self):
        import tempfile

        text = TASK_PATH.read_text(encoding="utf-8").replace(
            "start_mass_kg: 145000.0", "start_mass_kg: 144000.0"
        )
        path = Path(tempfile.mkdtemp(prefix="concorde-task-test-")) / "task.yaml"
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(TaskSpecError):
            load_task_spec(path)

    def test_run_record_and_maml_context(self):
        record = self.task.run_record()
        self.assertEqual(record["task_id"], self.task.task_id)
        self.assertEqual(record["task_fingerprint"], self.task.fingerprint())
        context = self.task.maml_context()
        self.assertAlmostEqual(context["cruise_distance_m"], 3028020.0, places=6)
        self.assertAlmostEqual(context["start_mass_kg"], 145000.0, places=9)
        self.assertTrue(all(isinstance(value, float) for value in context.values()))

    def test_maml_task_spec_adapter(self):
        maml_task = self.task.to_maml_task_spec()
        self.assertEqual(maml_task.task_id, self.task.task_id)
        self.assertIn("cruise_distance_m", maml_task.context)
        self.assertEqual(maml_task.model_config["aircraft"], "Concorde")


class ConstraintContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = load_task_spec()

    def test_constraint_names_are_frozen(self):
        self.assertEqual(
            list(CONSTRAINT_NAMES),
            [
                "geometry_invalid",
                "task_mass_balance",
                "fuel_capacity_excess",
                "zero_fuel_excess",
                "takeoff_excess",
                "fuel_remaining_deficit",
                "max_throttle",
                "cruise_range_error",
                "mission_convergence",
                "trim_attitude_limit",
            ],
        )

    def test_empty_constraints_flag_geometry_invalid(self):
        constraints = empty_constraints()
        self.assertEqual(set(constraints), set(CONSTRAINT_NAMES))
        self.assertIsNone(constraints["geometry_invalid"])
        self.assertFalse(feasibility(constraints))
        self.assertEqual(empty_constraints(1.0)["geometry_invalid"], 1.0)

    def test_baseline_observations_are_feasible(self):
        constraints = evaluate_constraints(self.task, baseline_observations())
        self.assertEqual(set(constraints), set(CONSTRAINT_NAMES))
        self.assertTrue(all(value <= 0.0 for value in constraints.values()), constraints)
        self.assertTrue(feasibility(constraints))
        self.assertEqual(violated_constraints(constraints), {})
        self.assertAlmostEqual(constraints["task_mass_balance"], 0.0, places=12)
        self.assertAlmostEqual(constraints["cruise_range_error"], 0.0, places=12)
        self.assertAlmostEqual(constraints["mission_convergence"], 0.0, places=12)

    def test_throttle_violation_is_detected(self):
        constraints = evaluate_constraints(self.task, baseline_observations(max_throttle=1.27))
        self.assertGreater(constraints["max_throttle"], 0.0)
        self.assertFalse(feasibility(constraints))
        self.assertIn("max_throttle", violated_constraints(constraints))

    def test_non_convergence_is_detected(self):
        constraints = evaluate_constraints(
            self.task, baseline_observations(converged=False, solver_converged=True)
        )
        self.assertEqual(constraints["mission_convergence"], 1.0)
        self.assertFalse(feasibility(constraints))
        large_residual = evaluate_constraints(
            self.task, baseline_observations(residual_max=1.0)
        )
        self.assertEqual(large_residual["mission_convergence"], 1.0)

    def test_range_error_is_normalized(self):
        observations = baseline_observations(
            range_span_m=BASELINE_RANGE * 1.01, range_end_m=BASELINE_RANGE * 1.01
        )
        constraints = evaluate_constraints(self.task, observations)
        self.assertAlmostEqual(constraints["cruise_range_error"], 0.01, places=9)

    def test_trim_limit_uses_alpha(self):
        constraints = evaluate_constraints(self.task, baseline_observations(alpha_end_deg=15.0))
        self.assertAlmostEqual(constraints["trim_attitude_limit"], (15.0 - 12.0) / 12.0, places=9)
        self.assertFalse(feasibility(constraints))

    def test_fuel_and_mass_constraints(self):
        observations = baseline_observations(
            mass_end_kg=85000.0, fuel_burn_kg=60000.0, max_throttle=0.9
        )
        constraints = evaluate_constraints(self.task, observations)
        self.assertLess(constraints["fuel_capacity_excess"], 0.0)
        self.assertGreater(constraints["fuel_remaining_deficit"], 0.0)
        self.assertFalse(feasibility(constraints))

    def test_missing_observation_raises(self):
        observations = baseline_observations()
        del observations["fuel_burn_kg"]
        with self.assertRaises(ValueError):
            evaluate_constraints(self.task, observations)


class MissionAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = load_task_spec()

    def test_segment_is_configured_from_the_task(self):
        analyses = {"cruise": {"vehicle": object()}}
        mission, segment = build_single_cruise_mission(analyses, self.task)
        self.assertEqual(segment.tag, "level_cruise")
        self.assertAlmostEqual(segment.altitude, 18288.0, places=9)
        self.assertAlmostEqual(segment.mach_number, 2.02, places=12)
        self.assertAlmostEqual(segment.distance, 3028020.0, places=6)
        self.assertTrue(segment.flight_dynamics.force_x)
        self.assertTrue(segment.flight_dynamics.force_z)
        self.assertTrue(segment.assigned_control_variables.throttle.active)
        self.assertEqual(
            segment.assigned_control_variables.throttle.assigned_propulsors,
            [list(self.task.propulsor_tags)],
        )
        self.assertEqual(len(mission.segments), 1)

    def test_missing_analysis_raises(self):
        with self.assertRaises(MissionBuildError):
            build_single_cruise_mission({}, self.task)


class ObservationExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = load_task_spec()

    def test_happy_path(self):
        segment = synthetic_segment()
        observations = extract_observations(segment, self.task)
        self.assertEqual(observations["objective_name"], "fuel_burn_kg")
        self.assertAlmostEqual(observations["mass_start_kg"], 145000.0, places=9)
        self.assertAlmostEqual(observations["mass_end_kg"], 109300.0, places=9)
        self.assertAlmostEqual(observations["fuel_burn_kg"], 35700.0, places=9)
        self.assertAlmostEqual(observations["range_span_m"], BASELINE_RANGE, places=6)
        self.assertAlmostEqual(observations["time_span_s"], 5080.0, places=9)
        self.assertAlmostEqual(observations["max_throttle"], 0.9642, places=9)
        self.assertAlmostEqual(observations["max_fuel_mass_flow_kg_s"], 2.0, places=9)
        self.assertAlmostEqual(observations["max_thrust_x_n"], 43000.0, places=9)
        self.assertAlmostEqual(observations["alpha_end_deg"], math.degrees(0.04), places=9)
        self.assertTrue(observations["converged"])
        self.assertTrue(observations["solver_converged"])
        self.assertEqual(observations["history_samples"], 2)
        self.assertEqual(len(observations["propulsors"]), 4)

    def test_mass_increase_rejected(self):
        segment = synthetic_segment(mass=[109300.0, 145000.0])
        with self.assertRaises(ObservationError):
            extract_observations(segment, self.task)

    def test_range_decrease_rejected(self):
        segment = synthetic_segment(range_history=[BASELINE_RANGE, 0.0])
        with self.assertRaises(ObservationError):
            extract_observations(segment, self.task)

    def test_non_finite_mass_rejected(self):
        segment = synthetic_segment(mass=[145000.0, float("nan")])
        with self.assertRaises(ObservationError):
            extract_observations(segment, self.task)

    def test_short_history_rejected(self):
        segment = synthetic_segment(mass=[145000.0])
        with self.assertRaises(ObservationError):
            extract_observations(segment, self.task)

    def test_missing_propulsor_rejected(self):
        segment = synthetic_segment(missing_propulsor=True)
        with self.assertRaises(ObservationError):
            extract_observations(segment, self.task)

    def test_thrust_force_fallback(self):
        segment = synthetic_segment()
        propulsor = segment.state.conditions.energy.propulsors["inner_right_turbojet"]
        del propulsor.thrust
        propulsor.thrust_force = np.asarray([[42000.0], [41000.0]], dtype=float)
        observations = extract_observations(segment, self.task)
        self.assertAlmostEqual(observations["max_thrust_x_n"], 42000.0, places=9)


if __name__ == "__main__":
    unittest.main()
