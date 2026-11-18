"""Unadmitted numerical model checks, not mesh/solver or active-mask evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("recovery_geometry_diagnostic",
    ROOT / "docs/evidence/drecover001/diagnose_geometry_effects.py")
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)


class GeometryEffectDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load(diag.CONFIG.read_bytes())

    def test_all_twelve_change_only_expected_numeric_component(self):
        before = copy.deepcopy(self.config)
        report = diag.diagnose(self.config)
        self.assertEqual(report["expected_component_only_count"], 12)
        self.assertEqual(len(report["probes"]), 12)
        self.assertEqual(self.config, before)
        self.assertFalse(report["freeze_issued"])
        self.assertFalse(report["real_admission"])
        self.assertEqual(report["aerodynamic_active_mask"], "NOT_VALIDATED")
        self.assertEqual(report["openvsp_builds"], 0)
        self.assertEqual(report["physical_solver_starts_actual"], 0)

    def test_diagnostic_does_not_call_or_patch_production_loader(self):
        with patch.object(diag, "load_design_space", side_effect=AssertionError("called")):
            self.assertEqual(diag.diagnose(self.config)["expected_component_only_count"], 12)
        with self.assertRaisesRegex(diag.DesignSpaceError, "provisional"):
            diag.load_design_space(diag.CONFIG)

    def test_reordered_or_renamed_active_variables_rejected(self):
        for change in ("swap", "rename"):
            config = copy.deepcopy(self.config)
            if change == "swap":
                config["variables"][0], config["variables"][1] = config["variables"][1], config["variables"][0]
            else:
                config["variables"][0]["name"] = "fuselage_length"
            with self.assertRaisesRegex(ValueError, "12D identity/order"):
                diag.diagnose(config)

    def test_changed_fixed_fuselage_identity_rejected(self):
        self.config["fixed_variables"][0]["id"] = "invalid"
        with self.assertRaisesRegex(ValueError, "fixed fuselage identity/order"):
            diag.diagnose(self.config)

    def test_invalid_bounds_rejected(self):
        for low, high in ((1., 0.), (0., float("nan")), (float("-inf"), float("inf"))):
            config = copy.deepcopy(self.config)
            config["variables"][0].update(lower=low, upper=high)
            with self.assertRaises((ValueError, OverflowError)):
                diag.diagnose(config)

    def test_input_echo_is_not_counted_as_geometry_effect(self):
        original = diag.build_geometry
        baseline = original([r["name"] for r in self.config["variables"] + self.config["fixed_variables"]],
                            [r["baseline"] for r in self.config["variables"] + self.config["fixed_variables"]])
        with patch.object(diag, "build_geometry", return_value=baseline):
            report = diag.diagnose(self.config)
        self.assertEqual(report["expected_component_only_count"], 0)
        self.assertTrue(all(not p["changed_components"] for p in report["probes"]))

    def test_high_bound_baseline_uses_negative_step(self):
        self.config["variables"][0]["baseline"] = self.config["variables"][0]["upper"]
        report = diag.diagnose(self.config)
        self.assertLess(report["probes"][0]["delta"], 0.)
        self.assertTrue(report["probes"][0]["expected_component_only"])


if __name__ == "__main__":
    unittest.main()
