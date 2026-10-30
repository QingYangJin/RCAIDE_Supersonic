"""Non-physical regression tests for 12D fixed-fuselage geometry and DOE."""
import unittest
from pathlib import Path
from types import SimpleNamespace

from research.concorde_metaopt.aircraft.design_space import load_design_space
from research.concorde_metaopt.aircraft.geometry_checks import FAIL, model_checks
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.data.generate_doe import screen_design
from research.concorde_metaopt.data.schema import (
    GEOMETRY_VALID, make_candidate_row, check_candidate_row,
)
from research.concorde_metaopt.evaluation.low_fidelity import SingleCruiseBackend

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "design_space_12d_lifting_surfaces.yaml"


class TwelveDimensionalPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.space = load_design_space(CONFIG)
        cls.design = cls.space.baseline_dict()

    def test_full_geometry_preserves_fixed_fuselage(self):
        full = self.space.expand(self.design)
        self.assertEqual(len(self.design), 12)
        self.assertEqual(len(full), 15)
        self.assertNotIn("fuselage_length", self.design)
        self.assertAlmostEqual(full["fuselage_length"], 61.66)

    def test_geometry_check_uses_declared_variables_and_fixed_values(self):
        full = self.space.expand(self.design)
        geometry = build_geometry(tuple(full), tuple(full.values()))
        checks = model_checks(geometry, self.space)
        gate = [check for check in checks if check.check_id == "G23_design_space_bounds"]
        self.assertEqual(len(gate), 1)
        self.assertNotEqual(gate[0].status, FAIL)

    def test_12d_screen_is_not_physical_evaluation(self):
        result = screen_design(self.space, self.design)
        self.assertEqual(result["status"], GEOMETRY_VALID, result)
        row = make_candidate_row(
            self.space, self.design, batch_id="offline", batch_index=0,
            sample_index=0, method="lhs", seed=42,
            geometry_status=result["status"], metrics=result["metrics"],
        )
        self.assertEqual(check_candidate_row(row, self.space), [])
        self.assertEqual(row["physical_call_count"], 0)
        self.assertNotIn("objective", row)
        self.assertEqual(len(row["design"]), 12)

    def test_legacy_fuselage_variable_cannot_be_smuggled_in(self):
        result = screen_design(self.space, self.design)
        row = make_candidate_row(
            self.space, self.design, batch_id="offline", batch_index=0,
            sample_index=0, method="lhs", seed=42,
            geometry_status=result["status"], metrics=result["metrics"],
        )
        row["design"]["fuselage_length"] = 61.66
        errors = check_candidate_row(row, self.space)
        self.assertTrue(any("undeclared" in item for item in errors), errors)

    def test_mission_preflight_expands_geometry_but_does_not_run_mission(self):
        backend = SingleCruiseBackend.__new__(SingleCruiseBackend)
        backend.design_space = self.space
        backend.names = tuple(self.space.names)
        backend.fidelity = "single_cruise"
        backend.task = SimpleNamespace(task_id="offline", fingerprint=lambda: "offline")
        backend._tutorial_sha256 = "offline-only"
        backend._template_hash_verified = False
        result = backend.preflight()
        self.assertEqual(result["physical_call_count"], 0)
        self.assertEqual(result["design_space_config"]["design_dim"], 12)
        self.assertAlmostEqual(result["baseline"]["fuselage_length_m"], 61.66)


if __name__ == "__main__":
    unittest.main()
