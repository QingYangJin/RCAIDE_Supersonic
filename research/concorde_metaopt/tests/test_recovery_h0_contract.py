"""Guard tests for the H0 geometry contract (zero physical)."""
import unittest

from research.concorde_metaopt.dreal001.geometry import h0_contract as h0

class H0ContractTests(unittest.TestCase):
    def test_contract_is_reproducible_and_zero_physical(self):
        contract = h0.build_contract()
        verification = h0.verify_contract(contract)
        self.assertEqual(verification["failure_count"], 0)
        self.assertEqual(verification["status"], "H0_GEOMETRY_CONTRACT_REPRODUCIBLE")
        self.assertEqual(contract["physical_solver_starts_actual"], 0)
        self.assertEqual(contract["internal_solver_cases_actual"], 0)

    def test_variable_order_matches_the_frozen_twelve(self):
        contract = h0.build_contract()
        self.assertEqual(tuple(contract["variable_order_12d"]), h0.VARIABLE_ORDER)
        self.assertEqual(len(contract["baseline_x12"]), 12)
        self.assertEqual(contract["baseline_x12"], [358.25, 1.83, 67.0, 48.0, 71.0,
                                                    0.480469, 0.945313, 0.408284,
                                                    0.130178, 0.0, 33.91, 0.0])
        self.assertEqual(tuple(contract["fixed_variables"]), h0.FIXED_ORDER)

    def test_production_loader_conflict_is_recorded_not_hidden(self):
        # dreal006 S0 (issue 16) replaced the blanket "reject every frozen space"
        # guard with an evidence check, so the 12D YAML now loads.  What must
        # stay true either way: the probe reports the real loader outcome instead
        # of hiding it, the YAML is never silently rewritten, and the disposition
        # names whichever side the code is on.
        contract = h0.build_contract()
        probe = contract["production_loader_probe"]
        conflict = contract["freeze_conflict"]
        self.assertEqual(probe["loaded"], conflict["loader_accepts_the_frozen_yaml"])
        if probe["loaded"]:
            self.assertIsNone(probe["exception_type"])
            self.assertIn("accepts", conflict["summary"])
        else:
            self.assertEqual(probe["exception_type"], "DesignSpaceError")
            self.assertIn("rejects", conflict["summary"])
        self.assertFalse(conflict["silently_flipped_yaml"])
        self.assertTrue(conflict["yaml_frozen"])
        self.assertEqual(conflict["yaml_stage"], "P1")

    def test_optimization_subspace_is_limited_to_measured_variables(self):
        contract = h0.build_contract()
        self.assertEqual(tuple(contract["optimization_subspace"]), h0.RESPONSIVE_VARIABLES)
        self.assertEqual(set(contract["optimization_subspace"]), {"sweep_1", "sweep_2"})
        for name in h0.VARIABLE_ORDER:
            if name in contract["optimization_subspace"]:
                continue
            self.assertTrue(contract["held_fixed_variables"][name]["held_fixed"])
        self.assertIn("wing_area", contract["held_fixed_variables"])

    def test_baseline_geometry_reproduces_the_frozen_reference(self):
        contract = h0.build_contract()
        repro = contract["baseline_geometry_reproduction"]
        self.assertTrue(all(repro["matches_frozen_reference"].values()))
        self.assertEqual(contract["baseline_design_id"], h0.design_id(
            contract["baseline_x12"]))

    def test_contract_declares_its_limitations(self):
        contract = h0.build_contract()
        self.assertFalse(contract["physics_validated"])
        self.assertIn("VSPAERO runs in LIFTING_SURFACE_ONLY mode",
                      " ".join(contract["limitations"]))
        self.assertIn("NOT_VALIDATED", contract["aerodynamic_active_mask_status"])


if __name__ == "__main__":
    unittest.main()
