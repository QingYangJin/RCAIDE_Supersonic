"""Unit tests for the provisional 15D design-space contract (P1).
"""
import copy
import unittest
from pathlib import Path

from research.concorde_metaopt.aircraft import design_space as ds
from research.concorde_metaopt.config_io import ConfigError, load_config, load_yaml_subset

CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "design_space_15d.yaml"


def load_raw_config():
    return load_config(CONFIG_PATH)


class LoadRealConfigTests(unittest.TestCase):
    def setUp(self):
        self.space = ds.load_design_space(CONFIG_PATH)

    def test_declares_fifteen_ordered_variables(self):
        self.assertEqual(len(self.space.variables), 15)
        self.assertEqual(self.space.ids, ds.EXPECTED_IDS)
        self.assertEqual(self.space.names, ds.EXPECTED_NAMES)

    def test_is_explicitly_provisional(self):
        self.assertFalse(self.space.frozen)
        self.assertEqual(self.space.bounds_status, "provisional_until_geometry_perturbation")
        self.assertEqual(self.space.units, "SI")
        self.assertEqual(len(self.space.freeze_requires), 3)

    def test_source_records_baseline_sha(self):
        self.assertEqual(
            self.space.source["baseline_sha256"],
            "4c633e485a915151faaa8104e6647f9dc02bd08ae1436c22845e5917b3d735bd",
        )

    def test_baseline_is_inside_bounds_and_constraints(self):
        baseline = self.space.baseline_dict()
        self.assertEqual(len(baseline), 15)
        self.assertEqual(self.space.check_physical(baseline), [])
        self.assertAlmostEqual(baseline["wing_area"], 358.25)
        self.assertAlmostEqual(baseline["span_location_2"], 0.480469)
        self.assertAlmostEqual(baseline["fuselage_height_width_ratio"], 1.152778)

    def test_units_and_targets_are_populated(self):
        for variable in self.space.variables:
            self.assertIn(variable.unit, ("m^2", "m", "deg", "dimensionless"))
            self.assertTrue(variable.target)
            self.assertLess(variable.lower, variable.upper)
            self.assertGreaterEqual(variable.baseline, variable.lower)
            self.assertLessEqual(variable.baseline, variable.upper)
            self.assertGreater(variable.scale, 0.0)


class NormalisationTests(unittest.TestCase):
    def setUp(self):
        self.space = ds.load_design_space(CONFIG_PATH)

    def test_baseline_normalises_to_zero(self):
        normalized = self.space.to_normalized(self.space.baseline_dict())
        self.assertEqual(normalized, (0.0,) * 15)

    def test_normalisation_roundtrip(self):
        physical = self.space.baseline_dict()
        physical["wing_area"] = 400.0
        physical["sweep_1"] = 70.0
        physical["tip_twist"] = -2.0
        normalized = self.space.to_normalized(physical)
        restored = self.space.from_normalized(normalized)
        for name in self.space.names:
            self.assertAlmostEqual(restored[name], physical[name], places=9)

    def test_unit_interval_roundtrip_and_ordering(self):
        physical = self.space.baseline_dict()
        fractions = self.space.to_unit_interval(physical)
        for fraction in fractions:
            self.assertGreaterEqual(fraction, 0.0)
            self.assertLessEqual(fraction, 1.0)
        restored = self.space.from_unit_interval(fractions)
        for name in self.space.names:
            self.assertAlmostEqual(restored[name], physical[name], places=9)

    def test_wrong_vector_length_is_rejected(self):
        with self.assertRaises(ds.DesignSpaceError):
            self.space.from_normalized([0.0] * 14)
        with self.assertRaises(ds.DesignSpaceError):
            self.space.to_normalized({"wing_area": 358.25})


class BoundsTests(unittest.TestCase):
    def setUp(self):
        self.space = ds.load_design_space(CONFIG_PATH)

    def test_out_of_bounds_value_is_reported(self):
        physical = self.space.baseline_dict()
        physical["wing_area"] = 1000.0
        violations = self.space.check_bounds(physical)
        self.assertTrue(any("wing_area" in item for item in violations))

    def test_non_finite_value_is_reported(self):
        physical = self.space.baseline_dict()
        physical["aspect_ratio"] = float("nan")
        violations = self.space.check_bounds(physical)
        self.assertTrue(any("aspect_ratio" in item for item in violations))

    def test_missing_variable_is_reported(self):
        physical = self.space.baseline_dict()
        del physical["tip_twist"]
        with self.assertRaises(ds.DesignSpaceError):
            self.space.check_bounds(physical)

    def test_unknown_variable_is_rejected(self):
        with self.assertRaises(ds.DesignSpaceError):
            self.space.variable("horizontal_tail_area")


class CrossConstraintTests(unittest.TestCase):
    def setUp(self):
        self.space = ds.load_design_space(CONFIG_PATH)

    def assert_violation(self, physical, code):
        violations = self.space.check_cross_constraints(physical)
        self.assertTrue(any(item.startswith(code) for item in violations), violations)

    def test_span_breakpoints_must_increase(self):
        physical = self.space.baseline_dict()
        physical["span_location_2"] = 0.95
        physical["span_location_3"] = 0.90
        self.assert_violation(physical, "C01")

    def test_chords_must_decrease_outboard(self):
        physical = self.space.baseline_dict()
        physical["chord_ratio_3"] = 0.45
        self.assert_violation(physical, "C02")

    def test_chord_ratio_two_must_stay_below_one(self):
        physical = self.space.baseline_dict()
        physical["chord_ratio_2"] = 1.0
        self.assert_violation(physical, "C02")

    def test_positive_quantities(self):
        physical = self.space.baseline_dict()
        physical["vertical_tail_area"] = -1.0
        self.assert_violation(physical, "C03")

    def test_sweep_range(self):
        physical = self.space.baseline_dict()
        physical["sweep_2"] = 100.0
        self.assert_violation(physical, "C04")


class ConfigValidationTests(unittest.TestCase):
    def setUp(self):
        self.raw = load_raw_config()

    def build(self, data):
        return ds.design_space_from_config(data, source="<test>")

    def test_missing_top_level_key_is_rejected(self):
        data = copy.deepcopy(self.raw)
        del data["cross_constraints"]
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_wrong_number_of_variables_is_rejected(self):
        data = copy.deepcopy(self.raw)
        data["variables"] = data["variables"][:-1]
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_swapped_variable_order_is_rejected(self):
        data = copy.deepcopy(self.raw)
        data["variables"][13], data["variables"][14] = data["variables"][14], data["variables"][13]
        with self.assertRaises(ds.DesignSpaceError) as context:
            self.build(data)
        self.assertIn("variable order", str(context.exception))

    def test_duplicate_id_is_rejected(self):
        data = copy.deepcopy(self.raw)
        data["variables"][11]["id"] = "W01"
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_wrong_unit_is_rejected(self):
        data = copy.deepcopy(self.raw)
        data["variables"][0]["unit"] = "ft^2"
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_baseline_outside_bounds_is_rejected(self):
        data = copy.deepcopy(self.raw)
        data["variables"][0]["baseline"] = 500.0
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_frozen_space_is_rejected_until_measured(self):
        data = copy.deepcopy(self.raw)
        data["frozen"] = True
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_missing_cross_constraint_is_rejected(self):
        data = copy.deepcopy(self.raw)
        data["cross_constraints"] = [rule for rule in data["cross_constraints"] if rule["id"] != "C04"]
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_baseline_that_breaks_cross_constraints_is_rejected(self):
        data = copy.deepcopy(self.raw)
        data["variables"][5]["baseline"] = 0.99
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_baseline_geometry_root_chord_conflict_is_rejected(self):
        data = copy.deepcopy(self.raw)
        data["baseline_geometry"]["main_wing"]["root_chord_m"] = 1.0
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_baseline_geometry_span_conflict_is_rejected(self):
        data = copy.deepcopy(self.raw)
        data["baseline_geometry"]["main_wing"]["projected_span_m"] = 24.0
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_baseline_geometry_tail_span_conflict_is_rejected(self):
        data = copy.deepcopy(self.raw)
        data["baseline_geometry"]["vertical_stabilizer"]["projected_span_m"] = 6.0
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_baseline_geometry_section_count_is_validated(self):
        data = copy.deepcopy(self.raw)
        data["baseline_geometry"]["main_wing"]["section_span_fractions"] = [0.0, 1.0]
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_baseline_geometry_exposed_area_must_match_reference(self):
        data = copy.deepcopy(self.raw)
        data["baseline_geometry"]["main_wing"]["exposed_area_m2"] = 326.5
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_baseline_geometry_status_is_required(self):
        data = copy.deepcopy(self.raw)
        data["baseline_geometry"]["status"] = ""
        with self.assertRaises(ds.DesignSpaceError):
            self.build(data)

    def test_c03_documents_aspect_ratio(self):
        expressions = {
            str(rule.get("id")): str(rule.get("expression")) for rule in self.raw["cross_constraints"]
        }
        self.assertIn("aspect_ratio", expressions["C03"])


class YamlSubsetTests(unittest.TestCase):
    def test_nested_mapping_and_sequence(self):
        text = "\n".join(
            [
                "outer:",
                "  items:",
                "    - name: first",
                "      value: 1",
                "    - name: second",
                "      value: 2.5",
                "  flag: true",
            ]
        )
        parsed = load_yaml_subset(text)
        self.assertEqual(parsed["outer"]["items"][0], {"name": "first", "value": 1})
        self.assertEqual(parsed["outer"]["items"][1]["value"], 2.5)
        self.assertIs(parsed["outer"]["flag"], True)

    def test_inline_list_and_hash_in_quotes(self):
        parsed = load_yaml_subset('sweeps: [63.0, 40.0, 0]\nissue: "#1 METAOPT-00"\n')
        self.assertEqual(parsed["sweeps"], [63.0, 40.0, 0])
        self.assertEqual(parsed["issue"], "#1 METAOPT-00")

    def test_comments_and_blank_lines(self):
        parsed = load_yaml_subset("# top\n\na: 1  # trailing\n\n# end\nb: text\n")
        self.assertEqual(parsed, {"a": 1, "b": "text"})

    def test_tabs_are_rejected(self):
        with self.assertRaises(ConfigError):
            load_yaml_subset("a:\n\tb: 1\n")

    def test_duplicate_keys_are_rejected(self):
        with self.assertRaises(ConfigError):
            load_yaml_subset("a: 1\na: 2\n")

    def test_inconsistent_indentation_is_rejected(self):
        with self.assertRaises(ConfigError):
            load_yaml_subset("a: 1\n  b: 2\n")


if __name__ == "__main__":
    unittest.main()
