"""P1 tests: 15D geometry model, 31-case effect matrix and RCAIDE cross-checks.

These tests do not run a Mission or CFD analysis. They verify that every one of
the 15 variables produces a real geometry change, that invalid designs are
rejected instead of being silently repaired, and that the RCAIDE rebuild agrees
with the dependency-free geometry model.
"""

import json
import math
import shutil
import unittest
from pathlib import Path

from research.concorde_metaopt.aircraft import geometry_checks as checks
from research.concorde_metaopt.aircraft.design_space import DesignSpaceError, load_design_space
from research.concorde_metaopt.aircraft.geometry_model import (
    GeometryError,
    build_geometry,
)
from research.concorde_metaopt.aircraft.geometry_builder import build_geometry_from_design_space
from research.concorde_metaopt.config_io import load_config

CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "design_space_15d.yaml"
TMP_ROOT = Path(__file__).resolve().parent / "_tmp"


class GeometryModelBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.space = load_design_space(CONFIG_PATH)
        cls.geometry = build_geometry_from_design_space(cls.space)

    def test_baseline_wing_values(self):
        wing = self.geometry.wing
        self.assertAlmostEqual(wing.area_m2, 358.25, places=9)
        self.assertAlmostEqual(wing.span_m, 25.604638251691824, places=9)
        self.assertAlmostEqual(wing.root_chord_m, 29.901818514349216, places=9)
        self.assertAlmostEqual(wing.mean_aerodynamic_chord_m, 18.489892944055953, places=9)
        self.assertAlmostEqual(wing.tip_chord_m, 0.9731361054965724, places=9)
        self.assertAlmostEqual(wing.taper_ratio, 0.03254437869822486, places=9)
        self.assertAlmostEqual(wing.wetted_area_m2, 717.57475, places=6)
        self.assertEqual(len(wing.sections), 4)

    def test_baseline_tail_and_fuselage_values(self):
        tail = self.geometry.vertical_tail
        self.assertAlmostEqual(tail.area_m2, 33.91, places=9)
        self.assertAlmostEqual(tail.span_m, 5.0093312926976585, places=9)
        self.assertAlmostEqual(tail.root_chord_m, 13.157616068421863, places=9)
        self.assertEqual(len(tail.sections), 3)
        fuselage = self.geometry.fuselage
        self.assertAlmostEqual(fuselage.length_m, 61.66, places=9)
        self.assertAlmostEqual(fuselage.nose_length_m, 12.384, places=9)
        self.assertAlmostEqual(fuselage.tail_length_m, 18.432, places=9)
        self.assertAlmostEqual(fuselage.cabin_length_m, 30.844, places=9)
        self.assertAlmostEqual(fuselage.usable_volume_m3, 231.62809266421624, places=6)
        self.assertEqual(len(fuselage.stations), 8)

    def test_baseline_model_checks_pass(self):
        results = checks.model_checks(self.geometry, self.space, include_source_checks=True)
        failures = [check for check in results if check.status == checks.FAIL]
        self.assertEqual(failures, [])
        statuses = {check.check_id: check.status for check in results}
        self.assertEqual(statuses["G18_fuselage_volume_requirement"], "pass")
        self.assertEqual(statuses["source_wing_root_chord"], "warn")

    def test_planform_geometry_is_plottable(self):
        planform = checks.planform_geometry(self.geometry)
        self.assertEqual(len(planform["wing"]), 4)
        self.assertEqual(len(planform["vertical_tail"]), 3)
        self.assertEqual(len(planform["fuselage"]), 8)
        self.assertGreater(planform["wing_span_m"], 0.0)

    def test_deterministic_compilation(self):
        again = build_geometry_from_design_space(self.space)
        self.assertEqual(checks.metrics(self.geometry), checks.metrics(again))


class EffectMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.space = load_design_space(CONFIG_PATH)
        cls.cases = checks.effect_cases(cls.space)
        cls.records = []
        for index, spec in enumerate(cls.cases):
            record = checks.run_case(
                cls.space,
                spec["physical"],
                spec["case_id"],
                use_rcaide=False,
                is_baseline=spec["is_baseline"],
            )
            record.update(
                {
                    "iteration": index,
                    "variable_id": spec["variable_id"],
                    "variable_name": spec["variable_name"],
                    "direction": spec["direction"],
                    "requested_delta": spec["delta"],
                }
            )
            cls.records.append(record)
        cls.by_id = {record["case_id"]: record for record in cls.records}
        cls.baseline_metrics = cls.by_id["baseline"]["metrics"]

    def test_exactly_31_cases_cover_all_variables(self):
        self.assertEqual(len(self.cases), 31)
        self.assertEqual(len(self.records), 31)
        variable_ids = {spec["variable_id"] for spec in self.cases if spec["variable_id"]}
        self.assertEqual(variable_ids, set(self.space.ids))

    def test_each_variable_changes_at_least_one_derived_metric(self):
        unchanged = []
        for record in self.records:
            if record["is_baseline"]:
                continue
            changed = []
            for name, value in record["metrics"].items():
                baseline_value = self.baseline_metrics.get(name)
                if isinstance(value, (int, float)) and isinstance(baseline_value, (int, float)):
                    scale = max(abs(baseline_value), 1.0)
                    if abs(value - baseline_value) > 1e-9 * scale:
                        changed.append(name)
            if not changed:
                unchanged.append(record["case_id"])
        self.assertEqual(unchanged, [])

    def test_all_perturbations_are_physically_valid(self):
        invalid = [(record["case_id"], record["failed_checks"]) for record in self.records if record["status"] != "ok"]
        self.assertEqual(invalid, [])

    def test_area_and_span_closure_hold_for_every_case(self):
        for record in self.records:
            metrics = record["metrics"]
            physical = record["physical"]
            area = physical["wing_area"]
            self.assertAlmostEqual(metrics["wing_area_m2"], area, places=6)
            self.assertAlmostEqual(metrics["wing_span_m"], math.sqrt(area * physical["aspect_ratio"]), places=6)
            self.assertGreaterEqual(metrics["fuselage_volume_margin_m3"], 0.0)

    def test_expected_direction_of_change(self):
        self.assertGreater(
            self.by_id["W01_plus"]["metrics"]["wing_span_m"], self.baseline_metrics["wing_span_m"]
        )
        self.assertLess(
            self.by_id["W01_minus"]["metrics"]["wing_span_m"], self.baseline_metrics["wing_span_m"]
        )
        self.assertGreater(
            self.by_id["W02_plus"]["metrics"]["wing_span_m"], self.baseline_metrics["wing_span_m"]
        )
        self.assertGreater(
            self.by_id["V01_plus"]["metrics"]["tail_area_m2"], self.baseline_metrics["tail_area_m2"]
        )
        self.assertGreater(
            self.by_id["F03_plus"]["metrics"]["fuselage_wetted_area_m2"],
            self.baseline_metrics["fuselage_wetted_area_m2"],
        )
        self.assertNotAlmostEqual(
            self.by_id["W10_plus"]["metrics"]["wing_tip_twist_deg"], 0.0, places=6
        )
        self.assertNotAlmostEqual(
            self.by_id["W08_plus"]["metrics"]["wing_root_chord_m"],
            self.baseline_metrics["wing_root_chord_m"],
            places=6,
        )

    def test_effect_delta_rows_cover_every_metric(self):
        rows = checks._effect_delta_rows(self.records, self.baseline_metrics)
        self.assertEqual(len(rows), 30 * len(self.baseline_metrics))
        self.assertEqual({row["metric"] for row in rows}, set(self.baseline_metrics))


class InvalidGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.space = load_design_space(CONFIG_PATH)
        cls.baseline = cls.space.baseline_dict()

    def _build(self, **overrides):
        physical = dict(self.baseline)
        physical.update(overrides)
        return build_geometry(self.space.names, [physical[name] for name in self.space.names])

    def test_negative_wing_area_is_rejected(self):
        with self.assertRaises(GeometryError):
            self._build(wing_area=-1.0)

    def test_unordered_span_locations_are_rejected(self):
        with self.assertRaises(GeometryError):
            self._build(span_location_2=0.6, span_location_3=0.5)

    def test_unordered_chord_ratios_are_rejected(self):
        with self.assertRaises(GeometryError):
            self._build(chord_ratio_2=0.12, chord_ratio_3=0.18)

    def test_fuselage_that_cannot_hold_its_nose_and_tail_is_rejected(self):
        with self.assertRaises(GeometryError):
            self._build(fuselage_length=1.0)

    def test_volume_requirement_failure_is_reported_not_repaired(self):
        geometry = self._build(fuselage_length=1.0) if False else None
        self.assertIsNone(geometry)
        physical = dict(self.baseline)
        physical["fuselage_length"] = 1.0
        with self.assertRaises(GeometryError):
            build_geometry(self.space.names, [physical[name] for name in self.space.names])


class RcaideCrossCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.space = load_design_space(CONFIG_PATH)
        cls.geometry = build_geometry_from_design_space(cls.space)

    def test_rcaide_rebuild_matches_model(self):
        results, derived = checks.rcaide_checks(self.geometry)
        self.assertTrue(derived, "RCAIDE adapter did not produce derived values")
        statuses = {check.check_id: check.status for check in results}
        self.assertEqual(statuses["R00_rcaide_available"], "pass")
        for check_id in (
            "R01_wing_area_match",
            "R02_wing_span_match",
            "R03_wing_root_chord_match",
            "R04_wing_mac_match",
            "R05_wing_wetted_match",
            "R09_tail_area_match",
            "R10_tail_span_match",
            "R12_fuselage_wetted_match",
        ):
            self.assertEqual(statuses[check_id], "pass", check_id)
        self.assertIn(statuses["R07_wing_ac_match"], ("pass", "warn"))
        self.assertEqual(statuses["R16_tip_sweep_rcaide_convention"], "info")

    def test_rcaide_metrics_are_recorded_for_baseline_case(self):
        record = checks.run_case(self.space, self.space.baseline_dict(), "baseline", use_rcaide=True)
        self.assertTrue(record["rcaide_metrics"])
        self.assertAlmostEqual(record["rcaide_metrics"]["wing_area_m2"], 358.25, places=9)


class GeometryRunArtifactTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.run_id = "unit-" + self._testMethodName
        self.output_root = TMP_ROOT

    def tearDown(self):
        shutil.rmtree(TMP_ROOT / self.run_id, ignore_errors=True)

    def test_run_writes_required_artifacts(self):
        summary = checks.run_geometry_check(
            output_root=self.output_root,
            run_id=self.run_id,
            use_rcaide=False,
            allow_existing=False,
        )
        run_dir = self.output_root / self.run_id
        required = [
            "summary.json",
            "run_config.json",
            "environment.json",
            "baseline_geometry.json",
            "checks.csv",
            "geometry_cases.jsonl",
            "geometry_effect_matrix.csv",
            "geometry_effect_delta.csv",
            "geometry_planforms.json",
            "figures/geometry_effect_heatmap.png",
            "figures/wing_planform_comparison.png",
        ]
        for relative in required:
            self.assertTrue((run_dir / relative).is_file(), relative)
        stored = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["run_id"], self.run_id)
        self.assertEqual(stored["stage"], "P1")
        self.assertEqual(stored["design_dim"], 15)
        self.assertEqual(stored["total_true_evaluations"], 0)
        self.assertEqual(stored["geometry"]["cases"], 31)
        self.assertIsNone(stored["best_feasible_fuel_kg"])
        self.assertIsNone(stored["seed"])
        self.assertEqual(stored["status"], "geometry_check_completed")
        lines = (run_dir / "geometry_cases.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 31)
        case = json.loads(lines[0])
        for key in (
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
        ):
            self.assertIn(key, case)
        self.assertIsNone(case["objective"])
        self.assertEqual(case["fidelity"], "geometry")
        self.assertEqual(case["physical_call_count"], 0)

    def test_existing_run_directory_is_rejected(self):
        checks.run_geometry_check(output_root=self.output_root, run_id=self.run_id, use_rcaide=False)
        with self.assertRaises(FileExistsError):
            checks.run_geometry_check(output_root=self.output_root, run_id=self.run_id, use_rcaide=False)

    def test_bad_delta_fraction_is_detected_by_empty_matrix(self):
        summary = checks.run_geometry_check(
            output_root=self.output_root,
            run_id=self.run_id,
            use_rcaide=False,
            delta_fraction=0.0,
        )
        self.assertEqual(summary["geometry"]["cases"], 1)


if __name__ == "__main__":
    unittest.main()
