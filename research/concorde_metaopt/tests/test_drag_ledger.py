"""Unit checks for drag component audit. Synthetic numbers, zero physics."""
import unittest

from research.concorde_metaopt.evaluation.drag_ledger import build_drag_ledger


def conditions():
    return {
        "freestream": {"dynamic_pressure": [4000.0, 5000.0]},
        "aerodynamics": {"coefficients": {"drag": {
            "total": [0.0102, 0.0102],
            "parasite": {"total": [0.004, 0.004]},
            "induced": {"total": [0.002, 0.002]},
            "compressible": {"total": [0.003, 0.003],
                             "wave": {"lift": [0.0006, 0.0006],
                                      "volume": [0.0007, 0.0007]}},
            "miscellaneous": {"total": [0.0003, 0.0003]},
            "cooling": {"total": [0.0002, 0.0002]},
            "trim": {"total": [0.0002, 0.0002]},
            "form": {"total": [0.0002, 0.0002]},
            "drag_coefficient_increment": [0.0001, 0.0001],
        }}},
    }


class DragLedgerOfflineTests(unittest.TestCase):
    def test_numerical_closure_is_not_physical_acceptance(self):
        ledger = build_drag_ledger(conditions(), reference_area_m2=358.25, trim_factor=1.02)
        self.assertEqual(ledger["status"], "ACCOUNTING_ONLY_UNVALIDATED")
        self.assertTrue(ledger["numerical_closure_passed"], ledger)
        self.assertAlmostEqual(ledger["numerical_closure_residual_cd"], 0.0, places=12)
        self.assertFalse(ledger["model_validated"])
        self.assertFalse(ledger["body_interference_validated"])
        self.assertAlmostEqual(ledger["total_drag_magnitude_n"], 0.0102 * 5000.0 * 358.25)

    def test_wave_subcomponents_not_in_additive_sum(self):
        ledger = build_drag_ledger(conditions(), reference_area_m2=358.25, trim_factor=1.02)
        self.assertEqual(ledger["diagnostic_subcomponents_cd_not_additive"]["wave_lift"], 0.0006)
        self.assertEqual(ledger["diagnostic_subcomponents_cd_not_additive"]["wave_volume"], 0.0007)
        self.assertTrue(ledger["numerical_closure_passed"])

    def test_missing_components_fail_closed(self):
        data = conditions()
        del data["aerodynamics"]["coefficients"]["drag"]["induced"]
        result = build_drag_ledger(data, reference_area_m2=358.25, trim_factor=1.02)
        self.assertEqual(result["status"], "PARTIAL_DATA_NOT_VALIDATED")
        self.assertIn("induced", result["missing_additive_components"])
        self.assertIsNone(result["numerical_closure_passed"])

    def test_missing_reference_area_cannot_create_force(self):
        ledger = build_drag_ledger(conditions(), trim_factor=1.02)
        self.assertIsNone(ledger["total_drag_magnitude_n"])
        self.assertEqual(ledger["status"], "PARTIAL_DATA_NOT_VALIDATED")


if __name__ == "__main__":
    unittest.main()
