"""Unit tests for the 12D lifting-surface design-space contract (D-12D-001).

The 12D set declares W01-W10 and V01-V02 and keeps the fuselage F01-F03 fixed.
These tests pin the loader behaviour: the declared dimension is 12, the fixed
variables are mandatory, ordered and re-injected for the 15-name geometry model,
and the legacy 15D config is unchanged.
"""
import copy
import unittest
from pathlib import Path

from research.concorde_metaopt.aircraft import design_space as ds
from research.concorde_metaopt.config_io import load_config

CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "design_space_12d_lifting_surfaces.yaml"
LEGACY_15D_PATH = Path(__file__).resolve().parent.parent / "configs" / "design_space_15d.yaml"


def load_raw_config():
    return load_config(CONFIG_PATH)


class LoadReal12DConfigTests(unittest.TestCase):
    def setUp(self):
        self.space = ds.load_design_space(CONFIG_PATH)

    def test_declares_twelve_ordered_lifting_surface_variables(self):
        self.assertEqual(self.space.design_set, "12d_lifting_surfaces")
        self.assertEqual(self.space.design_dim, 12)
        self.assertEqual(len(self.space.variables), 12)
        self.assertEqual(self.space.ids, ds.EXPECTED_IDS[:12])
        self.assertEqual(self.space.names, ds.LIFTING_SURFACE_NAMES)

    def test_fixes_the_three_fuselage_variables(self):
        self.assertEqual(self.space.fixed_names, ds.FIXED_FUSELAGE_NAMES)
        self.assertEqual(len(self.space.fixed_variables), 3)
        fixed = self.space.fixed_dict
        self.assertAlmostEqual(fixed["fuselage_length"], 61.66)
        self.assertAlmostEqual(fixed["fuselage_fineness"], 4.3)
        self.assertAlmostEqual(fixed["fuselage_height_width_ratio"], 1.152778)

    def test_expand_rebuilds_the_fifteen_name_geometry_vector(self):
        expanded = self.space.expand(self.space.baseline_dict())
        self.assertEqual(tuple(expanded), ds.EXPECTED_NAMES)
        self.assertEqual(len(expanded), 15)
        self.assertEqual(self.space.full_baseline_dict(), expanded)
        self.assertAlmostEqual(expanded["fuselage_length"], 61.66)
        self.assertAlmostEqual(expanded["wing_area"], 358.25)

    def test_baseline_is_physically_valid_including_cross_constraints(self):
        self.assertEqual(self.space.check_physical(self.space.baseline_dict()), [])
        self.assertEqual(self.space.check_cross_constraints(self.space.baseline_dict()), [])
        summary = self.space.config_summary()
        self.assertEqual(summary["design_set"], "12d_lifting_surfaces")
        self.assertEqual(summary["geometry_dim"], 15)
        self.assertEqual(summary["design_dim"], 12)

    def test_stays_provisional_and_records_the_fixed_fuselage_source(self):
        self.assertFalse(self.space.frozen)
        self.assertEqual(self.space.bounds_status, "provisional_until_geometry_perturbation")
        for fixed in self.space.fixed_variables:
            self.assertIn("owner decision", fixed.source)


class ExpandedVectorTests(unittest.TestCase):
    def setUp(self):
        self.space = ds.load_design_space(CONFIG_PATH)

    def test_expand_rejects_missing_declared_variable(self):
        with self.assertRaises(ds.DesignSpaceError):
            self.space.expand({})

    def test_expand_rejects_a_fixed_variable_supplied_by_the_caller(self):
        physical = self.space.baseline_dict()
        physical["fuselage_length"] = 62.0
        with self.assertRaises(ds.DesignSpaceError):
            self.space.expand(physical)

    def test_expand_rejects_an_undeclared_extra_name(self):
        physical = self.space.baseline_dict()
        physical["mystery"] = 1.0
        with self.assertRaises(ds.DesignSpaceError):
            self.space.expand(physical)


class RejectionTests(unittest.TestCase):
    def setUp(self):
        self.raw = load_raw_config()

    def test_missing_fixed_variables_are_rejected(self):
        raw = copy.deepcopy(self.raw)
        del raw["fixed_variables"]
        with self.assertRaises(ds.DesignSpaceError):
            ds.design_space_from_config(raw, source="<test>")

    def test_wrong_fixed_variable_count_is_rejected(self):
        raw = copy.deepcopy(self.raw)
        raw["fixed_variables"] = raw["fixed_variables"][:2]
        with self.assertRaises(ds.DesignSpaceError):
            ds.design_space_from_config(raw, source="<test>")

    def test_wrong_fixed_variable_order_is_rejected(self):
        raw = copy.deepcopy(self.raw)
        raw["fixed_variables"] = [raw["fixed_variables"][1], raw["fixed_variables"][0], raw["fixed_variables"][2]]
        with self.assertRaises(ds.DesignSpaceError):
            ds.design_space_from_config(raw, source="<test>")

    def test_fixed_variable_without_source_is_rejected(self):
        raw = copy.deepcopy(self.raw)
        del raw["fixed_variables"][0]["source"]
        with self.assertRaises(ds.DesignSpaceError):
            ds.design_space_from_config(raw, source="<test>")

    def test_unknown_design_set_is_rejected(self):
        raw = copy.deepcopy(self.raw)
        raw["design_set"] = "13d"
        with self.assertRaises(ds.DesignSpaceError):
            ds.design_space_from_config(raw, source="<test>")

    def test_twelve_dim_set_must_not_declare_fuselage_bounds(self):
        raw = copy.deepcopy(self.raw)
        legacy = load_config(LEGACY_15D_PATH)
        raw["variables"] = list(raw["variables"]) + list(legacy["variables"][12:])
        with self.assertRaises(ds.DesignSpaceError):
            ds.design_space_from_config(raw, source="<test>")

    def test_legacy_15d_config_keeps_its_fifteen_variables(self):
        legacy = ds.load_design_space(LEGACY_15D_PATH)
        self.assertEqual(legacy.design_set, "15d")
        self.assertEqual(legacy.design_dim, 15)
        self.assertEqual(len(legacy.variables), 15)
        self.assertEqual(legacy.fixed_variables, ())
        self.assertEqual(legacy.expand(legacy.baseline_dict()), legacy.baseline_dict())

    def test_baseline_geometry_is_checked_through_the_expanded_vector(self):
        raw = copy.deepcopy(self.raw)
        raw["baseline_geometry"]["main_wing"]["root_chord_m"] = 33.8
        with self.assertRaises(ds.DesignSpaceError):
            ds.design_space_from_config(raw, source="<test>")


if __name__ == "__main__":
    unittest.main()